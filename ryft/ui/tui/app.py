"""Full-screen TUI application shell.

A prompt_toolkit `Application` with three regions: a status bar, a body that
renders the Rich-composed dashboard / palette / help / result, and a bottom line
that is either key hints (dashboard mode) or the command-input `TextArea`
(palette mode). Modes are switched by reassigning the layout container; the body
is re-rendered on every `invalidate()` from Rich via `render.to_fragments`.

No business logic lives here beyond wiring keys to commands — handlers come
from the command registry and are invoked synchronously (long work should be
async services; command handlers are expected to be quick or return a
renderable).
"""

from __future__ import annotations

from typing import Any

from prompt_toolkit import Application
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings, merge_key_bindings
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.widgets import TextArea

from ..theme.palette import C, ptk_style
from . import dashboard, palette as palette_ui
from .render import to_fragments


class RyftTUI:
    def __init__(self, ctx, commands: list) -> None:
        self.ctx = ctx
        self.commands = commands
        self.mode = "dashboard"  # dashboard | palette | help | result
        self.query = ""
        self.selected = 0
        self.result: Any = None
        self._last_width = 80

        self.input = TextArea(
            prompt="❯ ", multiline=False, wrap_lines=False,
            style="class:palette.prompt",
            accept_handler=self._on_accept,
        )
        self.input.text = ""

        # Live-filter the palette as the user types (BLOCKER B fix #2): keep
        # `self.query` in sync with the TextArea buffer so filtering reacts.
        self.input.buffer.on_text_changed.add_handler(self._on_query_changed)
        # Arrow navigation + escape must work *while the TextArea is focused*, so
        # they live on the input's own key bindings (prepended so BufferControl's
        # default up/down/escape don't swallow them). BLOCKER B fix #1.
        _palette_kb = KeyBindings()
        _palette_kb.add("up", filter=Condition(lambda: self.mode == "palette"))(self._nav_up)
        _palette_kb.add("down", filter=Condition(lambda: self.mode == "palette"))(self._nav_down)
        _palette_kb.add("escape", filter=Condition(lambda: self.mode == "palette"))(self._palette_esc)
        # A fresh TextArea's control has `key_bindings = None`; `merge_key_bindings`
        # does NOT drop it, so a None would leak into the registry and crash
        # PTK's binding cache the moment the input is focused and typed into.
        base_kb = self.input.control.key_bindings
        self.input.control.key_bindings = merge_key_bindings(
            [_palette_kb, base_kb] if base_kb is not None else [_palette_kb]
        )

        self._bindings = self._build_bindings()
        self.app: Application | None = None
        # re-render on git changes so the dashboard stays live
        ctx.events.subscribe("git.state.changed", lambda _e: self._refresh())

    # ── layout ────────────────────────────────────────────────────────────

    def _body_renderable(self) -> Any:
        if self.mode == "palette":
            return palette_ui.build_palette(self.commands, self.query, self.selected)
        if self.mode == "help":
            return self._help_renderable()
        if self.mode == "result":
            return self.result if self.result is not None else "done"
        return dashboard.build_dashboard(self.ctx, self.commands)

    def _body_text(self) -> Any:
        try:
            from prompt_toolkit.application import get_app
            width = get_app().output.get_size().columns
        except Exception:
            width = self._last_width
        self._last_width = width
        return to_fragments(self._body_renderable(), width)

    def _status_text(self) -> Any:
        from prompt_toolkit.application import get_app
        width = get_app().output.get_size().columns
        branch = "—"
        try:
            from ... import git as gitsys
            branch = gitsys.current_branch(self.ctx.root)
        except Exception:
            pass
        if self.mode == "palette":
            mode = "palette"
        elif self.mode == "help":
            mode = "help"
        elif self.mode == "result":
            mode = "result"
        else:
            mode = "ready"
        text = f" RYFT · {self.ctx.config.project.name} · {branch} · {mode}"
        pad = max(0, width - len(text) - 1)
        return [("class:statusbar", text), ("class:statusbar.dim", " " * pad)]

    def _bottom_text(self) -> Any:
        return [("class:faint",
                 "  : or Ctrl+P command palette   ·   r refresh   ·   ? help   ·   q quit")]

    def _make_container(self) -> HSplit:
        status = Window(content=FormattedTextControl(self._status_text), height=1)
        body = Window(content=FormattedTextControl(self._body_text), wrap_lines=False)
        if self.mode == "palette":
            bottom = self.input
        else:
            bottom = Window(content=FormattedTextControl(self._bottom_text), height=1)
        return HSplit([status, body, bottom])

    def _refresh(self) -> None:
        if self.app is not None:
            self.app.invalidate()

    def _on_query_changed(self, buffer) -> None:
        """Keep the palette filter in sync with what is typed in the input."""
        self.query = buffer.text
        self.selected = 0
        self._refresh()

    # ── palette navigation (bound on the input's own key bindings) ──────────

    def _nav_up(self, event) -> None:
        if self.selected > 0:
            self.selected -= 1
        self._refresh()

    def _nav_down(self, event) -> None:
        matches = palette_ui.filter_commands(self.commands, self.query)
        if matches and self.selected < len(matches) - 1:
            self.selected += 1
        self._refresh()

    def _palette_esc(self, event) -> None:
        self.mode = "dashboard"
        self.result = None
        self._swap_layout()

    # ── key bindings ────────────────────────────────────────────────────────

    def _build_bindings(self) -> KeyBindings:
        kb = KeyBindings()

        @kb.add("q")
        def _quit(event) -> None:
            if self.mode in ("dashboard",):
                event.app.exit()

        @kb.add("c-c")
        def _sigint(event) -> None:
            event.app.exit()

        @kb.add(":")
        @kb.add("c-p")
        def _palette(event) -> None:
            self.mode = "palette"
            self.query = ""
            self.selected = 0
            self.input.text = ""
            self._swap_layout()

        @kb.add("r")
        def _refresh_key(event) -> None:
            self._force_refresh()
            self._refresh()

        @kb.add("?")
        def _help(event) -> None:
            self.mode = "help"
            self._swap_layout()

        @kb.add("escape")
        def _esc(event) -> None:
            if self.mode in ("palette", "help", "result"):
                self.mode = "dashboard"
                self.result = None
                self._swap_layout()

        # result mode: any key dismisses
        @kb.add("enter", filter=Condition(lambda: self.mode == "result"))
        def _dismiss(event) -> None:
            self.mode = "dashboard"
            self.result = None
            self._swap_layout()

        return kb

    def _swap_layout(self) -> None:
        if self.app is not None:
            self.app.layout.container = self._make_container()
            # Palette mode needs the command input focused so typing is captured
            # by its buffer; other modes leave focus untouched (prompt_toolkit
            # tolerates an unfocused layout and app-level key bindings still fire).
            if self.mode == "palette":
                self.app.layout.focus(self.input)
            self._refresh()

    def _on_accept(self, buffer) -> bool:
        """Enter pressed in palette: run the highlighted command."""
        matches = palette_ui.filter_commands(self.commands, self.query)
        if not matches:
            return True
        spec = matches[min(self.selected, len(matches) - 1)]
        self._run_command(spec, self.query)
        return True

    def _run_command(self, spec, raw_query: str) -> None:
        # strip leading command name from the query to form args
        rest = raw_query.strip()
        if rest.startswith("/") or rest.startswith(":"):
            rest = rest[1:]
        args = rest.split()[1:] if rest and spec.name in rest.split()[:1] else []
        try:
            out = spec.handler(self.ctx, args)
        except Exception as exc:  # noqa: BLE001 - command errors surface, not crash
            out = f"[error] {spec.name}: {exc}"
        self.result = out if out else f"✓ {spec.name} done"
        self.mode = "result"
        self._swap_layout()

    def _force_refresh(self) -> None:
        if self.ctx.services is not None:
            idx = self.ctx.services.get("indexer")
            if idx is not None:
                try:
                    idx.reindex_now()
                except Exception:  # noqa: BLE001
                    pass

    def _help_renderable(self) -> Any:
        from rich.console import Group
        from rich.text import Text
        from ..components import header_line, panel

        rows = [(f"/{c.name}", C["primary"]) for c in self.commands]
        lines = [header_line("help", f"{len(self.commands)} commands")]
        for c in self.commands:
            lines.append(Text(f"  /{c.name:<18}", style=f"bold {C['primary']}") +
                         Text(c.description, style=C["dim"]))
        lines.append(Text(""))
        lines.append(Text("  press esc to return", style=C["faint"]))
        return panel("help", Group(*lines))

    # ── run ────────────────────────────────────────────────────────────────

    def run(self) -> None:
        self.app = Application(
            layout=Layout(self._make_container()),
            key_bindings=self._bindings,
            style=ptk_style(),
            full_screen=True,
            mouse_support=False,
            erase_when_done=False,
        )
        self.app.run()
