"""Project root discovery + .src.py config loading/saving."""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar, cast

from .models import (
    Config, FormatterConfig, GitConfig,
    OllamaConfig, ProjectConfig, SyncConfig,
)

T = TypeVar("T")

CONFIG_FILENAME = ".src.py"

DEFAULT_IGNORE = ["__pycache__", ".venv", "venv", "dist", "build", ".git", "ryft"]

DEFAULT_PY = """\
# .src.py

class Project:
    name = "{name}"


class Ollama:
    enabled = True

    # Fast model for commit messages — keep this small (qwen3:0.6b is ideal).
    commit_model = "qwen3:0.6b"
    # Larger model for /analyze (full project diff review).
    analysis_model = "qwen2.5-coder:7b-instruct-q4_K_M"
    # Larger model for /review (per-file code review).
    review_model = "qwen2.5-coder:7b-instruct-q4_K_M"

    # Ollama API endpoint.
    host = "http://localhost:11434"
    # Seconds to wait for AI response.
    timeout = 60
    # Parallel commit message workers (2 is safe on 16GB RAM).
    commit_workers = 2


class Sync:
    enabled = False
    debounce_seconds = 30
    push = True


class Git:
    branch = "main"
    remote = "origin"
    fallback_commit_message = "chore: update {{file}}"

    # Skip AI for tiny changes (<= threshold lines changed).
    auto_commit_small_changes = True
    small_change_threshold = 10


class Formatter:
    enabled = True
    max_blank_lines = 2
    remove_comments = True


IGNORE = [
    "*.log",
    ".env",
    "node_modules",
    "coverage",
]
"""


