"""The command registry."""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from rich.tree import Tree  # type: ignore[import]

from . import ai, config as config_mod, doctor as doctor_mod, formatter, git, onboarding, recovery, ui
from .config import DEFAULT_IGNORE
from .models import CommandSpec
from .pipeline import CommitPipeline
from .utils import discover_files, human_path

logger = logging.getLogger(__name__)

# In src/commands.py
SUPPORTED_SUFFIXES = {".py", ".lua"}

# # # Decrypted from ryft/formatter.py:
# # In cmd_format()
# files = discover_files(cfg.root, cfg.ignore, suffixes=SUPPORTED_SUFFIXES)

# ---------------------------------------------------------------------------
# Help / status / exit
# ---------------------------------------------------------------------------

def cmd_help(ctx, args: list[str]) -> None:
    if args:
        name = args[0].lstrip("/")
        spec = COMMANDS.get(name)
        if spec is None:
            ui.error(f"No such command: /{name}")
            return
        ui.render_help_command(spec)
    else:
        ui.render_help_index(COMMANDS)

def cmd_status(ctx, args: list[str]) -> None:
    ui.render_dashboard(ctx)

def cmd_activity(ctx, args: list[str]) -> None:
    ui.render_activity_full(ctx)

def cmd_exit(ctx, args: list[str]) -> None:
    if ctx.sync and ctx.sync.is_running:
        ctx.sync.stop()
    ctx.running = False

# ---------------------------------------------------------------------------
# Sync & Formatter
# ---------------------------------------------------------------------------

def cmd_watch(ctx, args: list[str]) -> None:
    """Foreground sync: watch this folder and auto-commit on save until
    interrupted. This is what `ryft watch` runs from the shell."""
    cfg = ctx.config
    if not git.is_repo(cfg.root) and not recovery.ensure_git_repo(cfg.root):
        ui.warn("Watch needs a git repository. Run '/doctor fix' when you're ready.")
        return

    msg = ctx.sync.start()
    if not ctx.sync.is_running:
        ui.error(msg)
        return
    ui.success(f"Watching {cfg.root} — press Ctrl+C to stop.")
    try:
        while ctx.sync.is_running:
            import time as _time
            _time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        ui.warn(ctx.sync.stop())


def cmd_sync(ctx, args: list[str]) -> None:
    sub = args[0] if args else "status"
    if sub == "start":
        cfg = ctx.config
        if not git.is_repo(cfg.root) and not recovery.ensure_git_repo(cfg.root):
            ui.warn("Sync needs a git repository. Run '/doctor fix' when you're ready.")
            return
        if cfg.sync.debounce_seconds < 10:
            ui.warn(f"debounce_seconds={cfg.sync.debounce_seconds} is very low — may generate many commits.")
        msg = ctx.sync.start()
        (ui.success if ctx.sync.is_running else ui.warn)(msg)
    elif sub == "stop":
        ui.warn(ctx.sync.stop())
    elif sub == "status":
        state = "running" if ctx.sync.is_running else "stopped"
        ui.info(f"Sync is {state} (debounce {ctx.config.sync.debounce_seconds}s, push={ctx.config.sync.push})")
    else:
        ui.error("Usage: /sync start|stop|status")

def cmd_format(ctx, args: list[str]) -> None:
    cfg = ctx.config  # cfg is now defined here
    target = args[0] if args else "."

    with ui.TaskSpinner(ctx, "Scanning repository…") as spin:
        if target == "changed":
            files = [cfg.root / c.path for c in git.changed_files(cfg.root) if (cfg.root / c.path).exists()]
        elif target == ".":
            # Now it is safe to use cfg.root and cfg.ignore
            files = discover_files(cfg.root, cfg.ignore, suffixes=SUPPORTED_SUFFIXES)
        else:
            p = Path(target)
            files = [p if p.is_absolute() else cfg.root / target]
        spin.step(f"Found {len(files)} file(s)")

        spin.start("Formatting files…")
        changed = formatter.format_paths(files, cfg.formatter.max_blank_lines, cfg.formatter.remove_comments)

    for f in changed:
        ui.log_activity(ctx, f"Formatted {human_path(f, cfg.root)}", "info")

    if changed:
        ui.success(f"Formatted {len(changed)} file(s) (Python and Lua).")
    else:
        ui.info("Nothing to format.")
# ---------------------------------------------------------------------------
# AI
# ---------------------------------------------------------------------------

