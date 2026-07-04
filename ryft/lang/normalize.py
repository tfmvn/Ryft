"""Layer 1 — Universal Normalization.

Applies to every text file Ryft touches, regardless of language: line
ending normalization, trailing-whitespace trimming, blank-line
collapsing, trailing-blank-line removal, and a single final newline.
Indentation itself (tabs vs spaces, indent width) is never touched —
only trailing/blank-line whitespace, which carries no semantic meaning
in the vast majority of languages.

This stage must never change program behavior. It runs before *and*
after the language-specific formatter, so a stub formatter (which does
nothing but call this) still leaves every file in reasonable shape.

Known trade-off: a handful of formats give trailing whitespace or blank
runs actual meaning (Markdown's two-trailing-spaces line break, YAML
literal block scalars). Callers that care can pass
`trim_trailing_whitespace=False` / `collapse_blank_lines=False` via
`FormatOptions` for those files.
"""
from __future__ import annotations

from .base import FormatOptions


def normalize(text: str, options: FormatOptions) -> str:
    if not text:
        return text

    if options.normalize_line_endings:
        text = text.replace("\r\n", "\n").replace("\r", "\n")

    lines = text.split("\n")

    if options.trim_trailing_whitespace:
        lines = [line.rstrip(" \t") for line in lines]

    if options.collapse_blank_lines:
        lines = _collapse_blank_lines(lines, options.max_blank_lines)

    # Trailing blank lines at EOF — distinct from mid-file collapsing
    # above, and always applied regardless of max_blank_lines.
    while len(lines) > 1 and lines[-1] == "" and lines[-2] == "":
        lines.pop()

    text = "\n".join(lines)

    if options.insert_final_newline and text and not text.endswith("\n"):
        text += "\n"

    return text


def _collapse_blank_lines(lines: list[str], max_blank: int) -> list[str]:
    out: list[str] = []
    blanks = 0
    for line in lines:
        if line == "":
            blanks += 1
            if blanks <= max_blank:
                out.append(line)
        else:
            blanks = 0
            out.append(line)
    return out
