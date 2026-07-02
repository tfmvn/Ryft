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


def build_context() -> tuple[AppContext, bool]:
    """Build the AppContext, running first-run onboarding if no
    `.src.py` is found anywhere above the current directory.

    Returns (ctx, first_run) — first_run is True only when onboarding
    just created a fresh `.src.py` in this call.
    """
    cwd = Path.cwd()
    first_run = False

    if onboarding.needs_onboarding(cwd):
        cfg, created = onboarding.run_onboarding(cwd)
        first_run = created
    else:
        root = config.find_root(cwd) or cwd
        cfg = config.load_config(root)

    client = _build_ai_client(cfg)
    ctx = AppContext(config=cfg, ai=client, activity=ActivityFeed(), console=None)
    ctx.sync = SyncController(ctx)
    return ctx, first_run


def main() -> None:
    ctx, first_run = build_context()

    if ctx.config.sync.enabled:
        ctx.sync.start()

    argv = sys.argv[1:]
    if argv:
        # Non-interactive: `kyte doctor`, `kyte commit`, `kyte watch fix`, ...
        commands.dispatch(ctx, "/" + " ".join(argv))
        return

    app = ui.KyteApp(ctx, first_run=first_run)
    app.run()


if __name__ == "__main__":
    main()
