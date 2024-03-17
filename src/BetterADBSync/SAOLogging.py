"""Nice logging, with colors on Linux."""

import logging
import os
import sys
from typing import Any, Union

from rich.console import Group
from rich.filesize import decimal
from rich.live import Live
from rich.markup import escape
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.table import Table
from rich.text import Text
from rich.tree import Tree

overall_progress = Progress(
    TimeElapsedColumn(),
    TextColumn("{task.description}"),
    SpinnerColumn(),
    BarColumn(),
    TaskProgressColumn(),
    DownloadColumn(),
    TextColumn("{task.fields[fields]}"),
    TransferSpeedColumn(),
    TimeRemainingColumn(compact=True),
)


file_name_progress = Progress(
    TimeElapsedColumn(),
    TextColumn("{task.description}"),
    BarColumn(bar_width=10),
    TaskProgressColumn(),
    DownloadColumn(),
    TransferSpeedColumn(),
    SpinnerColumn(finished_text="✅"),  # ":heavy_check_mark:"
)

source_counting_progress = Progress(TextColumn("{task.description}"))
destination_counting_progress = Progress(TextColumn("{task.description}"))
destination_counting_progress.add_task(
    description=f"[green]Folders:0 | [magenta]Files:0 | [cyan]Size:0MB"
)
source_counting_progress.add_task(
    description=f"[green]Folders:0 | [magenta]Files:0 | [cyan]Size:0MB"
)
progress_table = Table.grid()
progress_table.add_row(
    Panel.fit(
        source_counting_progress,
        title="[b]Source",
        border_style="green",
        padding=(1, 1),
    ),
    Panel.fit(
        destination_counting_progress,
        title="[b]Destination",
        border_style="red",
        padding=(1, 1),
    ),
)

group = Group(progress_table, Group(file_name_progress, overall_progress))
live = Live(group)
# live.start()


class ColoredFormatter(logging.Formatter):
    """Logging Formatter to add colors"""

    fg_bright_blue = "\x1b[94m"
    fg_yellow = "\x1b[33m"
    fg_red = "\x1b[31m"
    fg_bright_red_bold = "\x1b[91;1m"
    reset = "\x1b[0m"

    def __init__(self, fmt, datefmt):
        super().__init__()
        self.messagefmt = fmt
        self.datefmt = datefmt

        self.formats = {
            logging.DEBUG: "{}{}{}".format(
                self.fg_bright_blue, self.messagefmt, self.reset
            ),
            logging.INFO: "{}".format(self.messagefmt),
            logging.WARNING: "{}{}{}".format(
                self.fg_yellow, self.messagefmt, self.reset
            ),
            logging.ERROR: "{}{}{}".format(self.fg_red, self.messagefmt, self.reset),
            logging.CRITICAL: "{}{}{}".format(
                self.fg_bright_red_bold, self.messagefmt, self.reset
            ),
        }

        self.formatters = {
            logging.DEBUG: logging.Formatter(
                self.formats[logging.DEBUG], datefmt=self.datefmt
            ),
            logging.INFO: logging.Formatter(
                self.formats[logging.INFO], datefmt=self.datefmt
            ),
            logging.WARNING: logging.Formatter(
                self.formats[logging.WARNING], datefmt=self.datefmt
            ),
            logging.ERROR: logging.Formatter(
                self.formats[logging.ERROR], datefmt=self.datefmt
            ),
            logging.CRITICAL: logging.Formatter(
                self.formats[logging.CRITICAL], datefmt=self.datefmt
            ),
        }

    def format(self, record):
        formatter = self.formatters[record.levelno]
        return formatter.format(record)


def setup_root_logger(
    no_color: bool = False,
    verbosity_level: int = 0,
    quietness_level: int = 0,
    messagefmt: str = "[%(asctime)s][%(levelname)s] %(message)s (%(filename)s:%(lineno)d)",
    messagefmt_verbose: str = "[%(asctime)s][%(levelname)s] %(message)s (%(filename)s:%(lineno)d)",
    datefmt: str = "%Y-%m-%d %H:%M:%S",
):
    messagefmt_to_use = messagefmt_verbose if verbosity_level else messagefmt
    logging_level = 10 * (2 + quietness_level - verbosity_level)
    if not no_color and sys.platform == "linux":
        formatter_class = ColoredFormatter
    else:
        formatter_class = logging.Formatter

    root_logger = logging.getLogger()
    root_logger.setLevel(logging_level)
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        formatter_class(fmt=messagefmt_to_use, datefmt=datefmt)
    )
    root_logger.addHandler(console_handler)


