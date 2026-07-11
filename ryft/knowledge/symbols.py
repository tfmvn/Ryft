"""Source symbol extraction.

For Python we use the `ast` module (accurate: we get real line ranges, docstrings,
and signatures). For every other language we fall back to a small set of
declaration regexes covering the common cases (function/class/struct/method
definitions in JS/TS, Go, Rust, Java, C#, Ruby). The heuristic is intentionally
lenient — it powers *search and navigation*, not compilation, so false positives
are harmless and misses just mean one fewer searchable symbol.

All extractors return `(content_hash, [Symbol])` so the indexer can skip files
whose hash is unchanged.
"""

from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .store import Symbol

_PY_EXT = {".py"}
_FUNC_RE = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_]\w*)\s*\("
    r"|^\s*func\s+([A-Za-z_]\w*)\s*\("          # Go
    r"|^\s*fn\s+([A-Za-z_]\w*)\s*\("            # Rust
    r"|^\s*def\s+([A-Za-z_]\w*)\s*\("           # Ruby / Python-ish
    r"|^\s*(?:public|private|protected|internal|static)?\s*[\w<>\[\],\s]+\s+([A-Za-z_]\w*)\s*\(",  # Java/C#
)
_CLASS_RE = re.compile(
    r"^\s*(?:export\s+)?(?:abstract\s+)?(?:final\s+)?"
    r"(?:class|interface|struct|enum|trait)\s+([A-Za-z_]\w*)"
)


@dataclass
class ExtractResult:
    hash: str
    symbols: list[Symbol]


def hash_text(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:16]


def extract(path: Path, root: Path, text: str | None = None) -> ExtractResult:
    text = text if text is not None else _read(path)
    h = hash_text(text)
    if path.suffix.lower() in _PY_EXT:
        symbols = _extract_python(path, root, text)
    else:
        symbols = _extract_heuristic(path, root, text)
    return ExtractResult(hash=h, symbols=symbols)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return path.name


def _extract_python(path: Path, root: Path, text: str) -> list[Symbol]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []
    _annotate_parents(tree)
    rel = _rel(path, root)
    lines = text.splitlines()
    out: list[Symbol] = []

    def _sig(node: ast.AST) -> str:
        start = node.lineno - 1
        sig_lines = []
        for ln in lines[start:]:
            sig_lines.append(ln)
            if ln.rstrip().endswith(":"):
                break
        return re.sub(r"\s+", " ", " ".join(sig_lines)).strip()[:160]

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = "method" if _in_class(node) else "function"
            out.append(Symbol(
                name=node.name, kind=kind, file=rel,
                line=node.lineno, end_line=getattr(node, "end_lineno", node.lineno),
                signature=_sig(node), doc=ast.get_docstring(node) or "",
                hash="",
            ))
        elif isinstance(node, ast.ClassDef):
            out.append(Symbol(
                name=node.name, kind="class", file=rel,
                line=node.lineno, end_line=getattr(node, "end_lineno", node.lineno),
                signature=_sig(node), doc=ast.get_docstring(node) or "",
                hash="",
            ))
    return out


def _in_class(node: ast.AST) -> bool:
    parent = getattr(node, "parent", None)
    while parent is not None:
        if isinstance(parent, ast.ClassDef):
            return True
        parent = getattr(parent, "parent", None)
    return False


def _extract_heuristic(path: Path, root: Path, text: str) -> list[Symbol]:
    rel = _rel(path, root)
    lines = text.splitlines()
    out: list[Symbol] = []
    for i, line in enumerate(lines, start=1):
        m = _CLASS_RE.match(line)
        if m:
            out.append(Symbol(
                name=m.group(1), kind="class", file=rel, line=i, end_line=i,
                signature=line.strip()[:160], doc="", hash="",
            ))
            continue
        m = _FUNC_RE.match(line)
        if m:
            name = next(g for g in m.groups() if g)
            out.append(Symbol(
                name=name, kind="function", file=rel, line=i, end_line=i,
                signature=line.strip()[:160], doc="", hash="",
            ))
    return out


# Track parent pointers so _in_class works during the single walk.
def _annotate_parents(tree: ast.AST) -> None:
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            child.parent = parent  # type: ignore[attr-defined]
