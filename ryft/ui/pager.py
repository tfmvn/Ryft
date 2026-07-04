"""Full-screen scrollable pager with keyboard navigation.

Keys: ↑/k  ↓/j  PgUp/u  PgDn/d  g(top)  G(bottom)  q/ESC(quit)
"""
from __future__ import annotations

from io import StringIO
from typing import TYPE_CHECKING

from prompt_toolkit.application import Application  # type: ignore[import]
from prompt_toolkit.formatted_text import ANSI, FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.patch_stdout import patch_stdout

from .colors import BG_OVERLAY, PTK_STYLE, TEXT_DIM, VIOLET, _THEME, _term_width, console

if TYPE_CHECKING:
    from rich.console import RenderableType


def _render_to_lines(renderable: "RenderableType", width: int) -> list[str]:
    """Render a Rich renderable to a list of ANSI-coloured strings, one per line."""
    from rich.console import Console
    buf = StringIO()
    c_local = Console(file=buf, force_terminal=True, width=width, theme=_THEME, highlight=False)
    c_local.print(renderable)
    raw = buf.getvalue()
    # Split on newlines but keep the ANSI codes per line
    return raw.split("\n")


def _pager(title: str, renderable: "RenderableType", *, width: int | None = None) -> None:
    """
    Full-screen scrollable pager.
    Keys: ↑/k  ↓/j  PgUp/u  PgDn/d  g(top)  G(bottom)  q/ESC(quit)
    """
    render_w = (width or _term_width()) - 2
    all_lines = _render_to_lines(renderable, render_w)

    state = {"top": 0}

    def _make_header() -> FormattedText:
        pct = int(state["top"] / max(1, len(all_lines)) * 100)
        return FormattedText([
            ("bg:" + BG_OVERLAY + " bold " + VIOLET, f"  {title}  "),
            ("bg:" + BG_OVERLAY + " " + TEXT_DIM,
             f"  ↑↓/jk · PgUp/d · PgDn/u · g/G top/bot · q quit"
             f"  [{pct}%]  "),
        ])

    def _make_body(rows: int) -> ANSI:
        visible = all_lines[state["top"]: state["top"] + rows]
        # pad to fill screen so background is consistent
        while len(visible) < rows:
            visible.append("")
        return ANSI("\n".join(visible))

    header_ctrl = FormattedTextControl(lambda: _make_header())
    header_win  = Window(height=1, content=header_ctrl, style="bg:" + BG_OVERLAY)

    body_ctrl = FormattedTextControl(lambda: _make_body(body_win.render_info.window_height if body_win.render_info else 40))
    body_win  = Window(content=body_ctrl, wrap_lines=False, always_hide_cursor=True)

    kb = KeyBindings()

    def _scroll(delta: int) -> None:
        rows = body_win.render_info.window_height if body_win.render_info else 40
        max_top = max(0, len(all_lines) - rows)
        state["top"] = max(0, min(state["top"] + delta, max_top))

    @kb.add("q")
    @kb.add("escape")
    def _quit(e): e.app.exit()

    @kb.add("up")
    @kb.add("k")
    def _up(e):   _scroll(-1)

    @kb.add("down")
    @kb.add("j")
    def _dn(e):   _scroll(1)

    @kb.add("pageup")
    @kb.add("u")
    def _pgup(e):
        rows = body_win.render_info.window_height if body_win.render_info else 40
        _scroll(-(rows - 2))

    @kb.add("pagedown")
    @kb.add("d")
    def _pgdn(e):
        rows = body_win.render_info.window_height if body_win.render_info else 40
        _scroll(rows - 2)

    @kb.add("g")
    def _top(e):  state["top"] = 0

    @kb.add("G")
    def _bot(e):
        rows = body_win.render_info.window_height if body_win.render_info else 40
        state["top"] = max(0, len(all_lines) - rows)

    app = Application(
        layout=Layout(HSplit([header_win, body_win])),
        key_bindings=kb,
        full_screen=True,
        style=PTK_STYLE,
        mouse_support=True,
    )
    with patch_stdout():
        app.run()
