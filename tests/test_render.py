"""Tests for the Rich render helpers and the prompt_toolkit fragment bridge.

These must run without a TTY — they exercise the ANSI->fragment bridge that
was fixed for prompt_toolkit 3.x (to_formatted_text(ANSI(...))).
"""

from rich.console import Group

from prompt_toolkit.formatted_text import ANSI, FormattedText

from ryft.ui.render import build_text
from ryft.ui.tui.render import to_fragments


def test_build_text_returns_group() -> None:
    out = build_text("test title", "line one\nline two")
    assert isinstance(out, Group)


def test_to_fragments_returns_formatted_text() -> None:
    ft = to_fragments(ANSI("\x1b[31mhello\x1b[0m"), width=40)
    assert isinstance(ft, FormattedText)

    tuples = list(ft)
    assert tuples
    assert any(txt for _, txt in tuples)


def test_to_fragments_handles_plain_text() -> None:
    ft = to_fragments("plain text with no escapes", width=30)
    assert isinstance(ft, FormattedText)
    assert "".join(txt for _, txt in ft).strip() == "plain text with no escapes"
