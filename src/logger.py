from __future__ import annotations

"""Centralized logging configuration for the project.

Call `setup_logging()` early (e.g., at CLI startup) to configure root logger
with colored output and sensible defaults. Individual modules should obtain a
logger via `get_logger(__name__)`.
"""

import logging
import os
from dotenv import load_dotenv
from typing import Optional

try:
    from rich.console import Console
    from rich.logging import RichHandler

    _RICH_AVAILABLE = True
except ImportError:  # pragma: no cover
    _RICH_AVAILABLE = False


# Load variables from .env file before accessing env vars
load_dotenv()

_DEFAULT_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Load variables from .env file at logger initialization time
# (already loaded above)


def setup_logging(level: str = _DEFAULT_LEVEL) -> None:
    """Configure global logging. Idempotent."""

    if logging.getLogger().handlers:
        return  # already configured

    root_level = logging.getLevelName(level)
    handlers: list[logging.Handler]

    if _RICH_AVAILABLE:
        handlers = [RichHandler(rich_tracebacks=True, markup=True)]
    else:
        stream = logging.StreamHandler()
        handlers = [stream]

    logging.basicConfig(
        level=root_level,
        format="%(message)s" if _RICH_AVAILABLE else "%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a module-level logger lazily configured."""

    setup_logging()
    return logging.getLogger(name) 