"""Sync mode: watch for saves, run format -> message -> commit -> push.

The actual format/diff/message/commit/push work is delegated to
`CommitPipeline` (see pipeline.py) -- the exact same pipeline the manual
`/commit` command uses -- so this module is only responsible for
watchdog plumbing (debouncing filesystem events) and updating the
sync-specific UI state (`ctx.sync_status`, the activity feed).
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from . import git
from .config import is_ignored
from .pipeline import CommitPipeline
from .utils import human_path

if TYPE_CHECKING:
    from .models import AppContext

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    FileSystemEventHandler = object  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


def run_commit_pipeline(ctx: "AppContext", path: Path, push: bool) -> bool:
    """Format -> diff -> AI message -> commit -> (optional) push for ONE
    file, via the shared CommitPipeline. Also updates `ctx.sync_status`
    (consumed by the REPL's bottom toolbar) and the activity feed --
    bookkeeping that only the sync watcher needs."""
    cfg = ctx.config
    root = cfg.root
    rel = human_path(path, root)
    status = ctx.sync_status
    pipeline = CommitPipeline(cfg)

    status.busy = True
    status.current_file = rel
    status.current_stage = "format"

    try:
        changed, fmt_error = pipeline.format_file(rel)
        if changed:
            ctx.activity.add(f"Formatted {rel}", "info")
        elif fmt_error:
            ctx.activity.add(f"Format failed on {rel}: {fmt_error}", "error")

        changed_files = {c.path for c in pipeline.scan(refresh=True)}
        if rel not in changed_files:
            logger.debug(
                "Sync skip %s: not in changed set (path=%s, root=%s, changed=%s)",
                rel, path, root, sorted(changed_files),
            )
            ctx.activity.add(
                f"Sync skipped {rel} (not detected as changed)", "warn"
            )
            return False

        status.current_stage = "message"
        diff = pipeline.diff_for(rel)
        message, source = pipeline.generate_message(rel, diff)

        status.current_stage = "commit"
        try:
            pipeline.commit(rel, message)
        except git.GitError as exc:
            logger.error("Commit failed on %s: %s", rel, exc)
            ctx.activity.add(f"Commit failed on {rel}: {exc}", "error")
            return False

        status.commits_this_session += 1
        status.last_file = rel
        status.last_commit_message = message

        tag = "" if source == "ollama" else f" ({source})"
        ctx.activity.add(f"Committed {rel}: {message}{tag}", "success")

        if push:
            status.current_stage = "push"
            try:
                pipeline.push()
                status.last_push_time = time.time()
                status.current_stage = "pushed"
                ctx.activity.add(
                    f"Pushed {rel} to {cfg.git.remote}/{cfg.git.branch}", "success"
                )
                time.sleep(1.2)  # let the toolbar show "pushed ✓" briefly
            except git.GitError as exc:
                logger.error("Push failed: %s", exc)
                ctx.activity.add(f"Push failed: {exc}", "error")

        return True
    finally:
        status.busy = False
        status.current_file = None
        status.current_stage = None


class _Handler(FileSystemEventHandler):
    def __init__(self, ctx: "AppContext") -> None:
        self.ctx = ctx
        self._timers: dict[str, threading.Timer] = {}
        self._lock = threading.Lock()

    def _on_change(self, src_path: str) -> None:
        path = Path(src_path)
        cfg = self.ctx.config
        if path.is_dir() or is_ignored(path, cfg.root, cfg.ignore):
            return
        delay = cfg.sync.debounce_seconds
        with self._lock:
            existing = self._timers.get(src_path)
            if existing:
                existing.cancel()
            timer = threading.Timer(delay, self._fire, args=(src_path,))
            timer.daemon = True
            self._timers[src_path] = timer
            timer.start()

    def _fire(self, src_path: str) -> None:
        with self._lock:
            self._timers.pop(src_path, None)

        logger.debug("Sync fire: %s", src_path)
        try:
            result = run_commit_pipeline(
                self.ctx,
                Path(src_path),
                push=self.ctx.config.sync.push,
            )
            logger.debug("Sync result for %s: %s", src_path, result)
        except Exception:
            # Runs on a watchdog-owned timer thread with nothing above it
            # to catch a failure -- an uncaught exception here would just
            # silently kill this debounce timer with no user-visible
            # sign anything went wrong, so log the full traceback and
            # move on rather than letting a bug in one commit cycle break
            # every commit cycle after it.
            logger.exception("Unhandled error in sync pipeline for %s", src_path)

    def on_created(self, event):
        if not event.is_directory:
            self._on_change(event.src_path)

    def on_modified(self, event):
        logger.debug("Watchdog event: %s", event.src_path)
        if not event.is_directory:
            self._on_change(event.src_path)


class SyncController:
    def __init__(self, ctx: "AppContext") -> None:
        self.ctx = ctx
        self._observer = None

    @property
    def is_running(self) -> bool:
        return self._observer is not None and self._observer.is_alive()

    def start(self) -> str:
        if not WATCHDOG_AVAILABLE:
            return "watchdog is not installed — run: pip install watchdog"
        if self.is_running:
            return "Sync is already running."
        handler = _Handler(self.ctx)
        observer = Observer()
        observer.schedule(handler, str(self.ctx.config.root), recursive=True)
        observer.start()
        self._observer = observer
        self.ctx.activity.add("Sync started", "success")
        return "Sync started — watching for file changes."

    def stop(self) -> str:
        if not self.is_running:
            return "Sync is not running."
        self._observer.stop()
        self._observer.join(timeout=5)
        self._observer = None
        self.ctx.activity.add("Sync stopped", "warn")
        return "Sync stopped."
