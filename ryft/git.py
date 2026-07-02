"""Git integration. Every git invocation in Ryft goes through `_run()` here —
no other module shells out to the `git` binary directly.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(Exception):
    pass


@dataclass
class FileChange:
    path: str
    status: str  # "M" modified, "A" added, "D" deleted, "?" untracked


def is_installed() -> bool:
    return shutil.which("git") is not None


def _run(args: list[str], cwd: Path, timeout: int = 30, check: bool = True) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=timeout
        )
    except FileNotFoundError as exc:
        raise GitError("git executable not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise GitError(f"git {' '.join(args)} timed out") from exc

    if check and result.returncode != 0:
        raise GitError(result.stderr.strip() or f"git {' '.join(args)} failed")
    # NOTE: only trim trailing newlines here, never the whole string — the
    # porcelain status format has a *significant* leading space on each
    # line (e.g. " M file.py"), which a blanket .strip() would eat.
    return result.stdout.rstrip("\n")


def is_repo(root: Path) -> bool:
    try:
        _run(["rev-parse", "--is-inside-work-tree"], root)
        return True
    except GitError:
        return False


def init(root: Path) -> str:
    return _run(["init"], root)


def current_branch(root: Path) -> str:
    try:
        return _run(["branch", "--show-current"], root).strip() or "(detached)"
    except GitError:
        return "(none)"


def has_remote(root: Path, name: str = "origin") -> bool:
    try:
        remotes = _run(["remote"], root, check=False)
    except GitError:
        return False
    return name in remotes.splitlines()


def remote_url(root: Path, name: str = "origin") -> str | None:
    try:
        url = _run(["remote", "get-url", name], root, check=False).strip()
    except GitError:
        return None
    return url or None


def is_locked(root: Path) -> bool:
    """True if a stale `.git/index.lock` is present — usually means a
    previous git process crashed mid-operation and left the repo stuck."""
    return (root / ".git" / "index.lock").exists()


def branch_exists(root: Path, branch: str) -> bool:
    try:
        _run(["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], root)
        return True
    except GitError:
        return False


def create_branch(root: Path, branch: str) -> str:
    return _run(["checkout", "-b", branch], root)


def changed_files(root: Path) -> list[FileChange]:
    """Parse `git status --porcelain` into a flat list of changed files."""
    try:
        out = _run(["status", "--porcelain"], root)
    except GitError:
        return []
    changes: list[FileChange] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        code = line[:2].strip()
        path = line[3:].strip().strip('"')
        status = "?" if code in ("??", "?") else code[0] if code[0] != " " else code[1]
        changes.append(FileChange(path=path, status=status or "M"))
    return changes


# --- Update these functions in git.py ---

def diff_stat(root: Path) -> list[tuple[str, int, int]]:
    """Returns a summary of changes: [(filepath, additions, deletions), ...]"""
    try:
        # HEAD catches staged + unstaged if we compare against the last commit
        out = _run(["diff", "HEAD", "--numstat", "--no-color"], root, check=False)
    except GitError:
        return []
    
    stats = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            adds = int(parts[0]) if parts[0] != "-" else 0
            dels = int(parts[1]) if parts[1] != "-" else 0
            stats.append((parts[2], adds, dels))
    return stats

def diff_for(root: Path, path: str) -> str:
    """Unified diff for one file — staged + unstaged combined."""
    try:
        staged = _run(["diff", "--cached", "--no-color", "--", path], root, check=False)
        unstaged = _run(["diff", "--no-color", "--", path], root, check=False)
    except GitError:
        return ""
    parts = [p for p in (staged, unstaged) if p.strip()]
    diff = "\n".join(parts)
    if diff:
        return diff
    try:
        # os.devnull rather than a hardcoded "/dev/null" — the latter
        # doesn't exist on Windows (it's "NUL" there).
        return _run(["diff", "--no-index", "--no-color", os.devnull, path], root, check=False)
    except GitError:
        return ""

def full_diff(root: Path) -> str:
    try:
        return _run(["diff", "--no-color"], root, check=False)
    except GitError:
        return ""


def commit_file(root: Path, path: str, message: str) -> str:
    """Stage exactly one file and commit it."""
    # Convert input path to a clean relative path from the root
    # This removes any accidental 'self-clone/' prefix if it's already in the root
    file_path = Path(path)
    if file_path.is_absolute():
        relative_path = file_path.relative_to(root)
    else:
        # If the path already includes the root name, strip it
        relative_path = file_path.relative_to(root.name) if str(file_path).startswith(str(root.name)) else file_path

    # --all ensures deletions are accurately staged
    # We use str(relative_path) to ensure git sees the path relative to the cwd
    _run(["add", "--all", "--", str(relative_path)], root)
    return _run(["commit", "-m", message, "--", str(relative_path)], root)


def push(root: Path, remote: str, branch: str) -> str:
    return _run(["push", remote, branch], root)


def pull(root: Path, remote: str, branch: str) -> str:
    return _run(["pull", remote, branch], root)


def log(root: Path, n: int = 10) -> str:
    return _run(["log", f"-{n}", "--oneline", "--decorate"], root, check=False)
