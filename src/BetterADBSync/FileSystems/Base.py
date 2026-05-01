from __future__ import annotations

import asyncio
import logging
import os
import stat
import time
from typing import Iterable, List, Optional, Tuple, Union

from rich.filesize import decimal
from rich.progress import Progress

from ..SAOLogging import (
    _fmt_duration,
    _fmt_size_iec,
    copied_file_name_progress,
    copying_file_name_progress,
    info_print_progress,
    logging_fatal,
    overall_progress,
    perror,
    truncate_path,
)
from ..types import FileInfo, TreeDict


class FileSystem:
    def __init__(self, adb_arguments: List[str]) -> None:
        self.adb_arguments = adb_arguments
        self.total_files = 0
        self.total_size = 0
        self.counting_progress: Optional[Progress] = None
        self.counting_progress_id = 0
        self.total_folders = 0

        self.copied_files = 0
        self.copied_size = 0
        self.process = None

    async def _get_files_tree(
        self, tree_path: str, tree_path_stat: os.stat_result, follow_links: bool = False
    ):
        # the reason to have two functions instead of one purely recursive one is to use self.lstat_in_dir ie ls
        # which is much faster than individually stat-ing each file. Hence we have get_files_tree's special first lstat
        if stat.S_ISLNK(tree_path_stat.st_mode):
            if not follow_links:
                logging.warning(f"Ignoring symlink {tree_path}")
                return None
            logging.debug(f"Following symlink {tree_path}")
            try:
                tree_path_realpath = await self.realpath(tree_path)
                tree_path_stat_realpath = await self.lstat(tree_path_realpath)
            except (FileNotFoundError, NotADirectoryError, PermissionError) as e:
                perror(f"Skipping symlink {tree_path}", e)
                return None
            return await self._get_files_tree(
                tree_path_realpath, tree_path_stat_realpath, follow_links=follow_links
            )
        elif stat.S_ISDIR(tree_path_stat.st_mode):
            self.total_folders += 1
            tree = {
                ".": (
                    60 * (int(tree_path_stat.st_atime) // 60),
                    60 * (int(tree_path_stat.st_mtime) // 60),
                    0,
                )
            }
            for (
                filename,
                stat_object_child,
            ) in await self.lstat_in_dir(tree_path):
                if filename in [".", ".."]:
                    continue
                tree[filename] = await self._get_files_tree(
                    self.join(tree_path, filename),
                    stat_object_child,
                    follow_links=follow_links,
                )
            return tree
        elif stat.S_ISREG(tree_path_stat.st_mode):
            self.total_files += 1
            self.total_size += tree_path_stat.st_size
            self.counting_progress.update(
                self.counting_progress_id,
                description=f"[green]Folders:{self.total_folders} | [magenta]Files:{self.total_files} | [cyan]Size:{decimal(self.total_size, separator='')}",
            )
            return (
                60 * (int(tree_path_stat.st_atime) // 60),
                60 * (int(tree_path_stat.st_mtime) // 60),
                tree_path_stat.st_size,
            )  # minute resolution
        else:
            raise NotImplementedError

    async def get_files_tree(
        self, tree_path: str, follow_links: bool = False
    ) -> Union[TreeDict, FileInfo, None]:
        statObject = await self.lstat(tree_path)
        return await self._get_files_tree(
            tree_path, statObject, follow_links=follow_links
        )

    async def remove_tree(
        self, tree_path: str, tree: Union[FileInfo, TreeDict], dry_run: bool = True
    ) -> None:
        if isinstance(tree, tuple):
            logging.info(f"Removing {tree_path}")
            if not dry_run:
                await self.unlink(tree_path)
        elif isinstance(tree, dict):
            remove_folder = tree.pop(".", False)
            for key, value in tree.items():
                await self.remove_tree(
                    self.normpath(self.join(tree_path, key)), value, dry_run=dry_run
                )
            if remove_folder:
                logging.info(f"Removing folder {tree_path}")
                if not dry_run:
                    await self.rmdir(tree_path)
        else:
            raise NotImplementedError

    async def push_tree_here(
        self,
        tree_path: str,
        relative_tree_path: str,  # for logging paths of files / folders copied relative to the source root / destination root
        # nicely instead of repeating the root every time; rsync does this nice logging
        tree: Union[FileInfo, TreeDict],
        destination_root: str,
        fs_source: FileSystem,
        overall_progress_task_id: int,
        dry_run: bool = True,
        show_progress: bool = False,
        source_total_files=0,
        completed_files=0,
        transfers: int = 1,
    ) -> None:
        copy_jobs: List[Tuple[str, str, FileInfo]] = []
        folder_targets: set[str] = set()

        def collect_jobs(
            src_root: str, dst_root: str, node: Union[FileInfo, TreeDict]
        ) -> None:
            if isinstance(node, tuple):
                copy_jobs.append((src_root, dst_root, node))
                destination_parent, _ = self.split(dst_root)
                if destination_parent not in ("", "."):
                    folder_targets.add(destination_parent)
                return
            if not isinstance(node, dict):
                raise NotImplementedError

            has_dot = "." in node
            if has_dot:
                folder_targets.add(dst_root)
            for key, value in node.items():
                if key == ".":
                    continue
                collect_jobs(
                    fs_source.normpath(fs_source.join(src_root, key)),
                    self.normpath(self.join(dst_root, key)),
                    value,
                )

        collect_jobs(tree_path, destination_root, tree)
        if not dry_run:
            for folder_path in sorted(folder_targets):
                await self.makedirs(folder_path)

        semaphore = asyncio.Semaphore(max(1, transfers))
        update_lock = asyncio.Lock()
        active_transfers = 0
        total_files = source_total_files or len(copy_jobs)
        total_bytes = sum(info[2] for _, _, info in copy_jobs)
        started_at = time.monotonic()

        def _status_text() -> str:
            elapsed = max(0.001, time.monotonic() - started_at)
            pct_bytes = (
                0 if total_bytes == 0 else int((self.copied_size / total_bytes) * 100)
            )
            speed = self.copied_size / elapsed
            remaining = max(0, total_bytes - self.copied_size)
            eta = "-" if speed <= 0 else _fmt_duration(remaining / speed)
            pct_files = (
                0 if total_files == 0 else int((self.copied_files / total_files) * 100)
            )
            return "\n".join(
                [
                    f"[cyan]Transferred:[/cyan]      {_fmt_size_iec(self.copied_size)} / {_fmt_size_iec(total_bytes)}, {pct_bytes}%, {_fmt_size_iec(speed)}/s, ETA {eta}",
                    f"[cyan]Checks:[/cyan]                 {completed_files} / {completed_files}, -, Listed {total_files}",
                    f"[cyan]Transferred:[/cyan]           {self.copied_files} / {total_files}, {pct_files}%",
                    f"[cyan]Elapsed time:[/cyan]         {_fmt_duration(elapsed)}",
                    "[cyan]Transferring:[/cyan]",
                ]
            )

        async def run_one(source_path: str, dest_path: str, info: FileInfo) -> None:
            nonlocal active_transfers
            async with update_lock:
                active_transfers += 1
                overall_progress.update(
                    overall_progress_task_id,
                    status=_status_text(),
                    visible=show_progress,
                )
            file_task_id = copying_file_name_progress.add_task(
                f"[green]{truncate_path(dest_path,2)}[/green]",
                total=info[2],
                visible=show_progress,
            )
            # initialize the copied file name progress task, not visible yet
            copied_file_task_id = copied_file_name_progress.add_task(
                f"[bold green]{truncate_path(dest_path,2)}[/bold green] [bold red]{'(--dry-run)' if dry_run else ''}",
                total=info[2],
                visible=False,
            )
            # copied_file_task_id = None
            try:
                if not dry_run:
                    await self.push_file_here(
                        source_path,
                        dest_path,
                        file_task_id,
                        copied_file_task_id,
                        info[2],
                        overall_progress_task_id,
                    )
                    await self.utime(dest_path, (info[0], info[1]))
                copying_file_name_progress.update(
                    file_task_id,
                    description=f"[bold green]{truncate_path(dest_path,2)}[/bold green] [bold red]{'(--dry-run)' if dry_run else ''}",
                    completed=info[2],
                    visible=show_progress,
                )
                # now show the copied file name progress, visible now
                copied_file_name_progress._update(
                    copied_file_task_id,
                    description=f"[bold green]{truncate_path(dest_path,2)}[/bold green] [bold red]{'(--dry-run)' if dry_run else ''}",
                    completed=info[2],
                    visible=True,
                    # refresh=True,
                )

            except KeyboardInterrupt:
                await self.terminate_process(self.process)
                await asyncio.sleep(1)
                await self.unlink(dest_path)
                logging_fatal(f"Removing ongoing file: {dest_path}")
            finally:
                async with update_lock:
                    self.total_files += 1
                    self.copied_files += 1
                    self.total_size += info[2]
                    self.copied_size += info[2]
                    active_transfers -= 1
                    overall_progress.update(
                        overall_progress_task_id,
                        completed=self.copied_size,
                        status=_status_text(),
                        visible=show_progress,
                    )
                    self.counting_progress.update(
                        self.counting_progress_id,
                        description=f"[green]Folders:{self.total_folders} | [magenta]Files:{self.total_files} | [cyan]Size:{decimal(self.total_size, separator='')}",
                    )
                # now stop and remove the copying file name progress task
                copying_file_name_progress._stop_task(file_task_id)
                copying_file_name_progress._remove_task(file_task_id)

                # now stop and remove the copied file name progress task
                copied_file_name_progress._stop_task(copied_file_task_id)

                allowed_screen_height = copied_file_name_progress.console.height - 15
                if (
                    allowed_screen_height > 0
                    and len(copied_file_name_progress.task_ids) > allowed_screen_height
                ):
                    old_task_id = copied_file_name_progress.task_ids.pop(0)
                    copied_file_name_progress._remove_task(old_task_id)

        worker_count = max(1, transfers)
        queue: asyncio.Queue[Optional[Tuple[str, str, FileInfo]]] = asyncio.Queue()
        first_error: Optional[BaseException] = None
        first_error_lock = asyncio.Lock()

        for job in copy_jobs:
            queue.put_nowait(job)
        for _ in range(worker_count):
            queue.put_nowait(None)

        async def worker() -> None:
            nonlocal first_error
            while True:
                job = await queue.get()
                try:
                    if job is None:
                        return
                    if first_error is not None:
                        continue
                    source_path, dest_path, info = job
                    async with semaphore:
                        await run_one(source_path, dest_path, info)
                except BaseException as exc:
                    async with first_error_lock:
                        if first_error is None:
                            first_error = exc
                finally:
                    queue.task_done()

        workers = [asyncio.create_task(worker()) for _ in range(worker_count)]
        await queue.join()
        for task in workers:
            await task

        if first_error is not None:
            raise first_error

    # Abstract methods below implemented in Local.py and Android.py

    @property
    def sep(self) -> str:
        raise NotImplementedError

    async def unlink(self, path: str) -> None:
        raise NotImplementedError

    async def rmdir(self, path: str) -> None:
        raise NotImplementedError

    async def makedirs(self, path: str) -> None:
        raise NotImplementedError

    async def realpath(self, path: str) -> str:
        raise NotImplementedError

    async def lstat(self, path: str) -> os.stat_result:
        raise NotImplementedError

    async def lstat_in_dir(self, path: str) -> Iterable[Tuple[str, os.stat_result]]:
        raise NotImplementedError

    async def utime(self, path: str, times: Tuple[int, int]) -> None:
        raise NotImplementedError

    def join(self, base: str, leaf: str) -> str:
        raise NotImplementedError

    def split(self, path: str) -> Tuple[str, str]:
        raise NotImplementedError

    def normpath(self, path: str) -> str:
        raise NotImplementedError

    async def exists(self, path: str) -> bool:
        raise NotImplementedError

    async def push_file_here(
        self,
        source: str,
        destination: str,
        file_task_id: int,
        copied_file_task_id: int,
        cur_file_size: int,
        overall_progress_task_id: int,
    ) -> None:
        raise NotImplementedError

    async def terminate_process(self, process) -> None:
        if process is None:
            return
        try:
            if getattr(process, "returncode", None) is None:
                process.terminate()
                await asyncio.sleep(0.2)
            if getattr(process, "returncode", None) is None:
                process.kill()
            await process.wait()
        except Exception:
            pass
