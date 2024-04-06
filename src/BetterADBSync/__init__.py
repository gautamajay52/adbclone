#!/usr/bin/env python3

"""Sync files between a computer and an Android device"""

__version__ = "0.0.4"

import fnmatch
import logging
import os
import stat
import time
from collections import deque
from datetime import datetime
from typing import List, Tuple, Union

from rich import print
from rich.text import Text
from rich.tree import Tree

from .argparsing import get_cli_args
from .FileSystems.Android import AndroidFileSystem
from .FileSystems.Base import FileSystem
from .FileSystems.Local import LocalFileSystem
from .SAOLogging import (
    FATAL,
    destination_counting_progress,
    live,
    log_tree,
    logging_fatal,
    overall_progress,
    perror,
    setup_root_logger,
    source_counting_progress,
    truncate_path,
)


class FileSyncer:
    @classmethod
    def diff_trees(
        cls,
        source: Union[dict, Tuple[int, int], None],
        destination: Union[dict, Tuple[int, int], None],
        path_source: str,
        path_destination: str,
        destination_exclude_patterns: List[str],
        path_join_function_source,
        path_join_function_destination,
        folder_file_overwrite_error: bool = True,
    ) -> Tuple[
        Union[dict, Tuple[int, int], None],  # delete
        Union[dict, Tuple[int, int], None],  # copy
        Union[dict, Tuple[int, int], None],  # excluded_source
        Union[dict, Tuple[int, int], None],  # unaccounted_destination
        Union[dict, Tuple[int, int], None],  # excluded_destination
    ]:

        exclude = False
        for destination_exclude_pattern in destination_exclude_patterns:
            if fnmatch.fnmatch(path_destination, destination_exclude_pattern):
                exclude = True
                break

        if source is None:
            if destination is None:
                delete = None
                copy = None
                excluded_source = None
                unaccounted_destination = None
                excluded_destination = None
            elif isinstance(destination, tuple):
                if exclude:
                    delete = None
                    copy = None
                    excluded_source = None
                    unaccounted_destination = None
                    excluded_destination = destination
                else:
                    delete = None
                    copy = None
                    excluded_source = None
                    unaccounted_destination = destination
                    excluded_destination = None
            elif isinstance(destination, dict):
                if exclude:
                    delete = {".": None}
                    copy = None
                    excluded_source = None
                    unaccounted_destination = {".": None}
                    excluded_destination = destination
                else:
                    delete = {".": None}
                    copy = None
                    excluded_source = None
                    unaccounted_destination = {".": destination["."]}
                    excluded_destination = {".": None}
                    destination.pop(".")
                    for key, value in destination.items():
                        (
                            delete[key],
                            _,
                            _,
                            unaccounted_destination[key],
                            excluded_destination[key],
                        ) = cls.diff_trees(
                            None,
                            value,
                            path_join_function_source(path_source, key),
                            path_join_function_destination(path_destination, key),
                            destination_exclude_patterns,
                            path_join_function_source,
                            path_join_function_destination,
                            folder_file_overwrite_error=folder_file_overwrite_error,
                        )
            else:
                raise NotImplementedError

        elif isinstance(source, tuple):
            if destination is None:
                if exclude:
                    delete = None
                    copy = None
                    excluded_source = source
                    unaccounted_destination = None
                    excluded_destination = None
                else:
                    delete = None
                    copy = source
                    excluded_source = None
                    unaccounted_destination = None
                    excluded_destination = None
            elif isinstance(destination, tuple):
                if exclude:
                    delete = None
                    copy = None
                    excluded_source = source
                    unaccounted_destination = None
                    excluded_destination = destination
                else:
                    if source[1] > destination[1]:
                        delete = destination
                        copy = source
                        excluded_source = None
                        unaccounted_destination = None
                        excluded_destination = None
                    elif source[2] != destination[2]:  # delete if size mismatch?
                        delete = destination
                        copy = source
                        excluded_source = None
                        unaccounted_destination = None
                        excluded_destination = None
                    else:
                        delete = None
                        copy = None
                        excluded_source = None
                        unaccounted_destination = None
                        excluded_destination = None
            elif isinstance(destination, dict):
                if exclude:
                    delete = {".": None}
                    copy = None
                    excluded_source = source
                    unaccounted_destination = {".": None}
                    excluded_destination = destination
                else:
                    delete = destination
                    copy = source
                    excluded_source = None
                    unaccounted_destination = {".": None}
                    excluded_destination = {".": None}
                    if folder_file_overwrite_error:
                        logging.critical(
                            f"Refusing to overwrite directory {path_destination} with file {path_source}"
                        )
                        logging_fatal("Use --force if you are sure!")
                    else:
                        logging.warning(
                            f"Overwriting directory {path_destination} with file {path_source}"
                        )
            else:
                raise NotImplementedError

        elif isinstance(source, dict):
            if destination is None:
                if exclude:
                    delete = None
                    copy = {".": None}
                    excluded_source = source
                    unaccounted_destination = None
                    excluded_destination = None
                else:
                    delete = None
                    copy = {".": source["."]}
                    excluded_source = {".": None}
                    unaccounted_destination = None
                    excluded_destination = None
                    source.pop(".")
                    for key, value in source.items():
                        _, copy[key], excluded_source[key], _, _ = cls.diff_trees(
                            value,
                            None,
                            path_join_function_source(path_source, key),
                            path_join_function_destination(path_destination, key),
                            destination_exclude_patterns,
                            path_join_function_source,
                            path_join_function_destination,
                            folder_file_overwrite_error=folder_file_overwrite_error,
                        )
            elif isinstance(destination, tuple):
                if exclude:
                    delete = None
                    copy = {".": None}
                    excluded_source = source
                    unaccounted_destination = None
                    excluded_destination = destination
                else:
                    delete = destination
                    copy = {".": source["."]}
                    excluded_source = {".": None}
                    unaccounted_destination = None
                    excluded_destination = None
                    source.pop(".")
                    for key, value in source.items():
                        _, copy[key], excluded_source[key], _, _ = cls.diff_trees(
                            value,
                            None,
                            path_join_function_source(path_source, key),
                            path_join_function_destination(path_destination, key),
                            destination_exclude_patterns,
                            path_join_function_source,
                            path_join_function_destination,
                            folder_file_overwrite_error=folder_file_overwrite_error,
                        )
                    if folder_file_overwrite_error:
                        logging.critical(
                            f"Refusing to overwrite file {path_destination} with directory {path_source}"
                        )
                        logging_fatal("Use --force if you are sure!")
                    else:
                        logging.warning(
                            f"Overwriting file {path_destination} with directory {path_source}"
                        )
                excluded_destination = None
            elif isinstance(destination, dict):
                if exclude:
                    delete = {".": None}
                    copy = {".": None}
                    excluded_source = source
                    unaccounted_destination = {".": None}
                    excluded_destination = destination
                else:
                    delete = {".": None}
                    copy = {".": None}
                    excluded_source = {".": None}
                    unaccounted_destination = {".": None}
                    excluded_destination = {".": None}
                    source.pop(".")
                    for key, value in source.items():
                        (
                            delete[key],
                            copy[key],
                            excluded_source[key],
                            unaccounted_destination[key],
                            excluded_destination[key],
                        ) = cls.diff_trees(
                            value,
                            destination.pop(key, None),
                            path_join_function_source(path_source, key),
                            path_join_function_destination(path_destination, key),
                            destination_exclude_patterns,
                            path_join_function_source,
                            path_join_function_destination,
                            folder_file_overwrite_error=folder_file_overwrite_error,
                        )
                    destination.pop(".")
                    for key, value in destination.items():
                        (
                            delete[key],
                            _,
                            _,
                            unaccounted_destination[key],
                            excluded_destination[key],
                        ) = cls.diff_trees(
                            None,
                            value,
                            path_join_function_source(path_source, key),
                            path_join_function_destination(path_destination, key),
                            destination_exclude_patterns,
                            path_join_function_source,
                            path_join_function_destination,
                            folder_file_overwrite_error=folder_file_overwrite_error,
                        )
            else:
                raise NotImplementedError

        else:
            raise NotImplementedError

        return (
            delete,
            copy,
            excluded_source,
            unaccounted_destination,
            excluded_destination,
        )

    @classmethod
    def remove_excluded_folders_from_unaccounted_tree(
        cls, unaccounted: Union[dict, Tuple[int, int]], excluded: Union[dict, None]
    ) -> dict:
        # For when we have --del but not --delete-excluded selected; we do not want to delete unaccounted folders that are the
        # parent of excluded items. At the point in the program that this function is called at either
        # 1) unaccounted is a tuple (file) and excluded is None
        # 2) unaccounted is a dict and excluded is a dict or None
        # trees passed to this function are already pruned; empty dictionary (sub)trees don't exist
        if excluded is None:
            return unaccounted
        else:
            unaccounted_non_excluded = {}
            for unaccounted_key, unaccounted_value in unaccounted.items():
                if unaccounted_key == ".":
                    continue
                unaccounted_non_excluded[unaccounted_key] = (
                    cls.remove_excluded_folders_from_unaccounted_tree(
                        unaccounted_value, excluded.get(unaccounted_key, None)
                    )
                )
            return unaccounted_non_excluded

    @classmethod
    def prune_tree(cls, tree):
        """Remove all Nones from a tree. May return None if tree is None however."""
        if not isinstance(tree, dict):
            return tree
        else:
            return_dict = {}
            for key, value in tree.items():
                value_pruned = cls.prune_tree(value)
                if value_pruned is not None:
                    return_dict[key] = value_pruned
            return return_dict or None

    @classmethod
    def sort_tree(cls, tree):
        if not isinstance(tree, dict):
            return tree
        return {k: cls.sort_tree(v) for k, v in sorted(tree.items())}

    @classmethod
    def paths_to_fixed_destination_paths(
        cls,
        path_source: str,
        fs_source: FileSystem,
        path_destination: str,
        fs_destination: FileSystem,
    ) -> Tuple[str, str]:
        """Modify sync paths according to how a trailing slash on the source path should be treated"""
        # TODO I'm not exactly sure if this covers source and destination being symlinks (lstat vs stat etc)
        # we only need to consider when the destination is a directory
        try:
            lstat_destination = fs_destination.lstat(path_destination)
        except FileNotFoundError:
            return path_source, path_destination
        except (NotADirectoryError, PermissionError) as e:
            perror(path_source, e, FATAL)

        if stat.S_ISLNK(lstat_destination.st_mode):
            logging_fatal(
                "Destination is a symlink. Not sure what to do. See GitHub issue #8"
            )

        if not stat.S_ISDIR(lstat_destination.st_mode):
            return path_source, path_destination

        # we know the destination is a directory at this point
        try:
            lstat_source = fs_source.lstat(path_source)
        except FileNotFoundError:
            return path_source, path_destination
        except (NotADirectoryError, PermissionError) as e:
            perror(path_source, e, FATAL)

        if stat.S_ISREG(lstat_source.st_mode) or (
            stat.S_ISDIR(lstat_source.st_mode) and path_source[-1] not in ["/", "\\"]
        ):
            path_destination = fs_destination.join(
                path_destination, fs_destination.split(path_source)[1]
            )
        return path_source, path_destination

    @classmethod
    def about_tree(self, tree, copy_size=0, copy_files=0):
        if not isinstance(tree, dict):
            copy_size += tree[2]
            copy_files += 1
        else:
            tree_items = list(tree.items())
            for key, value in tree_items:
                if key.endswith("."):
                    continue
                copy_files, copy_size = self.about_tree(value, copy_size, copy_files)
        return copy_files, copy_size