def cmd_analyze(ctx, args: list[str]) -> None:
    cfg = ctx.config
    files = [c.path for c in git.changed_files(cfg.root)]
    diff = git.full_diff(cfg.root)
    if not diff.strip():
        ui.info("Nothing to analyze — no local changes.")
        return

    # Use analysis_model (large model)
    client = ai.make_analysis_client(cfg.ollama)
    with ui.TaskSpinner(ctx, "Analyzing changes…") as spin:
        try:
            result = ai.analyze_diff(client, cfg.project.name, files, diff)
            spin.step("Analysis complete")
        except ai.OllamaError as exc:
            spin.fail(str(exc))
            return

    ui.render_ai_output(result, "Project Analysis")

def cmd_review(ctx, args: list[str]) -> None:
    cfg = ctx.config
    file = args[0] if args else None
    diff = git.diff_for(cfg.root, file) if file else git.full_diff(cfg.root)
    label = file or "(all changes)"
    if not diff.strip():
        ui.info(f"Nothing to review for {label}.")
        return

    # Use review_model (large model)
    client = ai.make_review_client(cfg.ollama)
    with ui.TaskSpinner(ctx, f"Reviewing {label}…") as spin:
        try:
            result = ai.review_diff(client, label, diff)
            spin.step("Review generated")
        except ai.OllamaError as exc:
            spin.fail(str(exc))
            return

    ui.render_ai_output(result, title=f"Review: {label}")

def cmd_message(ctx, args: list[str]) -> None:
    cfg = ctx.config
    if not args:
        ui.error("Usage: /message <file>")
        return
    file = args[0]
    pipeline = CommitPipeline(cfg)
    diff = pipeline.diff_for(file)
    if not diff.strip():
        ui.info(f"No changes in {file}.")
        return

    with ui.TaskSpinner(ctx, f"Generating message for {file}…") as spin:
        message, source = pipeline.generate_message(file, diff)
        spin.step("Message generated")

    ui.info(f"{message}  [via {source}]")

def cmd_model(ctx, args: list[str]) -> None:
    cfg = ctx.config
    sub = args[0] if args else "current"
    if sub == "list":
        installed = ctx.ai.list_models()
        ui.render_models(ai.SUPPORTED_MODELS, cfg.ollama.commit_model, installed)
    elif sub == "current":
        ui.info(
            f"commit={cfg.ollama.commit_model}  "
            f"analysis={cfg.ollama.analysis_model}  "
            f"review={cfg.ollama.review_model}"
        )
    else:
        config_mod.set_model(cfg, sub)
        ui.success(f"Commit model set to {sub}")

# ---------------------------------------------------------------------------
# Git — commit (parallel message generation + live tree)
# ---------------------------------------------------------------------------

def _generate_message_for(pipeline: CommitPipeline, fname: str, diff: str) -> tuple[str, str, str]:
    """Worker: returns (fname, message, source). Runs in a thread pool."""
    message, source = pipeline.generate_message(fname, diff)
    return fname, message, source


def _do_commit(ctx) -> None:
    cfg  = ctx.config
    root = cfg.root

    if not git.is_repo(root):
        if not recovery.ensure_git_repo(root):
            ui.warn("Commit needs a git repository. Run '/doctor fix' when you're ready.")
            return

    pipeline = CommitPipeline(cfg)

    # ── 1. collect changed files ──────────────────────────────────────────────
    with ui.TaskSpinner(ctx, "Scanning for changes…"):
        changes = pipeline.scan()

    if not changes:
        ui.info("Nothing to commit.")
        return

    filenames  = [c.path for c in changes]
    workers    = max(1, min(cfg.ollama.commit_workers, len(filenames)))

    # ── 2. pre-fetch all diffs (fast, serial git calls) ───────────────────────
    diffs: dict[str, str] = {}
    with ui.TaskSpinner(ctx, "Reading diffs…"):
        for fname in filenames:
            diffs[fname] = pipeline.diff_for(fname)

    # ── 3. format all files first (fast, no AI) ───────────────────────────────
    if cfg.formatter.enabled:
        with ui.TaskSpinner(ctx, "Formatting…"):
            for fname in filenames:
                _changed, fmt_error = pipeline.format_file(fname)
                if fmt_error:
                    logger.warning("Format failed on %s during commit: %s", fname, fmt_error)

    # ── 4. parallel message generation + live tree UI ────────────────────────
    # messages dict is populated as futures complete
    messages: dict[str, tuple[str, str]] = {}  # fname -> (message, source)
    success_count = 0

    with ui.LiveCommitView(ctx, filenames) as view:

        # Stage all as "summarize" active → done immediately (it's local, instant)
        for fname in filenames:
            view.set_stage(fname, "target", "active")
        for fname in filenames:
            view.set_stage(fname, "target", "done")

        # ── parallel message generation ───────────────────────────────────────
        # Mark all as "message/generating" before submitting so the tree
        # shows all files generating at once
        for fname in filenames:
            view.set_stage(fname, "format", "done")   # already formatted above
            view.set_stage(fname, "message", "active")

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_generate_message_for, pipeline, fname, diffs[fname]): fname
                for fname in filenames
            }
            for future in as_completed(futures):
                fname_done, message, source = future.result()
                messages[fname_done] = (message, source)
                view.set_stage(fname_done, "message", "done")

        # ── serial commits (git requires sequential staging) ──────────────────
        for fname in filenames:
            message, source = messages.get(fname, (
                cfg.git.fallback_commit_message.format(file=fname), "fallback"
            ))
            view.set_stage(fname, "commit", "active")
            try:
                pipeline.commit(fname, message)
                tag = "" if source == "ollama" else f" ({source})"
                ctx.activity.add(f"Committed {fname}: {message}{tag}", "success")
                view.set_stage(fname, "commit", "done")
                view.set_file_state(fname, "done", message)
                success_count += 1
            except git.GitError as exc:
                view.set_stage(fname, "commit", "error")
                ctx.activity.add(f"Commit failed on {fname}: {exc}", "error")
                view.set_file_state(fname, "error", str(exc))

    ui.info(f"{success_count}/{len(filenames)} committed.  Run /push to publish.")


