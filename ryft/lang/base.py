"""The formatter interface every language plugs into (Layer 2/3), and the
configurable cleanup options a formatter may or may not honor (Layer 4).

Nothing in here knows about any specific language. `ryft.formatter`
depends on this module; individual language modules (`python_lang.py`,
`lua_lang.py`, ...) implement it.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class FormatOptions:
    """Semantic Cleanup options (Layer 4).

    A formatter that can't support a given option should just ignore it
    rather than error — see each `*_lang.py` module for what it actually
    honors.
    """

    remove_comments: bool = True
    remove_docstrings: bool = False
    trim_trailing_whitespace: bool = True
    collapse_blank_lines: bool = True
    normalize_line_endings: bool = True
    insert_final_newline: bool = True
    max_blank_lines: int = 2


class LanguageFormatter(ABC):
    """One language's formatter. Declares what it handles, and knows how
    to format text — nothing else. Detection, ignore rules, writing to
    disk, and reporting all live in `ryft.formatter`, not here."""

    name: str = "Text"
    extensions: tuple[str, ...] = ()

    @abstractmethod
    def format(self, text: str, options: FormatOptions) -> str:
        """Return the formatted text.

        Must never intentionally change program behavior. When a
        transformation can't be performed safely, return `text`
        unchanged (or fall back to `ryft.lang.normalize.normalize`)
        rather than guess.
        """
        raise NotImplementedError


class StubFormatter(LanguageFormatter):
    """Placeholder for a language Ryft recognizes but doesn't have a real
    formatter for yet. Applies only the universal normalizer — nothing
    language-specific — so it's always safe to register.

    Swapping a stub out for a real formatter later is just registering a
    new `LanguageFormatter` for the same extensions; nothing else in the
    pipeline or registry has to change.
    """

    def __init__(self, name: str, extensions: tuple[str, ...]) -> None:
        self.name = name
        self.extensions = extensions

    def format(self, text: str, options: FormatOptions) -> str:
        from .normalize import normalize

        return normalize(text, options)
