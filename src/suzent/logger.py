"""
Centralized logging configuration for Suzent using loguru.

Simple logging setup with color-coded console output and optional file logging.
"""

import sys
from pathlib import Path
from typing import Optional

from loguru import logger

# Track if logging has been configured to prevent duplicate handlers
_logging_configured = False


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

    # Add console handler with colors and nice formatting
    logger.add(
        sys.stdout,
        level=level.upper(),
        format="<green>{time:HH:mm:ss}</green> | <level>{level:8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan> | <level>{message}</level>",
        colorize=True,
    )

    # Optional file handler with rotation
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        logger.add(
            log_file,
            level="DEBUG",  # Always log everything to file
            format="{time:YYYY-MM-DD HH:mm:ss} | {level:8} | {name}:{function}:{line} | {message}",
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
