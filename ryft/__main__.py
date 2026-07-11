"""Entry point: ``python -m ryft`` (also installed as the ``ryft`` script).

Two modes:
  ryft                 → interactive TUI (dashboard, command palette, diff/commit
                         review viewers). Background services start automatically.
  ryft <command> [...] → run one command non-interactively and exit, e.g.
                         ``ryft doctor``, ``ryft commit``, ``ryft ask "..."``

The single source of context construction is :func:`ryft.core.lifecycle.build_context`;
nothing else decides how the runtime is wired.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .core.lifecycle import build_context
from .logging_setup import configure_logging


_HELP_TEXT = """\
ryft — the AI-native command center for software projects

Usage:
  ryft                  start the interactive terminal UI (dashboard)
  ryft <command> [args] run one command and exit (CI / scripts)
  ryft --help, -h        show this help
  ryft --version         show version

Command groups:
  ai        ask  search  explain  review
  git       commit  sync  graph  timeline
  ops       doctor  release  plugins  providers  config
  knowledge memory  sessions
  ui        dashboard  help

Run 'ryft help' (inside the TUI) or 'ryft <command> --help' for details.
"""


def _print_help() -> None:
    print(_HELP_TEXT)


def _print_version() -> None:
    from . import __version__
    print(f"ryft {__version__}")


def _run_tui(ctx) -> None:
    from .commands import REGISTRY
    from .ui.tui import RyftTUI

    app = RyftTUI(ctx, list(REGISTRY.values()))
    try:
        app.run()
    finally:
        from .core.lifecycle import shutdown

        shutdown(ctx)


def main() -> None:
    argv = sys.argv[1:]

    # These never touch the project — no config, no git, no onboarding.
    if argv and argv[0] in ("--help", "-h", "help"):
        _print_help()
        return
    if argv and argv[0] in ("--version", "-V"):
        _print_version()
        return

    is_init = bool(argv) and argv[0].lower() == "init"

    # One-shot commands and `init` stay lightweight (no background workers);
    # the bare TUI starts the service manager for live git/index monitoring.
    ctx = build_context(start_services=not argv)
    configure_logging(ctx.config.root)

    if argv:
        from .commands import dispatch_argv

        dispatch_argv(ctx, argv)
        return

    _run_tui(ctx)


if __name__ == "__main__":
    main()
