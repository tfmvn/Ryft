"""Automatic dependency recovery.

Every "thing that could be missing" (a repo, a config file, a model, a
running Ollama daemon) gets one small `ensure_*` function here. Each one:

  1. checks the precondition
  2. if broken, explains what's wrong and offers to fix it (Y/n)
  3. performs the fix with live feedback
  4. re-validates and reports the result

`kyte doctor` calls these in "fix" mode. Commands that hit a hard
precondition (e.g. /commit with no repo) can call the same function
instead of just failing, so the user is never stranded.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from . import ai, config as config_mod, git, ui

if TYPE_CHECKING:
    from .models import AppContext


def ensure_git_repo(root: Path) -> bool:
    """Ensure *root* is a git repository, offering to `git init` if not."""
    if git.is_repo(root):
        return True
    if not git.is_installed():
        ui.error("git is not installed — install it before Kyte can track changes.")
        return False
    if not ui.confirm(f"No git repository found at {root}. Initialize one now?"):
        return False
    try:
        git.init(root)
    except git.GitError as exc:
        ui.error(f"git init failed: {exc}")
        return False
    ok = git.is_repo(root)
    if ok:
        ui.success("Repository initialized")
    return ok


def ensure_config(ctx: "AppContext") -> bool:
    """Ensure `.src.py` exists, offering to create a default one if not."""
    cfg = ctx.config
    status, _detail = config_mod.validate_config(cfg.root)
    if status == "valid":
        return True

    if status == "invalid":
        if not ui.confirm("Configuration file is invalid. Reset it to defaults?"):
            return False
    else:
        if not ui.confirm("No configuration found. Create one now?"):
            return False

    path = config_mod.init_config(cfg.root, cfg.project.name)
    cfg.path = path
    fresh = config_mod.load_config(cfg.root)
    ctx.config = fresh
    ui.success(f"Configuration written to {path}")
    return True


def ensure_ollama_running(cfg_ollama) -> bool:
    """Best-effort check for a reachable Ollama daemon. We can't start a
    background daemon safely on the user's behalf, so this only guides."""
    client = ai.OllamaClient(host=cfg_ollama.host, model=cfg_ollama.commit_model,
                              timeout=cfg_ollama.timeout)
    if client.is_available():
        return True
    if not ai.is_ollama_installed():
        ui.warn("Ollama isn't installed. AI features will use fallback commit messages.")
        ui.info("Install it from https://ollama.com, then run 'kyte doctor' again.")
        return False
    ui.warn(f"Ollama isn't reachable at {cfg_ollama.host}.")
    ui.info("Start it with: ollama serve")
    return False


def ensure_model(cfg_ollama, model: str) -> bool:
    """Ensure *model* is pulled locally, offering to download it if not."""
    client = ai.OllamaClient(host=cfg_ollama.host, model=model, timeout=cfg_ollama.timeout)
    if not client.is_available():
        return ensure_ollama_running(cfg_ollama)

    missing = ai.missing_models(client, [model])
    if not missing:
        return True

    if not ui.confirm(f"Required model:\n\n    {model}\n\nDownload now?"):
        return False

    ok = ui.run_model_pull(model)
    if not ok:
        ui.error(f"Failed to download {model}. Try 'ollama pull {model}' manually.")
        return False

    client2 = ai.OllamaClient(host=cfg_ollama.host, model=model, timeout=cfg_ollama.timeout)
    installed = model in client2.list_models()
    if installed:
        ui.success(f"{model} is ready.")
    else:
        ui.warn(f"{model} pull finished but the model isn't listed — check 'ollama list'.")
    return installed


def ensure_branch(root: Path, branch: str) -> bool:
    """Ensure the configured branch exists (or that HEAD is on *a* branch)."""
    current = git.current_branch(root)
    if current not in ("(none)", "(detached)"):
        return True
    if git.branch_exists(root, branch):
        return True
    if not ui.confirm(f"No branch checked out. Create and switch to '{branch}' now?"):
        return False
    try:
        git.create_branch(root, branch)
        ui.success(f"Switched to new branch '{branch}'")
        return True
    except git.GitError as exc:
        ui.error(f"Could not create branch: {exc}")
        return False
