"""Entry point: `python3 -m ryft` (also installed as the `ryft` script).

Supports two modes:
  ryft                 → interactive REPL (with first-run onboarding)
  ryft <command> [...]  → run one command non-interactively and exit,
                          e.g. `ryft doctor`, `ryft commit`, `ryft watch`
"""

from __future__ import annotations

import sys
from pathlib import Path

from . import ai, commands, config, onboarding, ui
from .models import AppContext
from .sync import SyncController
from .utils import ActivityFeed


def _build_ai_client(cfg) -> ai.OllamaClient:
    # Primary client — used for availability checks and legacy callers.
    # Commit/analysis/review commands each construct their own client
    # via ai.make_*_client() to use the correct model.
    return ai.OllamaClient(
        host=cfg.ollama.host,
        model=cfg.ollama.commit_model,
        timeout=cfg.ollama.timeout,
    )


_HELP_TEXT = """\
ryft — a calm, fast terminal companion for git

Usage:
  ryft                  interactive session (type /help once inside)
  ryft <command> [args]  run one command and exit, e.g. from a script or CI
  ryft --help, -h        show this help and exit
  ryft --version         show the installed version and exit

Common commands:
  ryft init              set up Ryft in this project
  ryft doctor             health check + auto-repair ('ryft doctor fix')
  ryft commit              commit changed files with an AI-written message
  ryft watch               watch this folder and auto-commit on save
  ryft push  / ryft pull   publish or fetch

Run 'ryft' with no arguments and type /help for the full command list.
"""


def _print_help() -> None:
    print(_HELP_TEXT)


def _print_version() -> None:
    from . import __version__
    print(f"ryft {__version__}")


def build_context(interactive: bool = True, quiet: bool = False) -> tuple[AppContext, bool]:
    """Build the AppContext, running first-run onboarding if no
    `.src.py` is found anywhere above the current directory.

    *interactive* controls what happens when no config exists yet:
      - True  (the bare `ryft` REPL): run the full onboarding walkthrough.
      - False (a one-shot `ryft <command>`, e.g. from a script or CI):
        proceed on in-memory defaults instead of prompting for input,
        since there's no guarantee stdin is attached to a human. Use
        `ryft init` to run onboarding explicitly.

    *quiet* suppresses the "using defaults" notice in the non-interactive
    path — used when the command about to run is `ryft init` itself,
    which explains the situation on its own terms.

    Returns (ctx, first_run) — first_run is True only when onboarding
    just created a fresh `.src.py` in this call.
    """
    cwd = Path.cwd()
    first_run = False

    if onboarding.needs_onboarding(cwd):
        if interactive:
            cfg, created = onboarding.run_onboarding(cwd)
            first_run = created
        else:
            cfg = config.load_config(cwd)
            if not quiet:
                ui.info("No .src.py found — using defaults. Run 'ryft init' to set one up.")
    else:
        root = config.find_root(cwd) or cwd
        cfg = config.load_config(root)

    client = _build_ai_client(cfg)
    ctx = AppContext(config=cfg, ai=client, activity=ActivityFeed(), console=None)
    ctx.sync = SyncController(ctx)
    return ctx, first_run


def main() -> None:
    argv = sys.argv[1:]

    # --help/--version short-circuit before touching the project at all —
    # these shouldn't require a git repo, a config file, or onboarding.
    if argv and argv[0] in ("--help", "-h", "help"):
        _print_help()
        return
    if argv and argv[0] in ("--version", "-V"):
        _print_version()
        return

    # Bare `ryft` starts the interactive REPL, so onboarding can be a full
    # walkthrough. `ryft <command>` runs once and exits — it may be called
    # from a script or CI, so it shouldn't block waiting on a prompt.
    # `ryft init` is the one exception: it's an explicit request to run
    # onboarding, so it handles that conversation itself (see cmd_init).
    is_init = bool(argv) and argv[0].lower() == "init"
    ctx, first_run = build_context(interactive=not argv, quiet=is_init)

    if ctx.config.sync.enabled:
        ctx.sync.start()

    if argv:
        # Non-interactive: `ryft doctor`, `ryft commit`, `ryft watch fix`, ...
        # Dispatched from argv directly (not re-joined into a string) so
        # arguments containing spaces, e.g. a quoted filename, survive.
        commands.dispatch_argv(ctx, argv)
        return

    app = ui.RyftApp(ctx, first_run=first_run)
    app.run()


if __name__ == "__main__":
    main()