def logging_fatal(message, log_stack_info: bool = True, exit_code: int = 1):
    overall_progress.console.print("[INFO] " + message)
    logging.debug("Stack Trace", stack_info=log_stack_info)
    overall_progress.console.print("[INFO] Exiting")
    raise SystemExit(exit_code)


def log_tree(title, tree, rtree: Tree):
    if not isinstance(tree, dict):
        text_filename = Text(os.path.basename(title), "green")
        text_filename.highlight_regex(r"\..*$", "bold red")
        text_filename.stylize(f"link file://{title}")
        file_size = tree[2]
        text_filename.append(f" ({decimal(file_size)})", "blue")
        icon = "🐍 " if os.path.splitext(title)[1] == ".py" else "📄 "
        rtree.add(Text(icon) + text_filename)
    else:
        tree_items = list(tree.items())
        style = "dim" if title.startswith("__") else ""
        branch = rtree.add(
            f"[bold magenta]:open_file_folder: [link file://{title}]{escape(os.path.basename(title))}",
            style=style,
            guide_style=style,
        )
        for key, value in tree_items:
            tut = os.path.join(title, key).replace("\\", "/")
            if tut.endswith("."):
                continue
            log_tree(tut, value, branch)


def log_tree_old(
    title, tree, finals=None, log_leaves_types=False, logging_level=logging.INFO
):
    """Log tree nicely if it is a dictionary.
    log_leaves_types can be False to log no leaves, True to log all leaves, or a tuple of types for which to log.
    """
    if finals is None:
        finals = []
    if not isinstance(tree, dict):
        logging.log(
            msg="{}{}{}".format(
                "".join(
                    [" " if final else "│" for final in finals[:-1]]
                    + ["└" if final else "├" for final in finals[-1:]]
                ),
                title,
                (
                    ": {}".format(tree)
                    if log_leaves_types is not False
                    and (log_leaves_types is True or isinstance(tree, log_leaves_types))
                    else ""
                ),
            ),
            level=logging_level,
        )
    else:
        logging.log(
            msg="{}{}".format(
                "".join(
                    [" " if final else "│" for final in finals[:-1]]
                    + ["└" if final else "├" for final in finals[-1:]]
                ),
                title,
            ),
            level=logging_level,
        )
        tree_items = list(tree.items())
        for key, value in tree_items[:-1]:
            log_tree(
                os.path.join(title, key),
                value,
                finals=finals + [False],
                log_leaves_types=log_leaves_types,
                logging_level=logging_level,
            )
        for key, value in tree_items[-1:]:
            log_tree(
                os.path.join(title, key),
                value,
                finals=finals + [True],
                log_leaves_types=log_leaves_types,
                logging_level=logging_level,
            )


# like logging.CRITICAl, logging.DEBUG etc
FATAL = 60


def perror(s: Union[str, Any], e: Exception, logging_level: int = logging.ERROR):
    strerror = (
        e.strerror
        if (isinstance(e, OSError) and e.strerror is not None)
        else e.__class__.__name__
    )
    msg = f"{s}{': ' if s else ''}{strerror}"
    if logging_level == FATAL:
        logging_fatal(msg)
    else:
        logging.log(logging_level, msg)


def truncate_path(path, n=3):
    """
    Truncate the path string to fit.
    """
    width = overall_progress.console.width
    max_length = round(width / n)

    # overall_progress.columns[3].bar_width = round(width / 5) if round(width / 5) < 40 else 40
    # file_name_progress.columns[2].bar_width =  round(width/20) if round(width/20) < 10 else 10
    if len(path) > max_length:
        split = round((max_length - 3) / 2)
        return path[:split] + "..." + path[-split:]
    else:
        return path