def main():
    args = get_cli_args(__doc__, __version__)

    setup_root_logger(
        no_color=args.logging_no_color,
        verbosity_level=args.logging_verbosity_verbose,
        quietness_level=args.logging_verbosity_quiet,
        messagefmt="[%(levelname)s] %(message)s" if os.name == "nt" else "%(message)s",
    )

    for exclude_from_pathname in args.exclude_from:
        with exclude_from_pathname.open("r") as f:
            args.exclude.extend(line for line in f.read().splitlines() if line)

    adb_arguments = [args.adb_bin] + [f"-{arg}" for arg in args.adb_flags]
    for option, value in args.adb_options:
        adb_arguments.append(f"-{option}")
        adb_arguments.append(value)

    fs_android = AndroidFileSystem(adb_arguments, args.adb_encoding)
    fs_local = LocalFileSystem(adb_arguments)

    try:
        fs_android.test_connection()
    except BrokenPipeError:
        logging_fatal("Connection test failed")

    live.start()

    if args.direction == "push":
        path_source = args.direction_push_local.rstrip("/")
        fs_source = fs_local
        path_destination = args.direction_push_android.rstrip("/")
        fs_destination = fs_android
    else:
        path_source = args.direction_pull_android.rstrip("/")
        fs_source = fs_android
        path_destination = args.direction_pull_local.rstrip("/")
        fs_destination = fs_local

    path_source, path_destination = FileSyncer.paths_to_fixed_destination_paths(
        path_source, fs_source, path_destination, fs_destination
    )

    path_source = fs_source.normpath(path_source)
    path_destination = fs_destination.normpath(path_destination)

    try:
        fs_source.counting_progress = source_counting_progress
        fs_source.counting_progress_id = source_counting_progress.tasks.pop(0).id

        files_tree_source = fs_source.get_files_tree(
            path_source, follow_links=args.copy_links
        )
        source_total_files, total_size = fs_source.total_files, fs_source.total_size
    except (FileNotFoundError, NotADirectoryError, PermissionError) as e:
        perror(path_source, e, FATAL)

    try:
        fs_destination.counting_progress = destination_counting_progress
        fs_destination.counting_progress_id = destination_counting_progress.tasks.pop(
            0
        ).id
        files_tree_destination = fs_destination.get_files_tree(
            path_destination, follow_links=args.copy_links
        )
        completed_files, completed_size = (
            fs_destination.total_files,
            fs_destination.total_size,
        )
    except FileNotFoundError:
        files_tree_destination = None
    except (NotADirectoryError, PermissionError) as e:
        perror(path_destination, e, FATAL)
    if args.show_tree:
        overall_progress.console.print("Source tree:")
        if files_tree_source is not None:
            tree = Tree(
                f":open_file_folder: [link file://{path_source}]{path_source}",
                guide_style="bold bright_blue",
            )
            log_tree(path_source, files_tree_source, tree)
            print(tree)
        overall_progress.console.print("")

        overall_progress.console.print("Destination tree:")
        if files_tree_destination is not None:
            tree = Tree(
                f":open_file_folder: [link file://{path_destination}]{path_destination}",
                guide_style="bold bright_blue",
            )
            log_tree(path_destination, files_tree_destination, tree)
            print(tree)

        overall_progress.console.print("")

    if isinstance(files_tree_source, dict):
        excludePatterns = [
            fs_destination.normpath(fs_destination.join(path_destination, exclude))
            for exclude in args.exclude
        ]
    else:
        excludePatterns = [
            fs_destination.normpath(path_destination + exclude)
            for exclude in args.exclude
        ]
    logging.debug("Exclude patterns:")
    logging.debug(excludePatterns)
    logging.debug("")

    (
        tree_delete,
        tree_copy,
        tree_excluded_source,
        tree_unaccounted_destination,
        tree_excluded_destination,
    ) = FileSyncer.diff_trees(
        files_tree_source,
        files_tree_destination,
        path_source,
        path_destination,
        excludePatterns,
        fs_source.join,
        fs_destination.join,
        folder_file_overwrite_error=not args.dry_run and not args.force,
    )

    if args.copy_to_new_folder:
        if path_destination != "." and fs_destination.exists(path_destination):
            path_destination = (
                f'{path_destination}_{datetime.now().strftime("%Y_%m_%d")}'
            )
            if fs_destination.exists(path_destination):  # recheck the new dest path
                files_tree_destination = fs_destination.get_files_tree(
                    path_destination, follow_links=args.copy_links
                )
                (
                    tree_delete,
                    tree_copy,
                    tree_excluded_source,
                    tree_unaccounted_destination,
                    tree_excluded_destination,
                ) = FileSyncer.diff_trees(
                    tree_copy,
                    files_tree_destination,
                    path_source,
                    path_destination,
                    excludePatterns,
                    fs_source.join,
                    fs_destination.join,
                    folder_file_overwrite_error=not args.dry_run and not args.force,
                )

    tree_delete = FileSyncer.prune_tree(tree_delete)
    tree_copy = FileSyncer.prune_tree(tree_copy)
    tree_excluded_source = FileSyncer.prune_tree(tree_excluded_source)
    tree_unaccounted_destination = FileSyncer.prune_tree(tree_unaccounted_destination)
    tree_excluded_destination = FileSyncer.prune_tree(tree_excluded_destination)

    tree_delete = FileSyncer.sort_tree(tree_delete)
    tree_copy = FileSyncer.sort_tree(tree_copy)
    tree_excluded_source = FileSyncer.sort_tree(tree_excluded_source)
    tree_unaccounted_destination = FileSyncer.sort_tree(tree_unaccounted_destination)
    tree_excluded_destination = FileSyncer.sort_tree(tree_excluded_destination)

    if tree_delete is not None:
        overall_progress.console.print("Delete tree:")
        tree = Tree(
            f":open_file_folder: [link file://{path_destination}]{path_destination}",
            guide_style="bold bright_blue",
        )
        log_tree(path_destination, tree_delete, tree)
        print(tree)
    overall_progress.console.print("")

    if args.show_tree:
        overall_progress.console.print("Copy tree:")
        if tree_copy is not None:
            tree = Tree(
                f":open_file_folder: [link file://{path_destination}]{path_destination}",
                guide_style="bold bright_blue",
            )
            log_tree(f"{path_source} --> {path_destination}", tree_copy, tree)
            print(tree)

        overall_progress.console.print("")

        overall_progress.console.print("Source excluded tree:")
        if tree_excluded_source is not None:
            tree = Tree(
                f":open_file_folder: [link file://{path_destination}]{path_destination}",
                guide_style="bold bright_blue",
            )
            log_tree(path_source, tree_excluded_source, tree)
            print(tree)
        overall_progress.console.print("")

        overall_progress.console.print("Destination unaccounted tree:")
        if tree_unaccounted_destination is not None:
            # log_treed(path_destination, tree_unaccounted_destination, log_leaves_types = False)
            tree = Tree(
                f":open_file_folder: [link file://{path_destination}]{path_destination}",
                guide_style="bold bright_blue",
            )
            log_tree(path_source, tree_unaccounted_destination, tree)
            print(tree)
        overall_progress.console.print("")

        overall_progress.console.print("Destination excluded tree:")
        if tree_excluded_destination is not None:
            tree = Tree(
                f":open_file_folder: [link file://{path_destination}]{path_destination}",
                guide_style="bold bright_blue",
            )
            log_tree(path_source, tree_excluded_destination, tree)
            print(tree)
        overall_progress.console.print("")

    tree_unaccounted_destination_non_excluded = None
    if tree_unaccounted_destination is not None:
        tree_unaccounted_destination_non_excluded = FileSyncer.prune_tree(
            FileSyncer.remove_excluded_folders_from_unaccounted_tree(
                tree_unaccounted_destination, tree_excluded_destination
            )
        )

    if args.show_tree:
        overall_progress.console.print(
            "Non-excluded-supporting destination unaccounted tree:"
        )
        if tree_unaccounted_destination_non_excluded is not None:
            tree = Tree(
                f":open_file_folder: [link file://{path_destination}]{path_destination}",
                guide_style="bold bright_blue",
            )
            log_tree(path_source, tree_unaccounted_destination_non_excluded, tree)
            print(tree)
        overall_progress.console.print("")

        overall_progress.console.print("SYNCING")
        overall_progress.console.print("")

    if tree_delete is not None:
        overall_progress.console.print("Deleting delete tree")
        fs_destination.remove_tree(path_destination, tree_delete, dry_run=args.dry_run)
    else:
        if args.show_tree:
            overall_progress.console.print("Empty delete tree")

    if args.delete_excluded and args.delete:
        if tree_excluded_destination is not None:
            overall_progress.console.print("Deleting destination excluded tree")
            fs_destination.remove_tree(
                path_destination, tree_excluded_destination, dry_run=args.dry_run
            )
        else:
            overall_progress.console.print("Empty destination excluded tree")

        if tree_unaccounted_destination is not None:
            overall_progress.console.print("Deleting destination unaccounted tree")
            fs_destination.remove_tree(
                path_destination, tree_unaccounted_destination, dry_run=args.dry_run
            )
        else:
            overall_progress.console.print("Empty destination unaccounted tree")
        overall_progress.console.print("")
    elif args.delete_excluded:
        if tree_excluded_destination is not None:
            overall_progress.console.print("Deleting destination excluded tree")
            fs_destination.remove_tree(
                path_destination, tree_excluded_destination, dry_run=args.dry_run
            )
        else:
            overall_progress.console.print("Empty destination excluded tree")
        overall_progress.console.print("")
    elif args.delete:
        if tree_unaccounted_destination_non_excluded is not None:
            overall_progress.console.print(
                "Deleting non-excluded-supporting destination unaccounted tree"
            )
            fs_destination.remove_tree(
                path_destination,
                tree_unaccounted_destination_non_excluded,
                dry_run=args.dry_run,
            )
        else:
            overall_progress.console.print(
                "Empty non-excluded-supporting destination unaccounted tree"
            )
        overall_progress.console.print("")

    if tree_copy is not None:
        fs_destination.makedirs(path_destination)
        copy_files, copy_size = FileSyncer.about_tree(tree_copy)
        overall_progress.console.print("Copying files:")
        prog_title = f"[bold red]{args.direction}ing [bold violet]{truncate_path(path_source,4)} [/bold violet]to [bold violet]{truncate_path(path_destination,4)}"

        fields = f"[0/{copy_files}]"
        prog_id = overall_progress.add_task(
            prog_title,
            total=copy_size,
            fields=fields,
            visible=args.show_progress,
        )
        fs_destination.push_tree_here(
            path_source,
            (
                fs_destination.split(path_source)[1]
                if isinstance(tree_copy, tuple)
                else "."
            ),
            tree_copy,
            path_destination,
            fs_source,
            dry_run=args.dry_run,
            show_progress=args.show_progress,
            source_total_files=copy_files,
        )
        prog_title = f"[bold red]{args.direction}ed [bold violet]{truncate_path(path_source,4)} [/bold violet]to [bold violet]{truncate_path(path_destination,4)}"
        overall_progress.update(prog_id, description=prog_title)
        time.sleep(0.5)
    else:
        overall_progress.console.print("Empty copy tree")


if __name__ == "__main__":
    main()
