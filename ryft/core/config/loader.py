"""Config discovery + loading for Ryft v2.

Discovery order (first hit defines the project root):
  1. ryft.toml            (preferred v2 format)
  2. pyproject.toml       ([tool.ryft] table)
  3. .src.py              (v1 format, still supported)

Then environment variables (`RYFT_*`) overlay the result. The v1 `.src.py`
`Ollama.*_model` fields are mapped automatically onto the v2 provider roles,
so existing projects keep working unchanged.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, cast

from .schema import (
    Config, FormatterConfig, GitConfig, GithubConfig, IgnoreConfig,
    OllamaBackendConfig, OllamaConfig, OpenAIBackendConfig, AnthropicBackendConfig,
    GoogleBackendConfig, ProviderRoleConfig, ProjectConfig, ServicesConfig,
    SyncConfig,
)

logger = logging.getLogger(__name__)

RYFT_TOML = "ryft.toml"
PYPROJECT = "pyproject.toml"
SRC_PY = ".src.py"

DEFAULT_IGNORE = ["__pycache__", ".venv", "venv", "dist", "build", ".git", "ryft"]


def _toml_loads(text: str) -> dict:
    """Parse TOML without forcing a hard dependency on 3.11+ or tomli."""
    try:
        import tomllib  # type: ignore
        return tomllib.loads(text)
    except ModuleNotFoundError:
        try:
            import tomli  # type: ignore
            return tomli.loads(text)
        except ModuleNotFoundError:
            raise RuntimeError(
                "No TOML parser available. Install 'tomli' (pip install tomli) "
                "or use Python 3.11+."
            )


def find_root(start: Path | None = None) -> Path | None:
    current = (start or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        for name in (RYFT_TOML, PYPROJECT, SRC_PY):
            if (directory / name).exists():
                return directory
    return None


# ── .src.py (v1) loader ──────────────────────────────────────────────────────

def _exec_src_py(path: Path) -> dict:
    """Execute a trusted, user-authored .src.py in an isolated namespace.

    This is a deliberate `exec`, not an import: the file never touches
    sys.modules, so re-reading it always yields fresh content. Same trust
    level as the old .src TOML file — executing user-authored local config is
    expected and intentional.
    """
    namespace: dict = {"__file__": str(path), "__builtins__": __builtins__}
    try:
        source = path.read_text(encoding="utf-8")
        code = compile(source, str(path), "exec")
        exec(code, namespace)  # noqa: S102 - trusted local config
    except Exception:
        logger.warning("Failed to execute %s — falling back to defaults", path, exc_info=True)
        return {}
    return namespace


def _from_src_py(ns: dict) -> Config:
    project = ns.get("Project")
    ollama = ns.get("Ollama")
    sync = ns.get("Sync")
    git = ns.get("Git")
    formatter = ns.get("Formatter")
    ignore = ns.get("IGNORE", [])

    legacy_model = _attr(ollama, "model", "qwen2.5-coder:7b-instruct-q4_K_M")
    roles = ProviderRoleConfig(
        commit=_attr(ollama, "commit_model", legacy_model),
        analyze=_attr(ollama, "analysis_model", legacy_model),
        review=_attr(ollama, "review_model", legacy_model),
        chat=_attr(ollama, "analysis_model", legacy_model),
        embed="ollama:nomic-embed-text",
        agent=_attr(ollama, "analysis_model", legacy_model),
    )
    return Config(
        version=3,
        project=ProjectConfig(name=_attr(project, "name", "project")),
        ollama=OllamaConfig(
            enabled=_attr(ollama, "enabled", True),
            host=_attr(ollama, "host", "http://localhost:11434"),
            timeout=_attr(ollama, "timeout", 60),
            commit_workers=_attr(ollama, "commit_workers", 2),
            model=legacy_model,
            commit_model=roles.commit,
            analysis_model=roles.analyze,
            review_model=roles.review,
        ),
        git=GitConfig(
            branch=_attr(git, "branch", "main"),
            remote=_attr(git, "remote", "origin"),
            fallback_commit_message=_attr(git, "fallback_commit_message", "chore: update {file}"),
            auto_commit_small_changes=_attr(git, "auto_commit_small_changes", True),
            small_change_threshold=_attr(git, "small_change_threshold", 10),
        ),
        formatter=FormatterConfig(
            enabled=_attr(formatter, "enabled", True),
            max_blank_lines=_attr(formatter, "max_blank_lines", 2),
            remove_comments=_attr(formatter, "remove_comments", True),
        ),
        sync=SyncConfig(
            enabled=_attr(sync, "enabled", False),
            debounce_seconds=_attr(sync, "debounce_seconds", 30),
            push=_attr(sync, "push", True),
        ),
        ignore=IgnoreConfig(patterns=list(ignore)),
        providers=_providers_with(
            roles=roles,
            ollama=OllamaBackendConfig(
                enabled=_attr(ollama, "enabled", True),
                host=_attr(ollama, "host", "http://localhost:11434"),
                timeout=_attr(ollama, "timeout", 60),
                commit_workers=_attr(ollama, "commit_workers", 2),
            ),
            openai=_resolve_keyed(OpenAIBackendConfig()),
            anthropic=_resolve_keyed(AnthropicBackendConfig()),
            google=_resolve_keyed(GoogleBackendConfig()),
        ),
        root=Path.cwd(),
    )


# ── ryft.toml / pyproject loader ─────────────────────────────────────────────

def _from_toml(tbl: dict) -> Config:
    cfg = Config(version=2)
    cfg.project = _section(tbl, "project", ProjectConfig)
    cfg.git = _section(tbl, "git", GitConfig)
    cfg.formatter = _section(tbl, "formatter", FormatterConfig)
    cfg.sync = _section(tbl, "sync", SyncConfig)
    cfg.ignore = _section(tbl, "ignore", IgnoreConfig)
    cfg.github = _section(tbl, "github", GithubConfig)
    cfg.services = _section(tbl, "services", ServicesConfig)
    cfg.providers = _providers_from_toml(tbl.get("providers", {}))
    return cfg


def _providers_from_toml(p: dict) -> Config.providers:  # type: ignore[name-defined]
    roles = ProviderRoleConfig(
        commit=p.get("commit", ProviderRoleConfig.commit),
        analyze=p.get("analyze", ProviderRoleConfig.analyze),
        review=p.get("review", ProviderRoleConfig.review),
        chat=p.get("chat", ProviderRoleConfig.chat),
        embed=p.get("embed", ProviderRoleConfig.embed),
        agent=p.get("agent", ProviderRoleConfig.agent),
    )
    return _providers_with(
        roles=roles,
        ollama=_resolve_ollama(_section(p, "ollama", OllamaBackendConfig)),
        openai=_resolve_keyed(_section(p, "openai", OpenAIBackendConfig)),
        anthropic=_resolve_keyed(_section(p, "anthropic", AnthropicBackendConfig)),
        google=_resolve_keyed(_section(p, "google", GoogleBackendConfig)),
    )


def _resolve_keyed(cfg: Any) -> Any:
    """Fill api_key from its env var and auto-enable when a key is present."""
    if not cfg.api_key:
        cfg.api_key = os.environ.get(cfg.api_key_env)
    cfg.enabled = bool(cfg.enabled) or bool(cfg.api_key)
    return cfg


def _resolve_ollama(cfg: Any) -> Any:
    return cfg


def _providers_with(**kw: Any) -> Config.providers:  # type: ignore[name-defined]
    from .schema import ProvidersConfig
    return ProvidersConfig(**kw)


def _section(tbl: dict, name: str, cls: type) -> Any:
    data = tbl.get(name, {})
    if not isinstance(data, dict):
        return cls()
    known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    clean = {k: v for k, v in data.items() if k in known}
    try:
        return cls(**clean)
    except Exception:
        logger.warning("Invalid [%s] config — using defaults", name, exc_info=True)
        return cls()


# ── public API ───────────────────────────────────────────────────────────────

def load_config(root: Path) -> Config:
    root = root.resolve()
    cfg_path = root / RYFT_TOML
    if cfg_path.exists():
        try:
            tbl = _toml_loads(cfg_path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("Could not parse %s — using defaults", cfg_path, exc_info=True)
            cfg = Config()
        else:
            cfg = _from_toml(tbl)
        cfg.source = str(cfg_path)
        cfg.path = cfg_path
    else:
        pp = root / PYPROJECT
        if pp.exists():
            try:
                tbl = _toml_loads(pp.read_text(encoding="utf-8")).get("tool", {}).get("ryft", {})
            except Exception:
                tbl = {}
            cfg = _from_toml(tbl) if tbl else Config()
            cfg.source = str(pp)
            cfg.path = pp if tbl else None
        else:
            src = root / SRC_PY
            cfg = _from_src_py(_exec_src_py(src)) if src.exists() else Config()
            cfg.source = str(src) if src.exists() else "defaults"
            cfg.path = src if src.exists() else None

    cfg.root = root
    _derive_ollama(cfg)
    return _apply_env(cfg)


def _strip_provider(assignment: str) -> str:
    """'ollama:qwen3:0.6b' -> 'qwen3:0.6b' (also handles no-prefix)."""
    if ":" in assignment:
        return assignment.split(":", 1)[1]
    return assignment


def _derive_ollama(cfg: Config) -> None:
    """Populate the back-compat `cfg.ollama` view from `cfg.providers`.

    Legacy code reads `cfg.ollama.commit_model` / `.host` / etc.; this keeps
    those accesses valid after the v2 provider-role migration without
    duplicating the source of truth (the provider roles remain canonical).
    """
    roles = cfg.providers.roles
    ob = cfg.providers.ollama
    cfg.ollama = OllamaConfig(
        enabled=ob.enabled,
        host=ob.host,
        timeout=ob.timeout,
        commit_workers=ob.commit_workers,
        model=_strip_provider(roles.analyze),
        commit_model=_strip_provider(roles.commit),
        analysis_model=_strip_provider(roles.analyze),
        review_model=_strip_provider(roles.review),
    )


def _apply_env(cfg: Config) -> Config:
    if os.environ.get("RYFT_PROJECT_NAME"):
        cfg.project.name = os.environ["RYFT_PROJECT_NAME"]
    if os.environ.get("RYFT_GIT_BRANCH"):
        cfg.git.branch = os.environ["RYFT_GIT_BRANCH"]
    if os.environ.get("RYFT_OLLAMA_HOST"):
        cfg.providers.ollama.host = os.environ["RYFT_OLLAMA_HOST"]
    if os.environ.get("RYFT_NO_AI"):
        cfg.providers.ollama.enabled = False
    return cfg


def validate_config(root: Path) -> tuple[str, str | None]:
    """Returns (status, detail): status ∈ missing|valid|invalid."""
    for name in (RYFT_TOML, PYPROJECT, SRC_PY):
        path = root / name
        if not path.exists():
            continue
        try:
            text = path.read_text(encoding="utf-8")
            if name == SRC_PY:
                compile(text, str(path), "exec")
            else:
                _toml_loads(text)
        except Exception as exc:  # noqa: BLE001 - surface any parse error
            return "invalid", f"{type(exc).__name__}: {exc}"
        return "valid", None
    return "missing", None


DEFAULT_TOML = """\
# ryft.toml — Ryft configuration (https://github.com/tfmvn/Ryft)
[project]
name = "{name}"

[git]
branch = "main"
remote = "origin"

[formatter]
enabled = true
remove_comments = true
max_blank_lines = 2

[sync]
enabled = false
debounce_seconds = 30
push = true

[providers]
commit   = "ollama:qwen3:0.6b"
analyze  = "ollama:qwen2.5-coder:7b-instruct-q4_K_M"
review   = "ollama:qwen2.5-coder:7b-instruct-q4_K_M"
chat     = "ollama:qwen2.5-coder:7b-instruct-q4_K_M"
embed    = "ollama:nomic-embed-text"

[providers.ollama]
host = "http://localhost:11434"
timeout = 60
commit_workers = 2

[ignore]
patterns = ["*.log", ".env", "node_modules", "coverage"]
"""


def init_config(root: Path, name: str | None = None) -> Path:
    path = root / RYFT_TOML
    path.write_text(DEFAULT_TOML.format(name=name or root.name), encoding="utf-8")
    return path


def _attr(obj: object | None, name: str, default: Any) -> Any:
    if obj is None:
        return default
    return cast(Any, getattr(obj, name, default))
