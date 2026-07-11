"""Project root discovery + config loading/saving.

Thin facade over :mod:`ryft.core.config.loader` (the v2 loader that understands
``ryft.toml``, ``pyproject.toml [tool.ryft]``, and the legacy ``.src.py``). The
v1 ``.src.py``-only API is kept for back-compat but now delegates to the shared
loader. ``is_ignored`` and ``set_model`` remain here because they touch the
local filesystem / on-disk config directly.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from .core.config.loader import (  # noqa: F401
    DEFAULT_TOML,
    find_root,
    init_config,
    load_config,
    validate_config,
)
from .core.config.schema import Config

logger = logging.getLogger(__name__)

CONFIG_FILENAME = ".src.py"
DEFAULT_IGNORE = ["__pycache__", ".venv", "venv", "dist", "build", ".git", "ryft"]


def is_ignored(path: Path, root: Path, extra_patterns: object = ()) -> bool:
    try:
        rel_parts = path.relative_to(root).parts
    except ValueError:
        rel_parts = path.parts
    # `cfg.ignore` is an `IgnoreConfig` dataclass in v2; accept it directly so
    # v1-era callers (pipeline.py, sync.py) that pass `cfg.ignore` keep working.
    if hasattr(extra_patterns, "patterns"):
        extra_patterns = extra_patterns.patterns  # type: ignore[attr-defined]
    patterns = set(DEFAULT_IGNORE) | set(extra_patterns or ())
    for part in rel_parts:
        if part in patterns or part.startswith("."):
            return True
    return False


def set_model(cfg: Config, model: str) -> None:
    """Update the commit model in memory and, best-effort, on disk.

    Updates both the back-compat ``cfg.ollama.commit_model`` view and the
    canonical ``cfg.providers.roles.commit`` assignment. If the active config
    file is ``ryft.toml``, the ``[providers] commit =`` line is rewritten; for
    the legacy ``.src.py`` the ``commit_model`` line is rewritten.
    """
    cfg.ollama.commit_model = model
    cfg.providers.roles.commit = f"ollama:{model}"

    if cfg.path is None or not cfg.path.exists():
        return

    text = cfg.path.read_text(encoding="utf-8")
    if cfg.path.name == "ryft.toml":
        if re.search(r"^\s*commit\s*=", text, flags=re.M):
            text = re.sub(
                r'(\s*commit\s*=\s*")[^"]*(")',
                lambda m: f'{m.group(1)}{model}{m.group(2)}',
                text, count=1, flags=re.M,
            )
        else:
            text = text.rstrip() + f'\ncommit = "ollama:{model}"\n'
    else:
        if re.search(r"^\s*commit_model\s*=", text, flags=re.M):
            text = re.sub(
                r'(\s*commit_model\s*=\s*")[^"]*(")',
                lambda m: f'{m.group(1)}{model}{m.group(2)}',
                text, count=1, flags=re.M,
            )
        else:
            text += f'\n    commit_model = "{model}"\n'
    cfg.path.write_text(text, encoding="utf-8")