# ---------------------------------------------------------------------------
# Git — push
# ---------------------------------------------------------------------------

def _do_push(ctx) -> None:
    import time as _time
    cfg    = ctx.config
    remote = cfg.git.remote
    branch = cfg.git.branch
    pipeline = CommitPipeline(cfg)

    result: dict = {}

    def _run_push():
        try:
            result["out"] = pipeline.push()
            result["ok"]  = True
        except git.GitError as exc:
            result["err"] = str(exc)
            result["ok"]  = False

    with ui.LivePushView(ctx, remote, branch) as view:
        push_thread = threading.Thread(target=_run_push, daemon=True)
        push_thread.start()

        view.set_stage("pack", "active")
        _time.sleep(0.25)
        view.set_stage("pack", "done")

        view.set_stage("delta", "active")
        _time.sleep(0.35)
        view.set_stage("delta", "done")

        view.set_stage("write", "active", "writing objects…")
        push_thread.join()
        view.set_stage("write", "done")

        if result.get("ok"):
            view.set_stage("push", "active", "updating remote refs…")
            _time.sleep(0.15)
            view.set_stage("push", "done")
            view.finish(ok=True, msg=f"→ {remote}/{branch}")
            ctx.activity.add(f"Pushed to {remote}/{branch}", "success")
        else:
            view.set_stage("push", "error")
            view.finish(ok=False, msg=result.get("err", "push failed"))
            ctx.activity.add(f"Push failed: {result.get('err', '')}", "error")


def _do_pull(ctx) -> None:
    cfg = ctx.config
    try:
        out = git.pull(cfg.root, cfg.git.remote, cfg.git.branch)
        ui.success(out or "Already up to date.")
    except git.GitError as exc:
        ui.error(str(exc))

def _do_diff(ctx, args: list[str]) -> None:
    cfg = ctx.config
    if args:
        file_path = args[0]
        text = git.diff_for(cfg.root, file_path)
        if not text.strip():
            ui.info(f"No differences in {file_path}.")
            return
        ui.render_file_diff(file_path, text)
    else:
        stats = git.diff_stat(cfg.root)
        if not stats:
            ui.info("Working tree is clean.")
            return
        ui.render_diff_summary(stats)

def _do_log(ctx) -> None:
    out = git.log(ctx.config.root)
    ui.render_text("Git Log", out or "No commits yet.")

def _do_status(ctx) -> None:
    changes = CommitPipeline(ctx.config).scan()
    ui.render_git_changes(changes)

def cmd_commit(ctx, args: list[str]) -> None: _do_commit(ctx)
def cmd_push(ctx, args: list[str]) -> None: _do_push(ctx)
def cmd_pull(ctx, args: list[str]) -> None: _do_pull(ctx)
def cmd_diff(ctx, args: list[str]) -> None: _do_diff(ctx, args)
def cmd_log(ctx, args: list[str]) -> None: _do_log(ctx)

