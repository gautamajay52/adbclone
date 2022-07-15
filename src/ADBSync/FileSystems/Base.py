from __future__ import annotations
from typing import Iterable, Tuple, Union
import logging
import os
import stat

class FileSystem():
    def _getFilesTree(self, tree_path: str, tree_path_stat: os.stat_result, followLinks: bool = False):
        # the reason to have two functions instead of one purely recursive one is to use self.lstat_inDir ie ls
        # which is much faster than individually stat-ing each file. Hence we have getFilesTree's special first lstat
        if stat.S_ISLNK(tree_path_stat.st_mode):
            if not followLinks:
                logging.warning(f"Ignoring symlink {tree_path}")
                return None
            logging.debug(f"Following symlink {tree_path}")
            try:
                tree_path_realPath = self.realPath(tree_path)
                tree_path_stat_realPath = self.lstat(tree_path_realPath)
            except (FileNotFoundError, NotADirectoryError, PermissionError) as e:
                logging.error(f"Skipping symlink {tree_path}: {e.strerror}")
                return None
            return self._getFilesTree(tree_path_realPath, tree_path_stat_realPath, followLinks = followLinks)
        elif stat.S_ISDIR(tree_path_stat.st_mode):
            tree = {".": (60 * (int(tree_path_stat.st_atime) // 60), 60 * (int(tree_path_stat.st_mtime) // 60))}
            for filename, statObject_child, in self.lstat_inDir(tree_path):
                if filename in [".", ".."]:
                    continue
                tree[filename] = self._getFilesTree(
                    self.joinPaths(tree_path, filename),
                    statObject_child,
                    followLinks = followLinks)
            return tree
        elif stat.S_ISREG(tree_path_stat.st_mode):
            return (60 * (int(tree_path_stat.st_atime) // 60), 60 * (int(tree_path_stat.st_mtime) // 60))
        else:
            raise NotImplementedError

    def getFilesTree(self, tree_path: str, followLinks: bool = False):
        statObject = self.lstat(tree_path)
        return self._getFilesTree(tree_path, statObject, followLinks = followLinks)

    def removeTree(self, tree_path: str, tree: Union[Tuple[int, int], dict], dryRun: bool = True) -> None:
        if isinstance(tree, tuple):
            logging.info(f"Removing {tree_path}")
            if not dryRun:
                self.unlink(tree_path)
        elif isinstance(tree, dict):
            removeFolder = tree.pop(".", False)
            for key, value in tree.items():
                self.removeTree(self.normPath(self.joinPaths(tree_path, key)), value, dryRun = dryRun)
            if removeFolder:
                logging.info(f"Removing folder {tree_path}")
                if not dryRun:
                    self.rmdir(tree_path)
        else:
            raise NotImplementedError

    def pushTreeHere(self,
        tree_path: str,
        relative_tree_path: str, # for logging paths of files / folders copied relative to the source root / destination root
                                 # nicely instead of repeating the root every time; rsync does this nice logging
        tree: Union[Tuple[int, int], dict],
        destination_root: str,
        fs_source: FileSystem,
        dryRun: bool = True,
        showProgress: bool = False
        ) -> None:
        if isinstance(tree, tuple):
            if dryRun:
                logging.info(f"{relative_tree_path}")
            else:
                if not showProgress:
                    # log this instead of letting adb display output
                    logging.info(f"{relative_tree_path}")
                self.pushFileHere(tree_path, destination_root, showProgress = showProgress)
                self.utime(destination_root, tree)
        elif isinstance(tree, dict):
            try:
                tree.pop(".") # directory needs making
                logging.info(f"{relative_tree_path}{self.sep}")
                if not dryRun:
                    self.makedirs(destination_root)
            except KeyError:
                pass
            for key, value in tree.items():
                self.pushTreeHere(
                    fs_source.normPath(fs_source.joinPaths(tree_path, key)),
                    fs_source.joinPaths(relative_tree_path, key),
                    value,
                    self.normPath(self.joinPaths(destination_root, key)),
                    fs_source,
                    dryRun = dryRun,
                    showProgress = showProgress
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

    def realPath(self, path: str) -> str:
        raise NotImplementedError

    def lstat(self, path: str) -> os.stat_result:
        raise NotImplementedError

    def lstat_inDir(self, path: str) -> Iterable[Tuple[str, os.stat_result]]:
        raise NotImplementedError

    def utime(self, path: str, times: Tuple[int, int]) -> None:
        raise NotImplementedError

    def joinPaths(self, base: str, leaf: str) -> str:
        raise NotImplementedError

    def path_split(self, path: str) -> Tuple[str, str]:
        raise NotImplementedError

    def normPath(self, path: str) -> str:
        raise NotImplementedError

    def pushFileHere(self, source: str, destination: str, showProgress: bool = False) -> None:
        raise NotImplementedError
