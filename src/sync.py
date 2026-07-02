"""Sync mode: watch for saves, run format → message → commit → push."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from . import ai, formatter, git
from .config import is_ignored
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


def run_commit_pipeline(ctx: "AppContext", path: Path, push: bool) -> bool:
    """Format → diff → AI message → commit → (optional) push for ONE file."""
    cfg    = ctx.config
    root   = cfg.root
    rel    = human_path(path, root)
    status = ctx.sync_status

    status.busy = True
    status.current_file = rel
    status.current_stage = "format"

    try:
        if cfg.formatter.enabled and path.exists():
            try:
                if formatter.format_file(path, max_blank_lines=cfg.formatter.max_blank_lines):
                    ctx.activity.add(f"Formatted {rel}", "info")
            except Exception as exc:
                ctx.activity.add(f"Format failed on {rel}: {exc}", "error")

        changed = {c.path for c in git.changed_files(root)}
        if rel not in changed:
            return False

        status.current_stage = "message"
        diff   = git.diff_for(root, rel)
        client = ai.make_commit_client(cfg.ollama)
        message, source = ai.generate_commit_message(
            client,
            cfg.ollama.enabled,
            cfg.git.fallback_commit_message,
            rel,
            diff,
            root=root,
            auto_threshold=cfg.git.small_change_threshold,
            use_auto_small=cfg.git.auto_commit_small_changes,
        )

        status.current_stage = "commit"
        try:
            git.commit_file(root, rel, message)
        except git.GitError as exc:
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
                git.push(root, cfg.git.remote, cfg.git.branch)
                status.last_push_time = time.time()
                status.current_stage = "pushed"
                ctx.activity.add(f"Pushed {rel} to {cfg.git.remote}/{cfg.git.branch}", "success")
                time.sleep(1.2)  # let the toolbar show "pushed ✓" briefly
            except git.GitError as exc:
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
        cfg  = self.ctx.config
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
        run_commit_pipeline(self.ctx, Path(src_path), push=self.ctx.config.sync.push)

    def on_created(self, event):
        if not event.is_directory:
            self._on_change(event.src_path)

    def on_modified(self, event):
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
        handler  = _Handler(self.ctx)
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