"""Formatting. Currently one formatter (Python comment stripping +
blank-line collapsing) but built so another language could register an
extension -> processor mapping without restructuring anything.
"""

from __future__ import annotations

import ast
import io
import tokenize
import re
from pathlib import Path


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
    

FORMATTERS = {
    ".py": PythonCommentRemover,
    ".lua": LuaCommentRemover
}


def format_file(path: Path, max_blank_lines: int = 2, remove_comments: bool = True) -> bool:
    """Format one file in place. Returns True if it changed."""
    cls = FORMATTERS.get(path.suffix.lower())
    if cls is None:
        return False

    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return False

    processor = cls(max_blank_lines=max_blank_lines, remove_comments=remove_comments)
    cleaned = processor.process(source)
    
    if cleaned == source:
        return False
    
    if path.suffix.lower() == ".py":
        try:
            ast.parse(cleaned)
        except SyntaxError:
            return False 
    
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(cleaned, encoding="utf-8")
    tmp.replace(path)
    return True

# src/formatter.py
def format_paths(paths: list[Path], max_blank_lines: int = 2, remove_comments: bool = True) -> list[Path]:
    changed = []
    for p in paths:
        if format_file(p, max_blank_lines=max_blank_lines, remove_comments=remove_comments):
            changed.append(p)
    return changed