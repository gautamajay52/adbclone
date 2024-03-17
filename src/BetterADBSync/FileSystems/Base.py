from __future__ import annotations

import logging
import os
import stat
import time
from typing import Iterable, List, Tuple, Union

from rich.filesize import decimal
from rich.progress import Progress

from ..SAOLogging import (
    file_name_progress,
    logging_fatal,
    overall_progress,
    perror,
    truncate_path,
)


class FileSystem:
    def __init__(self, adb_arguments: List[str]) -> None:
        self.adb_arguments = adb_arguments
        self.total_files = 0
        self.total_size = 0
        self.counting_progress: Progress = None
        self.counting_progress_id = 0
        self.total_folders = 0

        self.copied_files = 0
        self.copied_size = 0

    def _get_files_tree(
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
                tree_path_realpath = self.realpath(tree_path)
                tree_path_stat_realpath = self.lstat(tree_path_realpath)
            except (FileNotFoundError, NotADirectoryError, PermissionError) as e:
                perror(f"Skipping symlink {tree_path}", e)
                return None
            return self._get_files_tree(
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
            ) in self.lstat_in_dir(tree_path):
                if filename in [".", ".."]:
                    continue
                tree[filename] = self._get_files_tree(
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

    def get_files_tree(self, tree_path: str, follow_links: bool = False):
        statObject = self.lstat(tree_path)
        return self._get_files_tree(tree_path, statObject, follow_links=follow_links)

    def remove_tree(
        self, tree_path: str, tree: Union[Tuple[int, int], dict], dry_run: bool = True
    ) -> None:
        if isinstance(tree, tuple):
            logging.info(f"Removing {tree_path}")
            if not dry_run:
                self.unlink(tree_path)
        elif isinstance(tree, dict):
            remove_folder = tree.pop(".", False)
            for key, value in tree.items():
                self.remove_tree(
                    self.normpath(self.join(tree_path, key)), value, dry_run=dry_run
                )
            if remove_folder:
                logging.info(f"Removing folder {tree_path}")
                if not dry_run:
                    self.rmdir(tree_path)
        else:
            raise NotImplementedError

    def push_tree_here(
        self,
        tree_path: str,
        relative_tree_path: str,  # for logging paths of files / folders copied relative to the source root / destination root
        # nicely instead of repeating the root every time; rsync does this nice logging
        tree: Union[Tuple[int, int], dict],
        destination_root: str,
        fs_source: FileSystem,
        dry_run: bool = True,
        show_progress: bool = False,
        source_total_files=0,
    ) -> None:
        if isinstance(tree, tuple):
            file_task_id = file_name_progress.add_task(
                f"[green]{truncate_path(destination_root,2)}[/green] [blue]",
                total=tree[2],
                visible=show_progress,
            )
            if not dry_run:
                try:
                    self.push_file_here(
                        tree_path, destination_root, file_task_id, tree[2]
                    )
                    self.utime(destination_root, tuple(list(tree)[:-1]))
                except KeyboardInterrupt as e:
                    self.process.kill()
                    time.sleep(1)
                    self.unlink(destination_root)
                    logging_fatal(f"Removing ongoing file: {destination_root}")

            self.total_files += 1
            self.copied_files += 1
            self.total_size += tree[2]
            self.copied_size += tree[2]
            fields = f"[{self.copied_files}/{source_total_files}]"
            overall_progress.update(
                overall_progress.task_ids.pop(0),
                completed=self.copied_size,
                fields=fields,
                visible=show_progress,
            )

            # file_name_progress.columns[2].bar_width = 0 # hide the bar??

            file_name_progress.update(
                file_task_id,
                description=f"[bold green]{truncate_path(destination_root,2)}[/bold green] [bold red]{'(--dry-run)' if dry_run else ''}",
                completed=tree[2],
                visible=show_progress,
            )
            self.counting_progress.update(
                self.counting_progress_id,
                description=f"[green]Folders:{self.total_folders} | [magenta]Files:{self.total_files} | [cyan]Size:{decimal(self.total_size, separator='')}",
            )

            file_name_progress.stop_task(file_task_id)

            if (
                len(file_name_progress.task_ids)
                > file_name_progress.console.height - 10
            ):
                file_task_id = file_name_progress.task_ids.pop(0)
                file_name_progress.remove_task(file_task_id)

        elif isinstance(tree, dict):
            try:
                tree.pop(".")  # directory needs making
                if not dry_run:
                    self.makedirs(destination_root)
                self.total_folders += 1
            except KeyError:
                pass
            for key, value in tree.items():
                self.push_tree_here(
                    fs_source.normpath(fs_source.join(tree_path, key)),
                    fs_source.join(relative_tree_path, key),
                    value,
                    self.normpath(self.join(destination_root, key)),
                    fs_source,
                    dry_run=dry_run,
                    show_progress=show_progress,
                    source_total_files=source_total_files,
                )
        else:
            raise NotImplementedError

    # Abstract methods below implemented in Local.py and Android.py

    @property
    def sep(self) -> str:
        raise NotImplementedError

    def unlink(self, path: str) -> None:
        raise NotImplementedError

    def rmdir(self, path: str) -> None:
        raise NotImplementedError

    def makedirs(self, path: str) -> None:
        raise NotImplementedError

    def realpath(self, path: str) -> str:
        raise NotImplementedError

    def lstat(self, path: str) -> os.stat_result:
        raise NotImplementedError

    def lstat_in_dir(self, path: str) -> Iterable[Tuple[str, os.stat_result]]:
        raise NotImplementedError

    def utime(self, path: str, times: Tuple[int, int]) -> None:
        raise NotImplementedError

    def join(self, base: str, leaf: str) -> str:
        raise NotImplementedError

    def split(self, path: str) -> Tuple[str, str]:
        raise NotImplementedError

    def normpath(self, path: str) -> str:
        raise NotImplementedError

    def push_file_here(
        self, source: str, params, destination: str, show_progress: bool = False
    ) -> None:
        raise NotImplementedError
