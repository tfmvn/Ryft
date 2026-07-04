"""JSON language formatter.

Re-serializes with consistent 2-space indentation. JSON has no comments
and no meaningful whitespace, so round-tripping through `json.loads` /
`json.dumps` is safe by construction — if it doesn't parse (or is
JSON5/JSONC with comments Ryft doesn't want to guess about), it's left
to the universal normalizer only.
"""
from __future__ import annotations

import json

from . import register
from .base import FormatOptions, LanguageFormatter
from .normalize import normalize


class JSONFormatter(LanguageFormatter):
    name = "JSON"
    extensions = (".json",)

    def format(self, text: str, options: FormatOptions) -> str:
        if not text.strip():
            return normalize(text, options)

        try:
            data = json.loads(text)
        except ValueError:
            return normalize(text, options)

        pretty = json.dumps(data, indent=2, ensure_ascii=False)
        return normalize(pretty, options)


register(JSONFormatter())
