"""Lua language formatter — wraps the original regex-based comment
remover unchanged."""
from __future__ import annotations

from . import register
from .base import FormatOptions, LanguageFormatter
from .legacy import LuaCommentRemover
from .normalize import normalize


class LuaFormatter(LanguageFormatter):
    name = "Lua"
    extensions = (".lua",)

    def format(self, text: str, options: FormatOptions) -> str:
        if not text:
            return text

        remover = LuaCommentRemover(
            max_blank_lines=options.max_blank_lines,
            remove_comments=options.remove_comments,
        )
        result = remover.process(text)
        return normalize(result, options)


register(LuaFormatter())
