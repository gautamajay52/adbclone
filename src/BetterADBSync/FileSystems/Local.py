import os
import subprocess
import time
from typing import Iterable, Tuple

from ..SAOLogging import file_name_progress, logging_fatal, overall_progress
from .Base import FileSystem


class LocalFileSystem(FileSystem):
    @property
    def sep(self) -> str:
        return os.path.sep

    def unlink(self, path: str) -> None:
        if os.path.exists(path):
            os.remove(path)

    def rmdir(self, path: str) -> None:
        if os.path.exists(path):
            os.rmdir(path)

    def makedirs(self, path: str) -> None:
        os.makedirs(path, exist_ok=True)

    def realpath(self, path: str) -> str:
        return os.path.realpath(path)

    def lstat(self, path: str) -> os.stat_result:
        return os.lstat(path)

    def lstat_in_dir(self, path: str) -> Iterable[Tuple[str, os.stat_result]]:
        for filename in os.listdir(path):
            yield filename, self.lstat(self.join(path, filename))

    def utime(self, path: str, times: Tuple[int, int]) -> None:
        os.utime(path, times)

    def join(self, base: str, leaf: str) -> str:
        return os.path.join(base, leaf)

    def split(self, path: str) -> Tuple[str, str]:
        return os.path.split(path)

    def normpath(self, path: str) -> str:
        return os.path.normpath(path)

    def exists(self, path: str) -> bool:
        return os.path.exists(path)

    def push_file_here(
        self, source_path, destination_path, file_task_id, cur_file_size
    ):
        os.makedirs(os.path.dirname(destination_path), exist_ok=True)
        adb_process = subprocess.Popen(
            self.adb_arguments + ["pull", source_path, destination_path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.process = adb_process
        old_file_size = 0
        file_exists = False
        if cur_file_size > 30 * 1024 * 1024:
            time.sleep(1)
            while adb_process.poll() is None:
                if not file_exists:
                    file_exists = self.exists(destination_path)
                    continue

                current_file_size = self.lstat(
                    destination_path
                ).st_size  # expensive much?
                file_name_progress.update(file_task_id, completed=current_file_size)
                overall_progress.update(
                    overall_progress.task_ids.pop(0),
                    advance=current_file_size - old_file_size,
                )
                old_file_size = current_file_size
                time.sleep(0.5)  # increase?
        else:
            adb_process.wait()

    def _push_file_here(
        self, source: str, destination: str, show_progress: bool = False
    ) -> None:
        if show_progress:
            kwargs_call = {}
        else:
            kwargs_call = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
        if subprocess.call(
            self.adb_arguments + ["pull", source, destination], **kwargs_call
        ):
            logging_fatal("Non-zero exit code from adb pull")
