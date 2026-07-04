"""Ryft's formatting pipeline.

    File -> Language Detection -> Ignore Checks -> Universal Normalization
    -> Language Formatter -> Semantic Cleanup -> External Formatter (optional)
    -> Validation -> Atomic Write -> Report

`pipeline.py` orchestrates the stages; `ryft.lang` is the language
registry every formatter (Python, Lua, JSON today; stubs for everything
else Ryft recognizes) plugs into. See `ryft/lang/__init__.py` for how to
add a language.

This package replaces the old single-file `formatter.py` but keeps its
public surface: `format_file` and `format_paths` have the exact same
signatures and behavior for `.py`/`.lua` files, and `PythonCommentRemover`
/ `LuaCommentRemover` / `FORMATTERS` are still importable from here for
anything (including existing tests) that used them directly. `sync.py`
and `commands.py` did not need to change.
"""
from __future__ import annotations

from pathlib import Path

from ..lang import FormatOptions, get_formatter
from ..lang.legacy import LuaCommentRemover, PythonCommentRemover
from .pipeline import format_one, run_pipeline
from .report import FormatReport

__all__ = [
    "FormatOptions",
    "FormatReport",
    "format_file",
    "format_paths",
    "format_one",
    "run_pipeline",
    "get_formatter",
    "PythonCommentRemover",
    "LuaCommentRemover",
    "FORMATTERS",
]

# --- Backwards-compatible names -----------------------------------------
# PythonCommentRemover / LuaCommentRemover are imported above, unchanged
# from the original formatter.py, for any direct importer.
FORMATTERS = {".py": PythonCommentRemover, ".lua": LuaCommentRemover}


def format_file(path: Path, max_blank_lines: int = 2, remove_comments: bool = True) -> bool:
    """Format one file in place through the full pipeline. Returns True
    if it changed. Same signature and defaults as the original
    `formatter.format_file` — every existing caller (sync.py,
    commands.py) works unmodified."""
    options = FormatOptions(max_blank_lines=max_blank_lines, remove_comments=remove_comments)
    return format_one(path, options)


def format_paths(paths: list[Path], max_blank_lines: int = 2, remove_comments: bool = True) -> list[Path]:
    """Format many files in place. Returns the list that changed. Same
    signature as the original `formatter.format_paths`."""
    options = FormatOptions(max_blank_lines=max_blank_lines, remove_comments=remove_comments)
    changed: list[Path] = []
    for p in paths:
        if format_one(p, options):
            changed.append(p)
    return changed
