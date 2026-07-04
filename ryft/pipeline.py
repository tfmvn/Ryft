"""The single implementation of "what happens to a changed file on its
way into a commit": scan -> format -> diff -> AI message -> commit ->
push.

Before this module existed, `commands.py` (manual `/commit`) and
`sync.py` (the file-watcher) each called `git`/`ai`/`formatter` directly
and had grown two independent, slightly-drifted copies of this flow. Both
now build on `CommitPipeline` instead. The two callers still own their
own orchestration on top of it (parallel message generation + a live
tree view for `/commit`, single-file + toolbar status updates for sync)
because that's UI/control-flow, not "commit logic" — but the actual git
and AI calls all go through one place.

`CommitPipeline` is meant to be short-lived: create one per command
invocation (one `/commit`, one sync-triggered commit), not once for the
whole app, so `scan()`'s cache reflects a single consistent snapshot of
the working tree rather than silently drifting across unrelated calls.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from . import ai, formatter, git
from .config import is_ignored

if TYPE_CHECKING:
    from .models import Config

logger = logging.getLogger(__name__)


class CommitPipeline:
    """Scan / format / message / commit / push for one Ryft project."""

    def __init__(self, cfg: "Config") -> None:
        self.cfg = cfg
        self.root: Path = cfg.root
        self._changed_cache: list[git.FileChange] | None = None

    # ---- scanning -----------------------------------------------------

    def scan(self, *, refresh: bool = False) -> list[git.FileChange]:
        """Changed files, filtered by the project's ignore rules.

        Cached for the lifetime of this pipeline instance so a single
        commit operation doesn't re-run `git status` between every step
        that wants to know "what's changed" — pass refresh=True (e.g.
        after formatting a file, which can itself change what's staged)
        to force a fresh read.
        """
        if refresh or self._changed_cache is None:
            all_changes = git.changed_files(self.root)
            self._changed_cache = [
                c for c in all_changes
                if not is_ignored(self.root / c.path, self.root, self.cfg.ignore)
            ]
        return self._changed_cache

    # ---- formatting -----------------------------------------------------

    def format_file(self, rel_path: str) -> tuple[bool, str | None]:
        """Format one file in place, if the formatter is enabled.

        Returns (changed, error). Never raises — a formatting failure
        must never block the rest of the commit flow; the caller decides
        whether/how to surface `error` to the user.
        """
        if not self.cfg.formatter.enabled:
            return False, None
        path = self.root / rel_path
        if not path.exists():
            return False, None
        try:
            changed = formatter.format_file(
                path, max_blank_lines=self.cfg.formatter.max_blank_lines
            )
            return changed, None
        except OSError as exc:
            logger.warning("Format failed on %s: %s", rel_path, exc)
            return False, str(exc)
        except Exception as exc:  # defensive net for unforeseen formatter bugs
            logger.exception("Unexpected error formatting %s", rel_path)
            return False, str(exc)

    # ---- diff / message -------------------------------------------------

    def diff_for(self, rel_path: str) -> str:
        return git.diff_for(self.root, rel_path)

    def generate_message(self, rel_path: str, diff: str) -> tuple[str, str]:
        """Returns (message, source) — see `ai.generate_commit_message`
        for the source hierarchy (cache/auto/ollama/fallback)."""
        cfg = self.cfg
        client = ai.make_commit_client(cfg.ollama)
        return ai.generate_commit_message(
            client,
            cfg.ollama.enabled,
            cfg.git.fallback_commit_message,
            rel_path,
            diff,
            root=self.root,
            auto_threshold=cfg.git.small_change_threshold,
            use_auto_small=cfg.git.auto_commit_small_changes,
        )

    # ---- commit / push ----------------------------------------------------

    def commit(self, rel_path: str, message: str) -> str:
        """Stage and commit exactly one file. Raises git.GitError."""
        return git.commit_file(self.root, rel_path, message)

    def push(self) -> str:
        """Push to the project's configured remote/branch. Raises
        git.GitError."""
        return git.push(self.root, self.cfg.git.remote, self.cfg.git.branch)
