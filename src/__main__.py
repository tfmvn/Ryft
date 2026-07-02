"""Entry point: `python3 -m pm`"""

from __future__ import annotations
from pathlib import Path

from . import ai, config, ui
from .models import AppContext
from .sync import SyncController
from .utils import ActivityFeed


def build_context() -> AppContext:
    root = config.find_root() or Path.cwd()
    cfg  = config.load_config(root)

    # Primary client — used for availability checks and legacy callers.
    # Commit/analysis/review commands each construct their own client
    # via ai.make_*_client() to use the correct model.
    client = ai.OllamaClient(
        host=cfg.ollama.host,
        model=cfg.ollama.commit_model,
        timeout=cfg.ollama.timeout,
    )
    ctx = AppContext(config=cfg, ai=client, activity=ActivityFeed(), console=None)
    ctx.sync = SyncController(ctx)
    return ctx


def main() -> None:
    ctx = build_context()

    if ctx.config.sync.enabled:
        ctx.sync.start()

    app = ui.PMApp(ctx)
    app.run()


if __name__ == "__main__":
    main()