def cmd_git(ctx, args: list[str]) -> None:
    if not args:
        ui.error("Usage: /git status|diff|log|push|pull")
        return
    sub, rest = args[0], args[1:]
    {
        "status": lambda: _do_status(ctx),
        "diff":   lambda: _do_diff(ctx, rest),
        "log":    lambda: _do_log(ctx),
        "push":   lambda: _do_push(ctx),
        "pull":   lambda: _do_pull(ctx),
        "commit": lambda: _do_commit(ctx),
    }.get(sub, lambda: ui.error(f"Unknown git subcommand: {sub}"))()

# ---------------------------------------------------------------------------
# Project
# ---------------------------------------------------------------------------

def cmd_doctor(ctx, args: list[str]) -> None:
    fix = bool(args) and args[0] == "fix"

    with ui.TaskSpinner(ctx, "Running health checks…") as spin:
        checks = doctor_mod.run_doctor(ctx)
        spin.step("Health checks complete")

    ui.render_doctor(checks)

    if not fix:
        _, warn, fail = doctor_mod.summarize(checks)
        if warn or fail:
            ui.info("Run '/doctor fix' to walk through repairing these automatically.")
        return

    fixable = [c for c in checks if c.status != "ok" and c.auto_fix is not None]
    if not fixable:
        ui.info("Nothing auto-fixable — see the guidance above for anything else.")
        return

    fixed = 0
    for check in fixable:
        ui.info(f"Fixing: {check.name}")
        try:
            ok = check.auto_fix()
        except Exception as exc:
            # auto_fix callables come from a heterogeneous set of
            # recovery.ensure_* helpers (git init, branch creation, model
            # pulls, config writes, ...) — there's no single expected
            # exception type to narrow to here, so this stays a catch-all,
            # but it's logged rather than only shown once and discarded.
            logger.exception("Doctor auto-fix failed for %s", check.name)
            ui.error(f"{check.name}: fix failed — {exc}")
            continue
        if ok:
            fixed += 1
            ctx.activity.add(f"Doctor fixed: {check.name}", "success")
        else:
            ui.warn(f"{check.name}: skipped or still unresolved.")

    ui.success(f"Fixed {fixed}/{len(fixable)} issue(s). Run '/doctor' again to confirm.")

def cmd_init(ctx, args: list[str]) -> None:
    """Explicit onboarding entry point (`ryft init` / `/init`).

    Safe to run repeatedly: if a valid `.src.py` already exists, this
    just says so and stops — it never overwrites configuration without
    an explicit confirmation.
    """
    root = ctx.config.root
    status, detail = config_mod.validate_config(root)

    if status == "valid":
        ui.info(f"Ryft is already initialized here ({root / config_mod.CONFIG_FILENAME}).")
        if not ui.confirm("Reset configuration to defaults anyway?", default=False):
            return
    elif status == "invalid":
        ui.warn(f"A .src.py exists but is invalid: {detail}")
        if not ui.confirm("Reset it to defaults?", default=True):
            return

    cfg, created = onboarding.run_onboarding(root)
    ctx.config = cfg
    if created:
        ui.render_completion_screen(cfg.project.name)

def cmd_config(ctx, args: list[str]) -> None:
    cfg = ctx.config
    if args and args[0] == "init":
        path = config_mod.init_config(cfg.root, cfg.project.name)
        cfg.path = path
        ui.success(f"Initialized configuration at {path}")
        return
    if cfg.path and cfg.path.exists():
        ui.render_code(f"Configuration ({cfg.path.name})", cfg.path.read_text(encoding="utf-8"), "python")
    else:
        ui.warn("No .src.py file found. Using defaults. Run '/config init' to create one.")

def cmd_tree(ctx, args: list[str]) -> None:
    cfg = ctx.config
    root_node = Tree(f"[bold]{cfg.root.name}[/bold]")

    def add(node: Tree, path: Path, depth: int) -> None:
        if depth > 3: return
        try:
            entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except OSError: return
        for entry in entries:
            if entry.name in DEFAULT_IGNORE or entry.name in cfg.ignore or entry.name.startswith("."):
                continue
            if entry.is_dir():
                branch = node.add(f"[bold cyan]{entry.name}/[/bold cyan]")
                add(branch, entry, depth + 1)
            else:
                node.add(entry.name)

    add(root_node, cfg.root, 0)
    ui.render_tree(root_node)

def cmd_files(ctx, args: list[str]) -> None:
    cfg = ctx.config
    files = discover_files(cfg.root, cfg.ignore)
    ui.render_files([human_path(f, cfg.root) for f in files])