def find_root(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        if (directory / CONFIG_FILENAME).exists():
            return directory
    return None


def _exec_config(cfg_path: Path) -> dict:
    """Execute the .src.py file in an isolated namespace and return its
    top-level names. This is a deliberate `exec`, not an `import` — the
    file never touches sys.modules, so re-reading it (e.g. after
    `/config init`) always picks up fresh content with no caching.

    .src.py is a trusted, user-authored local file (same trust level the
    old .src TOML file had), so executing it is expected and intentional.
    """
    namespace: dict = {"__file__": str(cfg_path), "__builtins__": __builtins__}
    try:
        source = cfg_path.read_text(encoding="utf-8")
        code = compile(source, str(cfg_path), "exec")
        exec(code, namespace)
    except Exception:
        # Bad/unparsable config → fall back to defaults rather than crash.
        return {}
    return namespace


def _attr(obj: object | None, name: str, default: T) -> T:
    if obj is None:
        return default
    return cast(T, getattr(obj, name, default))


def load_config(root: Path) -> Config:
    cfg_path = root / CONFIG_FILENAME
    ns: dict = {}
    if cfg_path.exists():
        ns = _exec_config(cfg_path)

    ProjectCls   = ns.get("Project")
    OllamaCls    = ns.get("Ollama")
    SyncCls      = ns.get("Sync")
    GitCls       = ns.get("Git")
    FormatterCls = ns.get("Formatter")
    ignore_list  = ns.get("IGNORE", [])

    # Legacy single `model` attribute on Ollama → use as commit_model fallback
    legacy_model = _attr(OllamaCls, "model", OllamaConfig.commit_model)

    return Config(
        version=ns.get("VERSION", 3),
        project=ProjectConfig(name=_attr(ProjectCls, "name", root.name)),
        ollama=OllamaConfig(
            enabled=_attr(OllamaCls, "enabled", True),
            model=legacy_model,
            commit_model=_attr(OllamaCls, "commit_model", legacy_model),
            analysis_model=_attr(OllamaCls, "analysis_model", OllamaConfig.analysis_model),
            review_model=_attr(OllamaCls, "review_model", OllamaConfig.review_model),
            host=_attr(OllamaCls, "host", OllamaConfig.host),
            timeout=_attr(OllamaCls, "timeout", OllamaConfig.timeout),
            commit_workers=_attr(OllamaCls, "commit_workers", OllamaConfig.commit_workers),
        ),
        sync=SyncConfig(
            enabled=_attr(SyncCls, "enabled", False),
            debounce_seconds=_attr(SyncCls, "debounce_seconds", 30),
            push=_attr(SyncCls, "push", True),
        ),
        git=GitConfig(
            branch=_attr(GitCls, "branch", "main"),
            remote=_attr(GitCls, "remote", "origin"),
            fallback_commit_message=_attr(
                GitCls, "fallback_commit_message", "chore: update {file}"
            ),
            auto_commit_small_changes=_attr(GitCls, "auto_commit_small_changes", True),
            small_change_threshold=_attr(GitCls, "small_change_threshold", 10),
        ),
        formatter=FormatterConfig(
            enabled=_attr(FormatterCls, "enabled", True),
            max_blank_lines=_attr(FormatterCls, "max_blank_lines", 2),
            remove_comments=_attr(FormatterCls, "remove_comments", True),
        ),
        ignore=list(ignore_list),
        root=root,
        path=cfg_path if cfg_path.exists() else None,
    )


def validate_config(root: Path) -> tuple[str, str | None]:
    """Check `.src.py` without going through the silent fallback that
    `load_config` uses for normal operation.

    Returns (status, detail):
      status ∈ {"missing", "valid", "invalid"}
      detail is None for "missing"/"valid", or an error message for "invalid".
    """
    cfg_path = root / CONFIG_FILENAME
    if not cfg_path.exists():
        return "missing", None
    try:
        source = cfg_path.read_text(encoding="utf-8")
        code = compile(source, str(cfg_path), "exec")
        namespace: dict = {"__file__": str(cfg_path), "__builtins__": __builtins__}
        exec(code, namespace)
    except Exception as exc:
        return "invalid", f"{type(exc).__name__}: {exc}"
    return "valid", None


def init_config(root: Path, name: str | None = None) -> Path:
    cfg_path = root / CONFIG_FILENAME
    content = DEFAULT_PY.format(name=name or root.name)
    cfg_path.write_text(content, encoding="utf-8")
    return cfg_path


def _class_body_bounds(lines: list[str], class_header: str) -> tuple[int, int] | None:
    """Find the (start, end) line-index range of a top-level class body
    (e.g. `class Ollama:`). `start` is the header line; `end` is exclusive
    — the first line back at column 0 after it (or len(lines))."""
    start = None
    for i, line in enumerate(lines):
        if line.strip() == class_header:
            start = i
            break
    if start is None:
        return None
    end = len(lines)
    for i in range(start + 1, len(lines)):
        stripped = lines[i].strip()
        if stripped and not lines[i].startswith((" ", "\t")):
            end = i
            break
    return start, end


def set_model(cfg: Config, model: str) -> None:
    """Update commit_model in memory and on disk."""
    cfg.ollama.commit_model = model
    cfg.ollama.model = model
    if cfg.path is None or not cfg.path.exists():
        return
    text = cfg.path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    bounds = _class_body_bounds(lines, "class Ollama:")
    if bounds is None:
        return
    start, end = bounds

    patched = False
    for i in range(start + 1, end):
        stripped = lines[i].strip()
        if stripped.startswith("commit_model"):
            indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
            lines[i] = f'{indent}commit_model = "{model}"\n'
            patched = True
            break

    if not patched:
        # Fallback: patch legacy `model` attribute
        for i in range(start + 1, end):
            stripped = lines[i].strip()
            if stripped.startswith("model") and not stripped.startswith(("model_", "model.")):
                # exclude commit_model/analysis_model/review_model lines —
                # those don't start with "model" so they're already safe.
                indent = lines[i][: len(lines[i]) - len(lines[i].lstrip())]
                lines[i] = f'{indent}model = "{model}"\n'
                patched = True
                break

    if patched:
        cfg.path.write_text("".join(lines), encoding="utf-8")


def is_ignored(path: Path, root: Path, extra_patterns: list[str]) -> bool:
    try:
        rel_parts = path.relative_to(root).parts
    except ValueError:
        rel_parts = path.parts
    patterns = set(DEFAULT_IGNORE) | set(extra_patterns)
    for part in rel_parts:
        if part in patterns or part.startswith("."):
            return True
    return False