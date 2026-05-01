import asyncio
import contextlib
import os
from typing import Iterable, Tuple

from ..SAOLogging import (
    copied_file_name_progress,
    copying_file_name_progress,
    overall_progress,
)
from .Base import FileSystem


class LocalFileSystem(FileSystem):
    @property
    def sep(self) -> str:
        return os.path.sep

    async def unlink(self, path: str) -> None:
        if os.path.exists(path):
            os.remove(path)

    async def rmdir(self, path: str) -> None:
        if os.path.exists(path):
            os.rmdir(path)

    async def makedirs(self, path: str) -> None:
        os.makedirs(path, exist_ok=True)

    async def realpath(self, path: str) -> str:
        return os.path.realpath(path)

    async def lstat(self, path: str) -> os.stat_result:
        return os.lstat(path)

    async def lstat_in_dir(self, path: str) -> Iterable[Tuple[str, os.stat_result]]:
        entries = []
        for filename in os.listdir(path):
            entries.append((filename, await self.lstat(self.join(path, filename))))
        return entries

    async def utime(self, path: str, times: Tuple[int, int]) -> None:
        os.utime(path, times)

    def join(self, base: str, leaf: str) -> str:
        return os.path.join(base, leaf)

    def split(self, path: str) -> Tuple[str, str]:
        return os.path.split(path)

    def normpath(self, path: str) -> str:
        return os.path.normpath(path)

    async def exists(self, path: str) -> bool:
        return os.path.exists(path)

    async def push_file_here(
        self,
        source_path: str,
        destination_path: str,
        file_task_id: int,
        copied_file_task_id: int,
        cur_file_size: int,
        overall_progress_task_id: int,
    ) -> None:
        destination_dir = os.path.dirname(destination_path)
        if destination_dir:
            os.makedirs(destination_dir, exist_ok=True)
        adb_process = await asyncio.create_subprocess_exec(
            *self.adb_arguments,
            "pull",
            source_path,
            destination_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self.process = adb_process
        try:
            old_file_size = 0
            file_exists = False
            if cur_file_size > 30 * 1024 * 1024:
                while adb_process.returncode is None:
                    # with contextlib.suppress(asyncio.TimeoutError):
                    #     await asyncio.wait_for(adb_process.wait(), timeout=0.0)

                    if not file_exists:
                        file_exists = await self.exists(destination_path)
                        await asyncio.sleep(0.2)
                        continue

                    try:
                        current_file_size = (await self.lstat(destination_path)).st_size
                    except FileNotFoundError:
                        await asyncio.sleep(0.5)
                        continue
                    if current_file_size is None or current_file_size < old_file_size:
                        await asyncio.sleep(0.5)
                        continue
                    copying_file_name_progress._update(
                        file_task_id, completed=current_file_size
                    )
                    copied_file_name_progress._update(
                        copied_file_task_id, completed=current_file_size
                    )
                    overall_progress.update(
                        overall_progress_task_id,
                        advance=current_file_size - old_file_size,
                    )
                    old_file_size = current_file_size
                    await asyncio.sleep(1)  # increase?
                await adb_process.wait()
            else:
                await adb_process.wait()
        except BaseException:
            await self.terminate_process(adb_process)
            with contextlib.suppress(Exception):
                await self.unlink(destination_path)
            raise
        finally:
            await self.terminate_process(adb_process)
