"""Layer 5 — External Formatter Support.

If a real formatter for a language happens to be installed (ruff/black,
stylua, prettier, rustfmt, gofmt, clang-format, ...), Ryft will shell out
to it for a more thorough result. None of these are required — every
language Ryft claims to support already has an internal formatter (or a
stub that just normalizes), so a missing tool, a non-zero exit code, or
a timeout all just mean "skip this stage", never a hard failure.

Adapters are matched by the language's display `name` (as declared on
its `LanguageFormatter`), not by extension, since that's what stays
stable if a language ever grows more than one extension.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

_TIMEOUT_SECONDS = 10

# language name -> ordered list of "first one installed wins" commands.
# Each command must read source on stdin and write formatted source to
# stdout — that's the only contract external formatters have to meet.
_ADAPTERS: dict[str, list[list[str]]] = {
    "Python": [["ruff", "format", "--stdin-filename", "file.py", "-"], ["black", "-", "-q"]],
    "Lua": [["stylua", "-"]],
    "JSON": [["prettier", "--parser", "json"]],
    "JavaScript": [["prettier", "--parser", "babel"]],
    "TypeScript": [["prettier", "--parser", "typescript"]],
    "TSX": [["prettier", "--parser", "typescript"]],
    "JSX": [["prettier", "--parser", "babel"]],
    "CSS": [["prettier", "--parser", "css"]],
    "SCSS": [["prettier", "--parser", "scss"]],
    "HTML": [["prettier", "--parser", "html"]],
    "Markdown": [["prettier", "--parser", "markdown"]],
    "YAML": [["prettier", "--parser", "yaml"]],
    "Rust": [["rustfmt", "--emit", "stdout"]],
    "Go": [["gofmt"]],
    "C": [["clang-format"]],
    "C++": [["clang-format"]],
    "C#": [["clang-format"]],
    "Java": [["clang-format"]],
}

_availability_cache: dict[str, bool] = {}


def _tool_available(binary: str) -> bool:
    if binary not in _availability_cache:
        _availability_cache[binary] = shutil.which(binary) is not None
    return _availability_cache[binary]


def try_external(path: Path, text: str, language: str) -> str | None:
    """Try each configured external formatter for *language*, in order.
    Returns formatted text from the first one that runs successfully, or
    None if none are installed/usable — callers keep the pipeline's own
    result in that case."""
    for cmd in _ADAPTERS.get(language, ()):
        if not _tool_available(cmd[0]):
            continue
        try:
            result = subprocess.run(
                cmd,
                input=text,
                capture_output=True,
                text=True,
                timeout=_TIMEOUT_SECONDS,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout
    return None
