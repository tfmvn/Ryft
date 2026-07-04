"""Stub registrations for every language Ryft recognizes but doesn't
have a real formatter for yet.

Each one is a `StubFormatter` (see `base.py`) that runs only the
universal normalizer — never anything language-specific — so it's always
safe. Turning a stub into a real formatter later is a one-line swap:
write a `<language>_lang.py` with a proper `LanguageFormatter` and
`register()` it for the same extensions; nothing else changes.
"""
from __future__ import annotations

from . import register
from .base import StubFormatter

# (display name, extensions) — everything here gets a StubFormatter.
_STUB_LANGUAGES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("JavaScript", (".js", ".mjs", ".cjs")),
    ("TypeScript", (".ts",)),
    ("TSX", (".tsx",)),
    ("JSX", (".jsx",)),
    ("Rust", (".rs",)),
    ("Go", (".go",)),
    ("Java", (".java",)),
    ("Kotlin", (".kt", ".kts")),
    ("Swift", (".swift",)),
    ("PHP", (".php",)),
    ("Ruby", (".rb",)),
    ("Shell", (".sh", ".bash", ".zsh")),
    ("PowerShell", (".ps1",)),
    ("Batch", (".bat", ".cmd")),
    ("C", (".c", ".h")),
    ("C++", (".cpp", ".cc", ".cxx", ".hpp", ".hh")),
    ("C#", (".cs",)),
    ("HTML", (".html", ".htm")),
    ("CSS", (".css",)),
    ("SCSS", (".scss",)),
    ("Markdown", (".md", ".markdown")),
    ("YAML", (".yaml", ".yml")),
    ("XML", (".xml",)),
    ("TOML", (".toml",)),
    ("INI", (".ini", ".cfg")),
    ("SQL", (".sql",)),
)

for _name, _exts in _STUB_LANGUAGES:
    register(StubFormatter(_name, _exts))

# Extensionless files, matched by exact filename instead.
register(StubFormatter("Dockerfile", ()), filenames=("dockerfile",))
register(StubFormatter("Makefile", ()), filenames=("makefile",))