def cmd_root(ctx, args: list[str]) -> None:
    ui.info(str(ctx.config.root))

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

COMMANDS: dict[str, CommandSpec] = {
    "help":     CommandSpec("help",     cmd_help,     "Show available commands.",        usage=["/help"]),
    "status":   CommandSpec("status",   cmd_status,   "Show project status.",            usage=["/status"]),
    "activity": CommandSpec("activity", cmd_activity, "Show the activity feed.",         usage=["/activity"]),
    "sync":     CommandSpec("sync",     cmd_sync,     "Start/stop sync.",                usage=["/sync start|stop"]),
    "watch":    CommandSpec("watch",    cmd_watch,    "Watch this folder and auto-commit.", usage=["/watch", "ryft watch"]),
    "format":   CommandSpec("format",   cmd_format,   "Format files.",                   usage=["/format .", "/format changed"]),
    "analyze":  CommandSpec("analyze",  cmd_analyze,  "AI summary of changes.",          usage=["/analyze"]),
    "review":   CommandSpec("review",   cmd_review,   "AI code review.",                 usage=["/review", "/review <file>"]),
    "message":  CommandSpec("message",  cmd_message,  "Preview AI commit message.",      usage=["/message <file>"]),
    "model":    CommandSpec("model",    cmd_model,    "Show/switch models.",             usage=["/model list", "/model <name>"]),
    "git":      CommandSpec("git",      cmd_git,      "Run a git subcommand.",           usage=["/git status|diff|log|push"]),
    "commit":   CommandSpec("commit",   cmd_commit,   "Commit changed files with AI.",   usage=["/commit"]),
    "push":     CommandSpec("push",     cmd_push,     "Push commits.",                   usage=["/push"]),
    "pull":     CommandSpec("pull",     cmd_pull,     "Pull commits.",                   usage=["/pull"]),
    "diff":     CommandSpec("diff",     cmd_diff,     "Show a diff.",                    usage=["/diff", "/diff <file>"]),
    "log":      CommandSpec("log",      cmd_log,      "Show recent commits.",            usage=["/log"]),
    "init":     CommandSpec("init",     cmd_init,     "Set up Ryft in this project.",    usage=["/init", "ryft init"]),
    "doctor":   CommandSpec("doctor",   cmd_doctor,   "Run health checks.",              usage=["/doctor", "/doctor fix"]),
    "config":   CommandSpec("config",   cmd_config,   "Show config.",                    usage=["/config", "/config init"]),
    "tree":     CommandSpec("tree",     cmd_tree,     "Show project tree.",              usage=["/tree"]),
    "files":    CommandSpec("files",    cmd_files,    "List tracked files.",             usage=["/files"]),
    "root":     CommandSpec("root",     cmd_root,     "Show project root.",              usage=["/root"]),
    "exit":     CommandSpec("exit",     cmd_exit,     "Exit Ryft.",                      usage=["/exit"]),
}

COMMANDS["quit"] = COMMANDS["exit"]

def _execute(ctx, name: str, args: list[str], label: str) -> None:
    spec = COMMANDS.get(name)
    if spec is None:
        ui.error(f"Unknown command: {label}. Try /help.")
        return
    try:
        spec.handler(ctx, args)
    except Exception as exc:
        # Command handlers are a plugin-style registry covering ~25
        # unrelated features — this top-level catch-all is the last line
        # of defense against a handler bug taking down the whole REPL, so
        # it stays broad by design, but the failure is now logged (with a
        # traceback) instead of only ever surfacing as a one-line message
        # to the user.
        logger.exception("Command %s failed", label)
        ui.error(f"{label} failed: {exc}")


def dispatch(ctx, raw: str) -> None:
    """Dispatch a single typed REPL line, e.g. '/commit' or '/diff foo.py'."""
    raw = raw.strip()
    if not raw: return
    if not raw.startswith("/"):
        ui.warn("Ryft only understands slash commands. Try /help.")
        return
    parts = raw[1:].split()
    if not parts: return
    name, args = parts[0].lower(), parts[1:]
    _execute(ctx, name, args, f"/{name}")


def dispatch_argv(ctx, argv: list[str]) -> None:
    """Dispatch a command from already-split argv, e.g. `ryft diff foo.py`
    from the shell. Unlike dispatch(), this never re-joins/re-splits the
    arguments, so a value containing spaces (a quoted filename, a commit
    message, ...) survives intact."""
    if not argv: return
    name, args = argv[0].lower(), argv[1:]
    _execute(ctx, name, args, name)