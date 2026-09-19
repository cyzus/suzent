"""
Centralized logging configuration for Suzent using loguru.

One record is rendered one of two ways. A terminal gets a short, coloured line
meant to be read as it scrolls past. Anything else -- a file, a pipe, a service
manager's capture of stdout -- gets an uncoloured line carrying the full
timestamp and the call site, because that is the copy someone reads long after
the fact, and it is the copy the console's log viewer has to parse.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Optional

from loguru import logger

# Track if logging has been configured to prevent duplicate handlers
_logging_configured = False

# The fields, in the order every reader expects them: when, how bad, where
# from, what happened. Kept aligned between the two formats so a tail of a log
# parses the same whether it was written by the file handler or by a service
# manager capturing stdout.
CONSOLE_FORMAT = (
    "<green>{time:HH:mm:ss}</green> | <level>{level:8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
    "<level>{message}</level>"
)
FILE_FORMAT = (
    "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:8} | {name}:{function}:{line} | {message}"
)


def _stdout_is_a_terminal() -> bool:
    try:
        return sys.stdout.isatty()
    except (AttributeError, ValueError):  # closed or replaced stream
        return False


def _is_where_stdout_already_goes(path: Path) -> bool:
    """Whether stdout is already redirected into ``path``.

    The desktop app and the macOS LaunchAgent both point the child's stdout at
    ``server.log`` *and* ask for a log file, which wrote every record twice, in
    two different formats. Neither side can see the other's arrangement, so the
    duplicate is detected here instead: same device and inode means the file
    handler would only be echoing what stdout already delivers.
    """
    try:
        target = path.stat()
        stream = os.fstat(sys.stdout.fileno())
    except (OSError, AttributeError, ValueError):
        return False
    # st_ino is 0 for some Windows handles; an inode of 0 proves nothing.
    if not stream.st_ino:
        return False
    return (stream.st_dev, stream.st_ino) == (target.st_dev, target.st_ino)


class InterceptHandler(logging.Handler):
    """Hands a standard-library log record to loguru.

    Uvicorn, httpx and every other dependency log through ``logging``, and
    their lines used to arrive in the same file in their own shapes --
    ``INFO:     127.0.0.1 - "GET /ops/logs" 200 OK`` next to a loguru record.
    The console's viewer then had a log it could only half read: no level to
    filter on, no origin to search for, for the majority of the lines.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno  # a custom level loguru does not know

        # Attribute the line to the logger that emitted it -- "uvicorn.access"
        # -- rather than to the frame inside the logging machinery that would
        # otherwise be picked up, which is the same for every dependency.
        origin = logger.patch(
            lambda entry: entry.update(
                name=record.name, function=record.funcName, line=record.lineno
            )
        )
        origin.opt(exception=record.exc_info).log(level, record.getMessage())


def _stdlib_threshold(level: str) -> int:
    """``level`` as a number the standard library accepts.

    loguru has two levels ``logging`` has never heard of, and both are named
    in this module's own documentation as valid. Passing either one through by
    name raises ``ValueError: Unknown level`` and takes the server down during
    logging setup, so they are resolved to numbers here. loguru keeps the name
    it was given; only the stdlib threshold is translated.
    """
    severity = {"TRACE": 5, "SUCCESS": logging.INFO}.get(level.upper())
    if severity is not None:
        return severity
    resolved = logging.getLevelName(level.upper())
    # getLevelName answers "Level <name>" for anything it does not know.
    return resolved if isinstance(resolved, int) else logging.INFO


def _intercept_standard_logging(level: str) -> None:
    """Route every ``logging`` logger into loguru, and only into loguru.

    The threshold is applied here rather than at the sinks. The file sink
    keeps everything at DEBUG, which is right for Suzent's own records and
    wrong for its dependencies: httpx and friends at DEBUG bury the log this
    pass exists to make readable. Raising ``LOG_LEVEL`` lets them through.
    """
    logging.basicConfig(
        handlers=[InterceptHandler()], level=_stdlib_threshold(level), force=True
    )
    for name in list(logging.root.manager.loggerDict):
        existing = logging.getLogger(name)
        existing.handlers = []
        existing.propagate = True
        existing.setLevel(logging.NOTSET)  # defer to the root threshold


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
) -> None:
    """
    Configure logging for the entire application using loguru.

    Args:
        level: Logging level (TRACE, DEBUG, INFO, SUCCESS, WARNING, ERROR, CRITICAL)
        log_file: Optional file path to write logs to
    """
    global _logging_configured

    # Only configure once to prevent duplicate handlers
    if _logging_configured:
        return

    # Remove default handler
    logger.remove()

    _logging_configured = True

    _intercept_standard_logging(level)

    log_path = Path(log_file) if log_file else None

    # When both sinks would land in the same file, the file one wins: it keeps
    # every DEBUG record rather than only what `level` admits, and it rotates.
    # Output that never passes through loguru -- a traceback on the way out, a
    # dependency's print -- still reaches the file through the redirect.
    stdout_is_the_log_file = log_path is not None and _is_where_stdout_already_goes(
        log_path
    )

    if not stdout_is_the_log_file:
        to_terminal = _stdout_is_a_terminal()
        logger.add(
            sys.stdout,
            level=level.upper(),
            format=CONSOLE_FORMAT if to_terminal else FILE_FORMAT,
            colorize=to_terminal,
        )

    if log_path is None:
        return

    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_file,
        level="DEBUG",  # Always log everything to file
        format=FILE_FORMAT,
        rotation="10 MB",  # Rotate when file reaches 10MB
        retention="7 days",  # Keep logs for 7 days
        compression="zip",  # Compress rotated logs
    )


def get_logger(name: str):
    """
    Get a logger instance for a module.

    Args:
        name: Usually __name__ of the module

    Returns:
        Logger instance bound with the module name
    """
    return logger.bind(name=name)
