"""Entry point: `python3 -m kyte` (also installed as the `kyte` script).

Supports two modes:
  kyte                 → interactive REPL (with first-run onboarding)
  kyte <command> [...]  → run one command non-interactively and exit,
                          e.g. `kyte doctor`, `kyte commit`, `kyte watch`
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
kyte — a calm, fast terminal companion for git

Usage:
  kyte                  interactive session (type /help once inside)
  kyte <command> [args]  run one command and exit, e.g. from a script or CI
  kyte --help, -h        show this help and exit
  kyte --version         show the installed version and exit

Common commands:
  kyte init              set up Kyte in this project
  kyte doctor             health check + auto-repair ('kyte doctor fix')
  kyte commit              commit changed files with an AI-written message
  kyte watch               watch this folder and auto-commit on save
  kyte push  / kyte pull   publish or fetch

Run 'kyte' with no arguments and type /help for the full command list.
"""


def _print_help() -> None:
    print(_HELP_TEXT)


def _print_version() -> None:
    from . import __version__
    print(f"kyte {__version__}")


def build_context(interactive: bool = True, quiet: bool = False) -> tuple[AppContext, bool]:
    """Build the AppContext, running first-run onboarding if no
    `.src.py` is found anywhere above the current directory.

    *interactive* controls what happens when no config exists yet:
      - True  (the bare `kyte` REPL): run the full onboarding walkthrough.
      - False (a one-shot `kyte <command>`, e.g. from a script or CI):
        proceed on in-memory defaults instead of prompting for input,
        since there's no guarantee stdin is attached to a human. Use
        `kyte init` to run onboarding explicitly.

    *quiet* suppresses the "using defaults" notice in the non-interactive
    path — used when the command about to run is `kyte init` itself,
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
                ui.info("No .src.py found — using defaults. Run 'kyte init' to set one up.")
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

    # Bare `kyte` starts the interactive REPL, so onboarding can be a full
    # walkthrough. `kyte <command>` runs once and exits — it may be called
    # from a script or CI, so it shouldn't block waiting on a prompt.
    # `kyte init` is the one exception: it's an explicit request to run
    # onboarding, so it handles that conversation itself (see cmd_init).
    is_init = bool(argv) and argv[0].lower() == "init"
    ctx, first_run = build_context(interactive=not argv, quiet=is_init)

    if ctx.config.sync.enabled:
        ctx.sync.start()

    if argv:
        # Non-interactive: `kyte doctor`, `kyte commit`, `kyte watch fix`, ...
        # Dispatched from argv directly (not re-joined into a string) so
        # arguments containing spaces, e.g. a quoted filename, survive.
        commands.dispatch_argv(ctx, argv)
        return

    app = ui.KyteApp(ctx, first_run=first_run)
    app.run()


if __name__ == "__main__":
    main()
