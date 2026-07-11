"""Filesystem helpers: discovery, binary detection, path normalization.

Dependency-free. No git, no AI — just the local filesystem, so this module is
safe to import anywhere (including tests) without side effects. This is the
single filesystem-discvery module for Ryft; the old ``ryft.commons`` duplicate
was merged into ``ryft.git`` + ``ryft.fs`` during the v2 consolidation.
"""

from __future__ import annotations

import os
from pathlib import Path

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

BINARY_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico",
    ".pyc", ".pyo", ".so", ".dll", ".dylib", ".exe", ".bin",
    ".zip", ".tar", ".gz", ".whl", ".db", ".sqlite3", ".pdf",
    ".mp3", ".mp4", ".wav", ".mov",
})

_DEFAULT_IGNORE = ["__pycache__", ".venv", "venv", "dist", "build", ".git"]


def is_binary_file(path: Path) -> bool:
    if path.suffix.lower() in BINARY_EXTENSIONS:
        return True
    try:
        with path.open("rb") as f:
            return b"\x00" in f.read(8192)
    except OSError:
        return True


def discover_files(
    root: Path,
    extra_ignore: list[str],
    suffixes: set[str] | None = None,
) -> list[Path]:
    """Walk *root*, skipping ignored dirs, returning text files (optionally
    filtered to *suffixes*). Used by tree/files/bulk format."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dp = Path(dirpath)
        dirnames[:] = [d for d in dirnames if not _is_ignored(dp / d, root, extra_ignore)]
        for fname in filenames:
            fp = dp / fname
            if _is_ignored(fp, root, extra_ignore):
                continue
            if suffixes is not None and fp.suffix.lower() not in suffixes:
                continue
            if is_binary_file(fp):
                continue
            try:
                if fp.stat().st_size > MAX_FILE_SIZE:
                    continue
            except OSError:
                continue
            found.append(fp)
    return sorted(found)


def _is_ignored(path: Path, root: Path, extra_patterns: list[str]) -> bool:
    try:
        rel_parts = path.relative_to(root).parts
    except ValueError:
        rel_parts = path.parts
    patterns = set(_DEFAULT_IGNORE) | set(extra_patterns)
    for part in rel_parts:
        if part in patterns or part.startswith("."):
            return True
    return False


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    keep = max(80, max_chars - 80)
    return text[:keep] + f"\n... [truncated {len(text) - keep} chars]"


def human_path(path: Path, root: Path) -> str:
    """Relative path of *path* under *root*, for display AND git matching.

    Resolves both sides first so symlinked cwds (macOS /tmp, containers) still
    produce the relative string git itself would report.
    """
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except (ValueError, OSError):
        try:
            return str(path.relative_to(root))
        except ValueError:
            return str(path)
