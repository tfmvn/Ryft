"""Configuration schema for Ryft v2.

Plain dataclasses — no validation framework, so importing this module is
instant and dependency-free. `loader.py` populates these from `ryft.toml`,
`pyproject.toml [tool.ryft]`, `.src.py` (v1, backward-compatible), and
environment overlays.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProjectConfig:
    name: str = "project"


@dataclass
class GitConfig:
    branch: str = "main"
    remote: str = "origin"
    fallback_commit_message: str = "chore: update {file}"
    auto_commit_small_changes: bool = True
    small_change_threshold: int = 10


@dataclass
class FormatterConfig:
    enabled: bool = True
    max_blank_lines: int = 2
    remove_comments: bool = True


@dataclass
class SyncConfig:
    enabled: bool = False
    debounce_seconds: float = 30.0
    push: bool = True


@dataclass
class IgnoreConfig:
    patterns: list[str] = field(default_factory=list)


@dataclass
class ProviderRoleConfig:
    """role -> "provider:model" assignment."""

    commit: str = "ollama:qwen3:0.6b"
    analyze: str = "ollama:qwen2.5-coder:7b-instruct-q4_K_M"
    review: str = "ollama:qwen2.5-coder:7b-instruct-q4_K_M"
    chat: str = "ollama:qwen2.5-coder:7b-instruct-q4_K_M"
    embed: str = "ollama:nomic-embed-text"
    agent: str = "ollama:qwen2.5-coder:7b-instruct-q4_K_M"


@dataclass
class OllamaBackendConfig:
    enabled: bool = True
    host: str = "http://localhost:11434"
    timeout: int = 60
    commit_workers: int = 2
    models: list[str] = field(default_factory=list)
    default_model: str = ""


@dataclass
class OpenAIBackendConfig:
    enabled: bool = False
    api_key: str | None = None         # resolved from api_key_env at load time
    api_key_env: str = "OPENAI_API_KEY"
    base_url: str = "https://api.openai.com/v1"
    default_model: str = "gpt-4o-mini"
    models: list[str] = field(default_factory=list)


@dataclass
class AnthropicBackendConfig:
    enabled: bool = False
    api_key: str | None = None         # resolved from api_key_env at load time
    api_key_env: str = "ANTHROPIC_API_KEY"
    model: str = "claude-sonnet-4-0"


@dataclass
class GoogleBackendConfig:
    enabled: bool = False
    api_key: str | None = None         # resolved from api_key_env at load time
    api_key_env: str = "GEMINI_API_KEY"
    model: str = "gemini-1.5-flash"


@dataclass
class ProvidersConfig:
    roles: ProviderRoleConfig = field(default_factory=ProviderRoleConfig)
    ollama: OllamaBackendConfig = field(default_factory=OllamaBackendConfig)
    openai: OpenAIBackendConfig = field(default_factory=OpenAIBackendConfig)
    anthropic: AnthropicBackendConfig = field(default_factory=AnthropicBackendConfig)
    google: GoogleBackendConfig = field(default_factory=GoogleBackendConfig)


@dataclass
class OllamaConfig:
    """Back-compat view of the Ollama backend, mirroring the v1 `Ollama.*`
    fields (host / models per role / timeout / workers). The loader derives
    this from `providers.roles` + `providers.ollama` so legacy code that
    reads `cfg.ollama.commit_model` keeps working after the v2 migration."""

    enabled: bool = True
    host: str = "http://localhost:11434"
    timeout: int = 60
    commit_workers: int = 2
    model: str = "qwen2.5-coder:7b-instruct-q4_K_M"
    commit_model: str = "qwen3:0.6b"
    analysis_model: str = "qwen2.5-coder:7b-instruct-q4_K_M"
    review_model: str = "qwen2.5-coder:7b-instruct-q4_K_M"


@dataclass
class GithubConfig:
    token_env: str = "GITHUB_TOKEN"
    enabled: bool = True


@dataclass
class ServicesConfig:
    git_monitor: bool = True
    indexer: bool = True
    ai_cache: bool = True


@dataclass
class ThemeConfig:
    """User-overridable palette accents (optional)."""

    primary: str | None = None
    bg: str | None = None


@dataclass
class Config:
    version: int = 2
    source: str = "defaults"  # which file produced this config
    project: ProjectConfig = field(default_factory=ProjectConfig)
    git: GitConfig = field(default_factory=GitConfig)
    formatter: FormatterConfig = field(default_factory=FormatterConfig)
    sync: SyncConfig = field(default_factory=SyncConfig)
    ignore: IgnoreConfig = field(default_factory=IgnoreConfig)
    providers: ProvidersConfig = field(default_factory=ProvidersConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    github: GithubConfig = field(default_factory=GithubConfig)
    services: ServicesConfig = field(default_factory=ServicesConfig)
    theme: ThemeConfig = field(default_factory=ThemeConfig)
    root: Path = field(default_factory=Path.cwd)
    path: Path | None = None
