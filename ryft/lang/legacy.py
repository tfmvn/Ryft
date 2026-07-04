"""Ryft's original Python/Lua comment-and-blank-line formatters,
unchanged from the pre-refactor `formatter.py`.

Kept here verbatim for two reasons:

1. Backwards compatibility — `ryft.formatter` still re-exports
   `PythonCommentRemover` / `LuaCommentRemover` under their original
   names, in case anything (including existing tests) imports them
   directly.
2. Reuse — `lang/python_lang.py` and `lang/lua_lang.py` wrap these as
   the comment-stripping step of the new pipeline, instead of
   duplicating the logic.
"""

from __future__ import annotations

import io
import re
import tokenize


class PythonCommentRemover:
    """Strips comments from Python source and collapses excess blank lines."""

    extensions = (".py",)

    def __init__(self, max_blank_lines: int = 2, remove_comments: bool = True) -> None:
        self.max_blank_lines = max_blank_lines
        self.remove_comments = remove_comments

    def process(self, source: str) -> str:
        if not source:
            return source
        lines = self._strip_comments(source) if self.remove_comments else source.splitlines(keepends=True)
        return self._collapse_blanks(lines)

    def _strip_comments(self, source: str) -> list[str]:
        readline = io.BytesIO(source.encode("utf-8")).readline
        original = source.splitlines(keepends=True)
        padded = [""] + original

        spans: dict[int, list[tuple[int, int]]] = {}
        try:
            for tok in tokenize.tokenize(readline):
                if tok.type == tokenize.COMMENT:
                    row, cs = tok.start
                    _, ce = tok.end
                    spans.setdefault(row, []).append((cs, ce))
        except tokenize.TokenError:
            return original

        result: list[str] = []
        for lineno, line in enumerate(padded):
            if lineno == 0:
                continue
            if lineno not in spans:
                result.append(line)
                continue
            chars = list(line)
            for cs, ce in sorted(spans[lineno], reverse=True):
                del chars[cs:ce]
            cleaned = "".join(chars).rstrip()
            ending = "\r\n" if line.endswith("\r\n") else "\n"
            result.append((cleaned + ending) if cleaned else ending)
        return result

    def _collapse_blanks(self, lines: list[str]) -> str:
        out: list[str] = []
        blanks = 0
        for line in lines:
            if line.strip() == "":
                blanks += 1
                if blanks <= self.max_blank_lines:
                    out.append(line)
            else:
                blanks = 0
                out.append(line)
        while out and out[0].strip() == "":
            out.pop(0)
        return "".join(out)


class LuaCommentRemover:
    extensions = (".lua",)

    def __init__(self, max_blank_lines: int = 2, remove_comments: bool = True) -> None:
        self.max_blank_lines = max_blank_lines
        self.remove_comments = remove_comments

    def process(self, source: str) -> str:
        if self.remove_comments:
            source = re.sub(r'--\[\[.*?\]\]', '', source, flags=re.DOTALL)
            source = re.sub(r'--.*', '', source)
        return PythonCommentRemover(self.max_blank_lines)._collapse_blanks(source.splitlines(keepends=True))
