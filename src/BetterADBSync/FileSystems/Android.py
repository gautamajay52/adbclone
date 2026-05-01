import asyncio
import contextlib
import datetime
import logging
import os
import re
import shlex
import stat
from typing import Iterable, List, NoReturn, Optional, Tuple

from ..SAOLogging import (
    copied_file_name_progress,
    copying_file_name_progress,
    logging_fatal,
    overall_progress,
)
from .Base import FileSystem


class AndroidFileSystem(FileSystem):
    RE_TESTCONNECTION_NO_DEVICE = re.compile("^adb\\: no devices/emulators found$")
    RE_TESTCONNECTION_DAEMON_NOT_RUNNING = re.compile(
        "^\\* daemon not running; starting now at tcp:\\d+$"
    )
    RE_TESTCONNECTION_DAEMON_STARTED = re.compile("^\\* daemon started successfully$")

    RE_LS_TO_STAT = re.compile(
        r"""^
        (?:
        (?P<S_IFREG> -) |
        (?P<S_IFBLK> b) |
        (?P<S_IFCHR> c) |
        (?P<S_IFDIR> d) |
        (?P<S_IFLNK> l) |
        (?P<S_IFIFO> p) |
        (?P<S_IFSOCK> s))
        [-r][-w][-xsS]
        [-r][-w][-xsS]
        [-r][-w][-xtT] # Mode string
        [ ]+
        (?:
        [0-9]+ # Number of hard links
        [ ]+
        )?
        [^ ]+ # User name/ID
        [ ]+
        [^ ]+ # Group name/ID
        [ ]+
        (?(S_IFBLK) [^ ]+[ ]+[^ ]+[ ]+) # Device numbers
        (?(S_IFCHR) [^ ]+[ ]+[^ ]+[ ]+) # Device numbers
        (?(S_IFDIR) (?P<dirsize>[0-9]+ [ ]+))? # Directory size
        (?(S_IFREG) (?P<st_size> [0-9]+) [ ]+) # Size
        (?(S_IFLNK) ([0-9]+) [ ]+) # Link length
        (?P<st_mtime>
        [0-9]{4}-[0-9]{2}-[0-9]{2} # Date
        [ ]
        [0-9]{2}:[0-9]{2}) # Time
        [ ]
        # Don't capture filename for symlinks (ambiguous).
        (?(S_IFLNK) .* | (?P<filename> .*))
        $""",
        re.DOTALL | re.VERBOSE,
    )

    RE_NO_SUCH_FILE = re.compile("^.*: No such file or directory$")
    RE_LS_NOT_A_DIRECTORY = re.compile("ls: .*: Not a directory$")
    RE_TOTAL = re.compile("^total \\d+$")

    RE_REALPATH_NO_SUCH_FILE = re.compile("^realpath: .*: No such file or directory$")
    RE_REALPATH_NOT_A_DIRECTORY = re.compile("^realpath: .*: Not a directory$")

    ADBSYNC_END_OF_COMMAND = "ADBSYNC END OF COMMAND"

    def __init__(self, adb_arguments: List[str], adb_encoding: str) -> None:
        super().__init__(adb_arguments)
        self.adb_encoding = adb_encoding
        self.process = None

    def __del__(self):
        return

    async def adb_shell(self, commands: List[str]) -> List[str]:
        proc = await asyncio.create_subprocess_exec(
            *self.adb_arguments,
            "shell",
            shlex.join(commands),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        self.process = proc
        try:
            stdout, _ = await proc.communicate()
        except BaseException:
            await self.terminate_process(proc)
            raise
        output = stdout.decode(self.adb_encoding, errors="replace")
        return [line.rstrip("\r\n") for line in output.splitlines()]

    def line_not_captured(self, line: str) -> NoReturn:
        logging.critical("ADB line not captured")
        logging_fatal(line)

    async def test_connection(self) -> None:
        for line in await self.adb_shell([":"]):
            print(line)

            if self.RE_TESTCONNECTION_DAEMON_NOT_RUNNING.fullmatch(
                line
            ) or self.RE_TESTCONNECTION_DAEMON_STARTED.fullmatch(line):
                continue

            raise BrokenPipeError

    def ls_to_stat(self, line: str) -> Tuple[str, os.stat_result]:
        if self.RE_NO_SUCH_FILE.fullmatch(line):
            raise FileNotFoundError
        elif self.RE_LS_NOT_A_DIRECTORY.fullmatch(line):
            raise NotADirectoryError
        elif match := self.RE_LS_TO_STAT.fullmatch(line):
            match_groupdict = match.groupdict()
            st_mode = (
                stat.S_IRWXU | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH
            )  # 755
            if match_groupdict["S_IFREG"]:
                st_mode |= stat.S_IFREG
            if match_groupdict["S_IFBLK"]:
                st_mode |= stat.S_IFBLK
            if match_groupdict["S_IFCHR"]:
                st_mode |= stat.S_IFCHR
            if match_groupdict["S_IFDIR"]:
                st_mode |= stat.S_IFDIR
            if match_groupdict["S_IFIFO"]:
                st_mode |= stat.S_IFIFO
            if match_groupdict["S_IFLNK"]:
                st_mode |= stat.S_IFLNK
            if match_groupdict["S_IFSOCK"]:
                st_mode |= stat.S_IFSOCK
            st_size = (
                None
                if match_groupdict["st_size"] is None
                else int(match_groupdict["st_size"])
            )
            st_mtime = int(
                datetime.datetime.strptime(
                    match_groupdict["st_mtime"], "%Y-%m-%d %H:%M"
                ).timestamp()
            )

            # Fill the rest with dummy values.
            st_ino = 1
            st_rdev = 0
            st_nlink = 1
            st_uid = -2  # Nobody.
            st_gid = -2  # Nobody.
            st_atime = st_ctime = st_mtime

            return match_groupdict["filename"], os.stat_result(
                (
                    st_mode,
                    st_ino,
                    st_rdev,
                    st_nlink,
                    st_uid,
                    st_gid,
                    st_size,
                    st_atime,
                    st_mtime,
                    st_ctime,
                )
            )
        else:
            self.line_not_captured(line)

    @property
    def sep(self) -> str:
        return "/"

    async def _unlink(self, path: str) -> None:
        for line in await self.adb_shell(["rm", path]):
            self.line_not_captured(line)

    async def run(self, command: List[str]) -> Optional[str]:
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0:
            return None
        return stdout.decode(errors="replace").strip()

    async def exists(self, path: str) -> bool:
        try:
            await self.lstat(path)
            return True
        except (FileNotFoundError, NotADirectoryError, PermissionError, OSError):
            return False

    async def unlink(self, path: str) -> None:
        if await self.exists(path):
            await self._unlink(path)

    async def rmdir(self, path: str) -> None:
        if await self.exists(path):
            await self._rmdir(path)

    async def _rmdir(self, path: str) -> None:
        for line in await self.adb_shell(["rm", "-r", path]):
            self.line_not_captured(line)

    async def makedirs(self, path: str) -> None:
        for line in await self.adb_shell(["mkdir", "-p", path]):
            self.line_not_captured(line)

    async def realpath(self, path: str) -> str:
        for line in await self.adb_shell(["realpath", path]):
            if self.RE_REALPATH_NO_SUCH_FILE.fullmatch(line):
                raise FileNotFoundError
            elif self.RE_REALPATH_NOT_A_DIRECTORY.fullmatch(line):
                raise NotADirectoryError
            else:
                return line
            # permission error possible?

    async def lstat(self, path: str) -> os.stat_result:
        for line in await self.adb_shell(["ls", "-lad", path]):
            return self.ls_to_stat(line)[1]
        raise FileNotFoundError(path)

    async def lstat_in_dir(self, path: str) -> Iterable[Tuple[str, os.stat_result]]:
        entries: List[Tuple[str, os.stat_result]] = []
        for line in await self.adb_shell(["ls", "-la", path]):
            if self.RE_TOTAL.fullmatch(line):
                continue
            else:
                entries.append(self.ls_to_stat(line))
        return entries

    async def utime(self, path: str, times: Tuple[int, int]) -> None:
        atime = datetime.datetime.fromtimestamp(times[0]).strftime("%Y%m%d%H%M")
        mtime = datetime.datetime.fromtimestamp(times[1]).strftime("%Y%m%d%H%M")
        for line in await self.adb_shell(["touch", "-at", atime, "-mt", mtime, path]):
            self.line_not_captured(line)

    def join(self, base: str, leaf: str) -> str:
        return os.path.join(base, leaf).replace("\\", "/")  # for Windows

    def split(self, path: str) -> Tuple[str, str]:
        head, tail = os.path.split(path)
        return head.replace("\\", "/"), tail  # for Windows

    def normpath(self, path: str) -> str:
        return os.path.normpath(path).replace("\\", "/")

    async def push_file_here(
        self,
        source_path: str,
        destination_path: str,
        file_task_id: int,
        copied_file_task_id: int,
        cur_file_size: int,
        overall_progress_task_id: int,
    ) -> None:
        adb_process = await asyncio.create_subprocess_exec(
            *self.adb_arguments,
            "push",
            source_path,
            destination_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        self.process = adb_process
        try:
            old_file_size = 0

            if cur_file_size > 30 * 1024 * 1024:
                while adb_process.returncode is None:
                    # with contextlib.suppress(asyncio.TimeoutError):
                    #     await asyncio.wait_for(adb_process.wait(), timeout=0.0)

                    try:
                        current_file_size = (await self.lstat(destination_path)).st_size
                    except (
                        FileNotFoundError,
                        NotADirectoryError,
                        PermissionError,
                    ) as e:
                        copied_file_name_progress.console.print(
                            f"File not found: {destination_path} {e}"
                        )
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
