"""Replaces loguru's default handler before the CLI's remaining imports run.

``suzent.config`` logs which override file it loaded while it is still being
imported -- long before the Typer callback reaches ``configure_logging``. At
that point loguru's default handler is the only one installed, so the line
lands on stderr and corrupts commands that promise a single line of output,
``--version`` most visibly.

Importing this module first swaps that default for a WARNING-level handler.
``setup_logging`` removes it and installs the configured handler when the CLI
configures logging for real, so verbosity and the backend's own logging are
unaffected. This module must therefore be imported before any other
``suzent.*`` module in the CLI package.
"""

import sys

from loguru import logger

logger.remove()
logger.add(sys.stderr, level="WARNING")
