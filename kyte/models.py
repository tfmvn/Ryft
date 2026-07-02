"""Shared data shapes used across Kyte."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional


@dataclass
class ProjectConfig:
    name: str = "project"


@dataclass
class OllamaConfig:
    enabled: bool = True
    # Legacy single-model field (still read from .src.py as fallback)
    model: str = "qwen2.5-coder:7b-instruct-q4_K_M"
    # Per-role models
    commit_model: str = "qwen3:0.6b"
    analysis_model: str = "qwen2.5-coder:7b-instruct-q4_K_M"
    review_model: str = "qwen2.5-coder:7b-instruct-q4_K_M"
    host: str = "http://localhost:11434"
    timeout: int = 60
    commit_workers: int = 2


@dataclass
class SyncConfig:
    enabled: bool = False
    debounce_seconds: float = 30
    push: bool = True


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
class Config:
    version: int = 3
    project: ProjectConfig = field(default_factory=ProjectConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    sync: SyncConfig = field(default_factory=SyncConfig)
    git: GitConfig = field(default_factory=GitConfig)
    formatter: FormatterConfig = field(default_factory=FormatterConfig)
    ignore: list[str] = field(default_factory=list)
    root: Path = field(default_factory=Path.cwd)
    path: Optional[Path] = None


@dataclass
class ActivityEvent:
    message: str
    level: str = "info"
    at: float = field(default_factory=time.time)

    @property
    def time_str(self) -> str:
        return time.strftime("%H:%M", time.localtime(self.at))

    # NOTE: icon/colour rendering lives in ui._icon_color(), which is the
    # single source of truth the UI actually calls. An older icon/color
    # pair used to live here too but had gone stale (some glyphs required
    # a Nerd Font and had silently degraded to empty strings) and nothing
    # in the codebase referenced it — removed rather than fixed in place.


@dataclass
class SyncStatus:
    current_file: Optional[str] = None
    current_stage: Optional[str] = None

    last_file: Optional[str] = None
    last_commit_message: Optional[str] = None
    last_push_time: Optional[float] = None

    commits_this_session: int = 0

    busy: bool = False


@dataclass
class AppContext:
    config: Config
    ai: Any
    activity: Any
    console: Any
    sync: Any = None
    sync_status: "SyncStatus" = field(default_factory=SyncStatus)
    running: bool = True


@dataclass
class CommandSpec:
    name: str
    handler: Callable[["object", list[str]], None]
    description: str
    usage: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)