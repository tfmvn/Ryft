"""Stage orchestration.

    File
     -> Language Detection      (ryft.lang.get_formatter)
     -> Ignore Checks           (ryft.config.is_ignored, in run_pipeline)
     -> Universal Normalization (ryft.lang.normalize, pre-pass)
     -> Language Formatter      (formatter.format(text, options))
     -> Semantic Cleanup        (folded into FormatOptions, consumed above)
     -> External Formatter      (formatter/external.py, optional)
     -> Validation               (_validate, below)
     -> Atomic Write              (_atomic_write, below)
     -> Report                    (FormatReport)

Every stage is a small, independent function. Nothing here hardcodes a
language — that all lives in the registry.
"""
from __future__ import annotations

import time
from pathlib import Path

from ..lang import FormatOptions, get_formatter
from ..lang.normalize import normalize
from ..utils import is_binary_file
from .external import try_external
from .report import FormatReport

# --- Validation --------------------------------------------------------
# Optional, per-extension: if a language has a cheap way to confirm the
# formatted text is still valid, register it here. No entry == no
# validation (the formatter's own carefulness is all that's relied on;
# this is a best-effort net, not universal coverage).

_VALIDATORS: dict[str, "callable"] = {}


def _validator(*extensions: str):
    def deco(fn):
        for ext in extensions:
            _VALIDATORS[ext] = fn
        return fn

    return deco


@_validator(".py")
def _validate_python(text: str) -> bool:
    import ast

    try:
        ast.parse(text)
        return True
    except SyntaxError:
        return False


@_validator(".json")
def _validate_json(text: str) -> bool:
    import json

    try:
        json.loads(text)
        return True
    except ValueError:
        return False


def _validate(path: Path, text: str) -> bool:
    validator = _VALIDATORS.get(path.suffix.lower())
    if validator is None:
        return True
    return validator(text)


# --- Core pipeline -------------------------------------------------------


def _run_stages(path: Path, options: FormatOptions, use_external: bool) -> tuple[str, str] | None:
    """Read the file and run every formatting stage without writing
    anything. Returns (source, result), or None if the file can't or
    shouldn't be touched at all."""
    if not path.exists() or not path.is_file() or is_binary_file(path):
        return None

    language_formatter = get_formatter(path)
    if language_formatter is None:
        return None

    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    text = normalize(source, options)
    text = language_formatter.format(text, options)

    if use_external:
        external_result = try_external(path, text, language_formatter.name)
        if external_result is not None:
            text = normalize(external_result, options)

    return source, text


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def format_one(path: Path, options: FormatOptions, *, use_external: bool = True) -> bool:
    """Run the full pipeline on one file. Returns True if its contents
    changed on disk. Never reformats a file whose content is unchanged
    (no-op write), and never writes anything that fails validation."""
    staged = _run_stages(path, options, use_external)
    if staged is None:
        return False

    source, text = staged
    if text == source:
        return False
    if not _validate(path, text):
        return False

    _atomic_write(path, text)
    return True


def run_pipeline(
    paths: list[Path],
    options: FormatOptions,
    *,
    root: Path | None = None,
    ignore_patterns: list[str] | None = None,
    use_external: bool = True,
) -> FormatReport:
    """Format many files and return an aggregate FormatReport. If *root*
    is given, each path is checked against `ryft.config.is_ignored`
    first (using *ignore_patterns* on top of Ryft's defaults)."""
    from ..config import is_ignored

    started = time.perf_counter()
    report = FormatReport()
    ignore_patterns = ignore_patterns or []

    for path in paths:
        report.files_scanned += 1

        if root is not None and is_ignored(path, root, ignore_patterns):
            report.files_ignored += 1
            continue

        staged = _run_stages(path, options, use_external)
        if staged is None:
            report.files_skipped += 1
            continue

        source, text = staged
        if text == source:
            report.files_skipped += 1
            continue
        if not _validate(path, text):
            report.files_skipped += 1
            continue

        report.whitespace_chars_removed += max(0, len(source) - len(text))
        report.blank_lines_collapsed += max(0, source.count("\n\n\n") - text.count("\n\n\n"))

        _atomic_write(path, text)
        report.files_formatted += 1
        report.changed_files.append(path)

    report.elapsed_seconds = time.perf_counter() - started
    return report
