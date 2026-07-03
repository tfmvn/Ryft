"""Small shared helpers: the activity feed, file discovery, misc utils.

Nothing in here is specific to git/ai/formatter — those modules import
from here, not the other way around.
"""

from __future__ import annotations

import os
from collections import deque
from pathlib import Path

from .config import is_ignored
from .models import ActivityEvent

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB

BINARY_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".ico",
    ".pyc", ".pyo", ".so", ".dll", ".dylib", ".exe", ".bin",
    ".zip", ".tar", ".gz", ".whl", ".db", ".sqlite3", ".pdf",
    ".mp3", ".mp4", ".wav", ".mov",
})


class ActivityFeed:
    """In-memory ring buffer of recent events, newest last.

    This is the ONLY place events get recorded. Commands and the sync
    pipeline call `.add()`; the UI calls `.recent()` to render the panel.
    No raw logging anywhere else — that's the whole point.
    """

    def __init__(self, max_events: int = 200) -> None:
        self._events: deque[ActivityEvent] = deque(maxlen=max_events)

    def add(self, message: str, level: str = "info") -> ActivityEvent:
        event = ActivityEvent(message=message, level=level)
        self._events.append(event)
        return event

    def recent(self, n: int = 8) -> list[ActivityEvent]:
        return list(self._events)[-n:]

    def all(self) -> list[ActivityEvent]:
        return list(self._events)


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
    filtered to *suffixes*). Used by /tree, /files, and bulk /format."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dp = Path(dirpath)
        dirnames[:] = [d for d in dirnames if not is_ignored(dp / d, root, extra_ignore)]
        for fname in filenames:
            fp = dp / fname
            if is_ignored(fp, root, extra_ignore):
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


def truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    keep = max_chars - 80
    return text[:keep] + f"\n... [truncated {len(text) - keep} chars]"


def human_path(path: Path, root: Path) -> str:
    """Relative path of *path* under *root*, for display AND for matching
    against `git status` output.

    IMPORTANT: uses .resolve() on both sides before computing the relative
    path. Plain `path.relative_to(root)` compares path *components*
    literally — it does not follow symlinks. If `root` is an unresolved
    path (e.g. from Path.cwd()) but `path` arrives already canonicalized
    (e.g. from a filesystem-watcher event on macOS, where /tmp is a
    symlink to /private/tmp, or inside a container/synced-folder clone),
    the two won't share a literal prefix even though they point at the
    same file. That raises ValueError here, which used to silently fall
    back to returning the *absolute* path — which then can never match
    the relative paths `git status --porcelain` reports, so every
    downstream "is this file changed?" check fails silently.

    Resolving both sides first makes the comparison symlink-safe while
    still producing the same relative string git itself would report.
    """
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except (ValueError, OSError):
        # OSError: resolve() can fail on a file that vanished mid-event.
        # ValueError: path genuinely isn't under root.
        try:
            return str(path.relative_to(root))
        except ValueError:
            return str(path)