"""`kyte doctor` — comprehensive health checks.

Each check produces a `DoctorCheck`: a status (ok/warn/fail), a short
detail for the summary line, and — for anything that isn't "ok" — a
plain-English explanation of *why it matters* and *how to fix it*, plus
an optional callable that performs the fix automatically.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, TYPE_CHECKING

from . import ai, config as config_mod, git, recovery

if TYPE_CHECKING:
    from .models import AppContext

Status = str  # "ok" | "warn" | "fail"

MIN_PYTHON = (3, 10)


@dataclass
class DoctorCheck:
    name: str
    status: Status
    detail: str
    why: Optional[str] = None
    fix_hint: Optional[str] = None
    auto_fix: Optional[Callable[[], bool]] = field(default=None, repr=False)


def _python_check() -> DoctorCheck:
    v = sys.version_info
    ver_str = f"{v.major}.{v.minor}.{v.micro}"
    if (v.major, v.minor) >= MIN_PYTHON:
        return DoctorCheck("Python", "ok", ver_str)
    return DoctorCheck(
        "Python", "warn", ver_str,
        why=f"Kyte targets Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+; older versions may hit "
            "subtle typing/stdlib differences.",
        fix_hint=f"Upgrade to Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]} or newer.",
    )


def _git_installed_check() -> DoctorCheck:
    if git.is_installed():
        return DoctorCheck("Git installation", "ok", "found on PATH")
    return DoctorCheck(
        "Git installation", "fail", "not found",
        why="Kyte shells out to git for every status/diff/commit/push — nothing works without it.",
        fix_hint="Install git (e.g. 'apt install git', 'brew install git') then re-run 'kyte doctor'.",
    )


def _repo_check(root: Path) -> DoctorCheck:
    if git.is_repo(root):
        return DoctorCheck("Current repository", "ok", str(root))
    return DoctorCheck(
        "Current repository", "fail", f"{root} is not a git repository",
        why="Kyte tracks changes and commits through git; without a repo there's nothing to sync.",
        fix_hint="Run 'git init' in this folder, or let Kyte do it for you.",
        auto_fix=lambda: recovery.ensure_git_repo(root),
    )


def _remote_check(root: Path, remote: str) -> DoctorCheck:
    if not git.is_repo(root):
        return DoctorCheck("Remote origin", "warn", "skipped (no repository)")
    if git.has_remote(root, remote):
        url = git.remote_url(root, remote) or "(url unavailable)"
        return DoctorCheck("Remote origin", "ok", url)
    return DoctorCheck(
        "Remote origin", "warn", f"no '{remote}' remote configured",
        why="'/push' and '/pull' need a remote to talk to. You can still commit locally without one.",
        fix_hint=f"Run: git remote add {remote} <url>",
    )


def _branch_check(root: Path, branch: str) -> DoctorCheck:
    if not git.is_repo(root):
        return DoctorCheck("Current branch", "warn", "skipped (no repository)")
    current = git.current_branch(root)
    if current not in ("(none)", "(detached)"):
        return DoctorCheck("Current branch", "ok", current)
    return DoctorCheck(
        "Current branch", "warn", current,
        why="With no branch checked out, commits have nowhere to land.",
        fix_hint=f"Run: git checkout -b {branch}",
        auto_fix=lambda: recovery.ensure_branch(root, branch),
    )


def _ollama_installed_check() -> DoctorCheck:
    if ai.is_ollama_installed():
        return DoctorCheck("Ollama installation", "ok", "found on PATH")
    return DoctorCheck(
        "Ollama installation", "warn", "not found",
        why="Without Ollama, Kyte falls back to template commit messages — everything else still works.",
        fix_hint="Install from https://ollama.com to enable AI commit messages, review, and analysis.",
    )


def _ollama_connectivity_check(cfg_ollama) -> DoctorCheck:
    client = ai.OllamaClient(host=cfg_ollama.host, model=cfg_ollama.commit_model,
                              timeout=cfg_ollama.timeout)
    if client.is_available():
        return DoctorCheck("Ollama connectivity", "ok", cfg_ollama.host)
    if not ai.is_ollama_installed():
        return DoctorCheck("Ollama connectivity", "warn", "skipped (not installed)")
    return DoctorCheck(
        "Ollama connectivity", "warn", f"unreachable at {cfg_ollama.host}",
        why="Ollama is installed but its daemon isn't running, so AI features are unavailable.",
        fix_hint="Run: ollama serve",
    )


def _models_check(cfg_ollama) -> DoctorCheck:
    client = ai.OllamaClient(host=cfg_ollama.host, model=cfg_ollama.commit_model,
                              timeout=cfg_ollama.timeout)
    if not client.is_available():
        return DoctorCheck("Required models", "warn", "skipped (Ollama unreachable)")
    required = [cfg_ollama.commit_model, cfg_ollama.analysis_model, cfg_ollama.review_model]
    required = sorted(set(required))
    missing = ai.missing_models(client, required)
    if not missing:
        return DoctorCheck("Required models", "ok", ", ".join(required))
    return DoctorCheck(
        "Required models", "warn", f"missing: {', '.join(missing)}",
        why="Commit/analysis/review will fall back to templates until these are pulled.",
        fix_hint="Run: ollama pull <model>  (or let Kyte pull it for you)",
        auto_fix=lambda: all(recovery.ensure_model(cfg_ollama, m) for m in missing),
    )


def _config_check(ctx: "AppContext") -> DoctorCheck:
    root = ctx.config.root
    status, detail = config_mod.validate_config(root)
    if status == "valid":
        return DoctorCheck("Configuration", "ok", str(root / config_mod.CONFIG_FILENAME))
    if status == "missing":
        return DoctorCheck(
            "Configuration", "warn", "no .src.py found — using defaults",
            why="Without .src.py, Kyte uses built-in defaults for models, git, and formatting.",
            fix_hint="Run '/config init' to create one.",
            auto_fix=lambda: recovery.ensure_config(ctx),
        )
    return DoctorCheck(
        "Configuration", "fail", detail or "invalid",
        why="Kyte couldn't execute .src.py, so it silently fell back to defaults.",
        fix_hint="Fix the syntax error above, or run '/config init' to reset to defaults.",
        auto_fix=lambda: recovery.ensure_config(ctx),
    )


def _permissions_check(root: Path) -> DoctorCheck:
    if os.access(root, os.W_OK):
        return DoctorCheck("Permissions", "ok", f"{root} is writable")
    return DoctorCheck(
        "Permissions", "fail", f"{root} is not writable",
        why="Kyte needs to write formatted files, .src.py, and .kyte/cache.json here.",
        fix_hint=f"Fix ownership/permissions on {root} (e.g. 'chown' or 'chmod u+w').",
    )


def _repo_state_check(root: Path) -> DoctorCheck:
    if not git.is_repo(root):
        return DoctorCheck("Repository state", "warn", "skipped (no repository)")
    if git.is_locked(root):
        return DoctorCheck(
            "Repository state", "fail", "stale index.lock present",
            why="A previous git process likely crashed mid-operation and left the repo locked; "
                "every git command will fail until the lock is cleared.",
            fix_hint=f"Remove {root / '.git' / 'index.lock'} once you're sure no git process is running.",
        )
    n = len(git.changed_files(root))
    detail = "clean" if n == 0 else f"{n} file(s) with uncommitted changes"
    return DoctorCheck("Repository state", "ok", detail)


def run_doctor(ctx: "AppContext") -> list[DoctorCheck]:
    """Run every check and return the results, in display order."""
    cfg = ctx.config
    return [
        _python_check(),
        _git_installed_check(),
        _repo_check(cfg.root),
        _remote_check(cfg.root, cfg.git.remote),
        _branch_check(cfg.root, cfg.git.branch),
        _ollama_installed_check(),
        _ollama_connectivity_check(cfg.ollama),
        _models_check(cfg.ollama),
        _config_check(ctx),
        _permissions_check(cfg.root),
        _repo_state_check(cfg.root),
    ]


def summarize(checks: list[DoctorCheck]) -> tuple[int, int, int]:
    """Returns (ok_count, warn_count, fail_count)."""
    ok = sum(1 for c in checks if c.status == "ok")
    warn = sum(1 for c in checks if c.status == "warn")
    fail = sum(1 for c in checks if c.status == "fail")
    return ok, warn, fail
