"""Git-facing commands: commit, push, pull, diff, log, status, and the
unified /git dispatcher.

/commit is the one non-trivial handler here: it drives `CommitPipeline`
(scan -> format -> diff -> AI message -> commit) with a live tree view,
generating commit messages for multiple files in parallel via
`cfg.ollama.commit_workers` threads, matching the docstring in ai.py
("Parallel generation via ThreadPoolExecutor, called from commands.py").
Commits themselves are still applied one at a time, sequentially -- git
doesn't support concurrent commits against the same working tree.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

from . import register
from .. import git
from ..pipeline import CommitPipeline

if TYPE_CHECKING:
    from ..models import AppContext


def _selected_files(pipeline: CommitPipeline, args: list[str]) -> list[str]:
    changes = pipeline.scan(refresh=True)
    if not args:
        return [c.path for c in changes]
    wanted = set(args)
    return [c.path for c in changes if c.path in wanted]


@register(
    "commit",
    description="Commit changed files with an AI-written message",
    usage=["/commit", "/commit <file> [file ...]"],
    examples=["/commit", "/commit src/app.py"],
)
def cmd_commit(ctx: "AppContext", args: list[str]) -> None:
    from .. import ui

    cfg = ctx.config
    if not git.is_repo(cfg.root):
        from ..recovery import ensure_git_repo
        if not ensure_git_repo(cfg.root):
            return

    pipeline = CommitPipeline(cfg)
    files = _selected_files(pipeline, args)
    if not files:
        ui.success("Working tree is clean.")
        return

    messages: dict[str, str] = {}
    sources: dict[str, str] = {}

    with ui.LiveCommitView(ctx, files) as view:
        # "target" is just file selection -- instant.
        for f in files:
            view.set_stage(f, "target", "done")

        for f in files:
            view.set_stage(f, "format", "active")
            _changed, err = pipeline.format_file(f)
            view.set_stage(f, "format", "error" if err else "done")

        # Formatting can change diffs, so refresh before reading them.
        pipeline.scan(refresh=True)

        for f in files:
            view.set_stage(f, "message", "active")

        def _generate(f: str) -> tuple[str, str, str]:
            diff = pipeline.diff_for(f)
            msg, source = pipeline.generate_message(f, diff)
            return f, msg, source

        workers = max(1, cfg.ollama.commit_workers)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for f, msg, source in pool.map(_generate, files):
                messages[f], sources[f] = msg, source
                view.set_stage(f, "message", "done")

        committed: list[str] = []
        for f in files:
            view.set_stage(f, "commit", "active")
            try:
                pipeline.commit(f, messages[f])
            except git.GitError as exc:
                view.set_stage(f, "commit", "error")
                view.set_file_state(f, "error", str(exc))
                ui.log_activity(ctx, f"Commit failed on {f}: {exc}", "error")
                continue
            view.set_stage(f, "commit", "done")
            view.set_file_state(f, "done", messages[f])
            committed.append(f)

    for f in committed:
        tag = "" if sources.get(f) == "ollama" else f" ({sources[f]})"
        ui.log_activity(ctx, f"Committed {f}: {messages[f]}{tag}", "success")


@register(
    "push",
    description="Push committed changes to the remote",
    usage=["/push", "/push <remote> <branch>"],
)
def cmd_push(ctx: "AppContext", args: list[str]) -> None:
    from .. import ui

    cfg = ctx.config
    if not git.is_repo(cfg.root):
        ui.error("Not a git repository.")
        return
    remote = args[0] if len(args) >= 1 else cfg.git.remote
    branch = args[1] if len(args) >= 2 else cfg.git.branch

    with ui.LivePushView(ctx, remote, branch) as view:
        for stage in ("pack", "delta", "write"):
            view.set_stage(stage, "active")
            view.set_stage(stage, "done")
        view.set_stage("push", "active")
        try:
            git.push(cfg.root, remote, branch)
        except git.GitError as exc:
            view.set_stage("push", "error")
            view.finish(False, str(exc))
            ui.log_activity(ctx, f"Push failed: {exc}", "error")
            return
        view.set_stage("push", "done")
        view.finish(True, "done")

    ui.log_activity(ctx, f"Pushed to {remote}/{branch}", "success")


@register(
    "pull",
    description="Pull the latest changes from the remote",
    usage=["/pull", "/pull <remote> <branch>"],
)
def cmd_pull(ctx: "AppContext", args: list[str]) -> None:
    from .. import ui

    cfg = ctx.config
    if not git.is_repo(cfg.root):
        ui.error("Not a git repository.")
        return
    remote = args[0] if len(args) >= 1 else cfg.git.remote
    branch = args[1] if len(args) >= 2 else cfg.git.branch

    with ui.TaskSpinner(ctx, f"Pulling {remote}/{branch}…") as spinner:
        try:
            git.pull(cfg.root, remote, branch)
        except git.GitError as exc:
            spinner.fail(f"Pull failed: {exc}")
            return
        spinner.step(f"Pulled {remote}/{branch}")


@register(
    "diff",
    description="Show a diff -- summary for all files, or one file in detail",
    usage=["/diff", "/diff <file>"],
)
def cmd_diff(ctx: "AppContext", args: list[str]) -> None:
    from .. import ui

    cfg = ctx.config
    if args:
        file = args[0]
        diff = git.diff_for(cfg.root, file)
        ui.render_file_diff(file, diff)
    else:
        ui.render_diff_summary(git.diff_stat(cfg.root))


@register("log", description="Show recent commit history")
def cmd_log(ctx: "AppContext", args: list[str]) -> None:
    from .. import ui

    n = 10
    if args and args[0].isdigit():
        n = int(args[0])
    text = git.log(ctx.config.root, n)
    ui.render_text("log", text or "(no commits yet)")


@register("status", description="Show project + repository status")
def cmd_status(ctx: "AppContext", args: list[str]) -> None:
    from ..commands import REGISTRY
    from ..ui.tui.dashboard import build_dashboard
    from rich.console import Console

    Console().print(build_dashboard(ctx, list(REGISTRY.values())))


_GIT_SUBCOMMANDS = {
    "status": cmd_status,
    "diff": cmd_diff,
    "log": cmd_log,
    "push": cmd_push,
    "pull": cmd_pull,
    "commit": cmd_commit,
}


@register(
    "git",
    description="Run a git-flavored subcommand (status/diff/log/push/pull/commit)",
    usage=["/git <status|diff|log|push|pull|commit> [args...]"],
    examples=["/git status", "/git diff src/app.py"],
)
def cmd_git(ctx: "AppContext", args: list[str]) -> None:
    from .. import ui

    if not args:
        ui.error("usage: /git <status|diff|log|push|pull|commit> [args...]")
        return
    sub, rest = args[0], args[1:]
    handler = _GIT_SUBCOMMANDS.get(sub)
    if handler is None:
        ui.error(f"Unknown /git subcommand: {sub}")
        return
    handler(ctx, rest)
