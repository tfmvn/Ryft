"""Python language formatter.

Wraps the original `tokenize`-based comment remover unchanged, and adds
an optional, best-effort docstring-removal pass on top. Comment/docstring
stripping only ever runs on source that still parses afterward — if a
transform would leave the file unparsable (e.g. removing a function's
only statement), it's discarded and the original text is kept. The
pipeline's own validation stage (`ryft.formatter.pipeline`) double-checks
this before anything is written to disk.
"""
from __future__ import annotations

import ast

from . import register
from .base import FormatOptions, LanguageFormatter
from .legacy import PythonCommentRemover
from .normalize import normalize


class PythonFormatter(LanguageFormatter):
    name = "Python"
    extensions = (".py",)

    def format(self, text: str, options: FormatOptions) -> str:
        if not text:
            return text

        remover = PythonCommentRemover(
            max_blank_lines=options.max_blank_lines,
            remove_comments=options.remove_comments,
        )
        result = remover.process(text)

        if options.remove_docstrings:
            result = _strip_docstrings(result)

        return normalize(result, options)


def _strip_docstrings(source: str) -> str:
    """Best-effort docstring removal, safe by construction: falls back to
    the untouched source rather than risk producing anything that
    doesn't parse."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return source

    doc_lines: set[int] = set()

    def visit(node: ast.AST) -> None:
        body = getattr(node, "body", None)
        if body and isinstance(body[0], ast.Expr):
            value = body[0].value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                doc_lines.update(range(body[0].lineno, body[0].end_lineno + 1))
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(tree)
    if not doc_lines:
        return source

    lines = source.splitlines(keepends=True)
    kept = [line for i, line in enumerate(lines, start=1) if i not in doc_lines]
    candidate = "".join(kept)

    try:
        ast.parse(candidate)
    except SyntaxError:
        # e.g. a function whose only statement was its docstring — would
        # leave an empty body. Prefer no change over a risky one.
        return source
    return candidate


register(PythonFormatter())
