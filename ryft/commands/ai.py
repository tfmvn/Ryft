"""AI-facing commands: /analyze, /review, /message, /model.

Each builds the correctly-scoped client via `ai.make_*_client()` (per the
note in ai.py: commit/analysis/review use different models), rather than
the single general-purpose client on `ctx.ai`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from . import register
from .. import ai as ai_mod, git

if TYPE_CHECKING:
    from ..models import AppContext


def _first_changed_file(root) -> str | None:
    changes = git.changed_files(root)
    return changes[0].path if changes else None


@register("analyze", description="AI review of the full project diff")
def cmd_analyze(ctx: "AppContext", args: list[str]) -> None:
    from .. import ui

    cfg = ctx.config
    diff = git.full_diff(cfg.root)
    if not diff.strip():
        ui.success("Working tree is clean — nothing to analyze.")
        return

    files = [c.path for c in git.changed_files(cfg.root)]
    client = ai_mod.make_analysis_client(cfg.ollama)
    with ui.TaskSpinner(ctx, "Analyzing…") as spinner:
        try:
            text = ai_mod.analyze_diff(client, cfg.project.name, files, diff)
        except ai_mod.OllamaError as exc:
            spinner.fail(str(exc))
            return
        spinner.step("Analysis complete")
    ui.render_ai_output(text, "Analysis")


@register(
    "review",
    description="AI code review of one changed file",
    usage=["/review", "/review <file>"],
)
def cmd_review(ctx: "AppContext", args: list[str]) -> None:
    from .. import ui

    cfg = ctx.config
    file = args[0] if args else _first_changed_file(cfg.root)
    if file is None:
        ui.success("Working tree is clean — nothing to review.")
        return

    diff = git.diff_for(cfg.root, file)
    client = ai_mod.make_review_client(cfg.ollama)
    with ui.TaskSpinner(ctx, f"Reviewing {file}…") as spinner:
        try:
            text = ai_mod.review_diff(client, file, diff)
        except ai_mod.OllamaError as exc:
            spinner.fail(str(exc))
            return
        spinner.step("Review complete")
    ui.render_ai_output(text, f"Review · {file}")


@register(
    "message",
    description="Generate a commit message for one file without committing",
    usage=["/message", "/message <file>"],
)
def cmd_message(ctx: "AppContext", args: list[str]) -> None:
    from .. import ui

    cfg = ctx.config
    file = args[0] if args else _first_changed_file(cfg.root)
    if file is None:
        ui.success("Working tree is clean — nothing to message.")
        return

    diff = git.diff_for(cfg.root, file)
    client = ai_mod.make_commit_client(cfg.ollama)
    msg, source = ai_mod.generate_commit_message(
        client,
        cfg.ollama.enabled,
        cfg.git.fallback_commit_message,
        file,
        diff,
        root=cfg.root,
        auto_threshold=cfg.git.small_change_threshold,
        use_auto_small=cfg.git.auto_commit_small_changes,
    )
    ui.info(f"{msg}  ({source})")


@register(
    "model",
    description="List available models or show the current commit model",
    usage=["/model list", "/model current", "/model <name>"],
)
def cmd_model(ctx: "AppContext", args: list[str]) -> None:
    from .. import ui
    from .. import config as config_mod
    from ..recovery import ensure_model

    cfg = ctx.config
    sub = args[0] if args else "current"

    if sub == "current":
        ui.info(cfg.ollama.commit_model)
        return

    if sub == "list":
        client = ai_mod.OllamaClient(
            host=cfg.ollama.host, model=cfg.ollama.commit_model, timeout=cfg.ollama.timeout
        )
        installed = client.list_models()
        ui.render_models(ai_mod.SUPPORTED_MODELS, cfg.ollama.commit_model, installed)
        return

    # Anything else is treated as "switch the commit model to this name".
    model = sub
    config_mod.set_model(cfg, model)
    if ensure_model(cfg.ollama, model):
        ui.success(f"Commit model set to {model}")
    else:
        ui.warn(f"Commit model set to {model}, but it isn't confirmed available yet.")
