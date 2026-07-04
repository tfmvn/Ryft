"""Language registry (Layer 2 of the formatter architecture).

Maps file extensions (and a couple of exact filenames, for things like
`Dockerfile`) to `LanguageFormatter` instances. The pipeline in
`ryft.formatter` never hardcodes a language list — it just calls
`get_formatter(path)` and asks the result to format the text. Adding a
language means writing one small module here and importing it at the
bottom of this file; nothing in `ryft.formatter` changes.

Real formatters today: Python, Lua, JSON. Everything else in Ryft's
supported-language list gets a `StubFormatter` (universal normalization
only) until a real one is written — see `stubs.py`.
"""
from __future__ import annotations

from pathlib import Path

from .base import FormatOptions, LanguageFormatter, StubFormatter

__all__ = [
    "FormatOptions",
    "LanguageFormatter",
    "StubFormatter",
    "register",
    "get_formatter",
    "all_languages",
]

_BY_EXTENSION: dict[str, LanguageFormatter] = {}
_BY_FILENAME: dict[str, LanguageFormatter] = {}


def register(formatter: LanguageFormatter, *, filenames: tuple[str, ...] = ()) -> LanguageFormatter:
    """Register *formatter* for every extension it declares, plus any
    exact *filenames* (case-insensitive — for extensionless files like
    `Dockerfile`/`Makefile`). Returns the formatter, so it can be used
    directly as a decorator-free one-liner at the bottom of a module."""
    for ext in formatter.extensions:
        _BY_EXTENSION[ext.lower()] = formatter
    for name in filenames:
        _BY_FILENAME[name.lower()] = formatter
    return formatter


def get_formatter(path: Path) -> LanguageFormatter | None:
    """Look up the formatter for *path*. Exact filename takes priority
    over suffix, so `Dockerfile` (no extension) still resolves."""
    hit = _BY_FILENAME.get(path.name.lower())
    if hit is not None:
        return hit
    return _BY_EXTENSION.get(path.suffix.lower())


def all_languages() -> list[str]:
    """Every language name Ryft currently recognizes, stub or real."""
    names = {f.name for f in _BY_EXTENSION.values()} | {f.name for f in _BY_FILENAME.values()}
    return sorted(names)


# Side-effect imports: each of these calls register() at import time.
# Order doesn't matter. Real formatters first for readability only.
from . import json_lang, lua_lang, python_lang  # noqa: E402,F401
from . import stubs  # noqa: E402,F401
