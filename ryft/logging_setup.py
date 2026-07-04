"""Centralized logging configuration for Ryft.

Ryft's UI (rich console output, the activity feed) is the intended
"visible" surface for the person running it — logging exists alongside
that, not instead of it, so nothing here should ever print to
stdout/stderr on its own. Everything goes to a rotating file under
``<project_root>/.ryft/ryft.log`` so `/doctor`-style debugging has a
trail to inspect without changing what shows up on screen.

Call `configure_logging(root)` once, early in the process (currently
from `__main__.build_context`). It's safe to call more than once —
later calls are no-ops once the root Ryft logger already has handlers.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path

_LOGGER_NAME = "ryft"
_CONFIGURED = False


def configure_logging(root: Path | None = None) -> logging.Logger:
    """Attach a rotating file handler to the `ryft` logger tree.

    Level defaults to INFO, or DEBUG if RYFT_DEBUG is set in the
    environment (any non-empty value) — useful when reproducing an
    issue without editing code.
    """
    global _CONFIGURED
    logger = logging.getLogger(_LOGGER_NAME)

    if _CONFIGURED:
        return logger

    level = logging.DEBUG if os.environ.get("RYFT_DEBUG") else logging.INFO
    logger.setLevel(level)

    try:
        log_dir = (root or Path.cwd()) / ".ryft"
        log_dir.mkdir(parents=True, exist_ok=True)
        handler: logging.Handler = logging.handlers.RotatingFileHandler(
            log_dir / "ryft.log", maxBytes=1_000_000, backupCount=2, encoding="utf-8"
        )
    except OSError:
        # Read-only filesystem, permissions issue, etc. — fall back to a
        # no-op handler rather than let logging setup break the CLI.
        handler = logging.NullHandler()

    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)-8s %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    logger.propagate = False
    _CONFIGURED = True
    return logger
