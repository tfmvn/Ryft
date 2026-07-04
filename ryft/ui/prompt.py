"""One-line output helpers (info, success, warn, error), confirm, and
run_model_pull.

These are the functions called by command handlers and onboarding to print
status messages. ``_ctx`` is accepted but ignored — this matches the
original signatures so callers that accidentally pass a context still work.
"""
from __future__ import annotations

from rich.markup import escape
from rich.prompt import Confirm
from rich.text import Text

from .colors import VIOLET, AMBER, CORAL, MINT, TEXT_HI, TEXT_MID, TEXT_DIM, _rule, _sp, console
from .icons import _I


def info(msg: str,    _ctx=None) -> None: console.print(f"  [{TEXT_DIM}]{_I['arrow']}[/]  [{TEXT_MID}]{escape(msg)}[/]")
def success(msg: str, _ctx=None) -> None: console.print(f"  [{MINT}]{_I['check']}[/]  [{TEXT_MID}]{escape(msg)}[/]")
def warn(msg: str,    _ctx=None) -> None: console.print(f"  [{AMBER}]{_I['warn']}[/]  [{TEXT_MID}]{escape(msg)}[/]")
def error(msg: str,   _ctx=None) -> None: console.print(f"  [{CORAL}]{_I['cross']}[/]  [{TEXT_MID}]{escape(msg)}[/]")


def confirm(question: str, default: bool = True) -> bool:
    """Styled Y/n prompt used by onboarding and auto-recovery flows."""
    _sp()
    for line in question.splitlines():
        console.print(f"  [{TEXT_HI}]{escape(line)}[/]" if line.strip() else "")
    try:
        return Confirm.ask(f"  [{VIOLET}]?[/]", default=default, console=console)
    except (EOFError, KeyboardInterrupt):
        return False


def run_model_pull(model: str) -> bool:
    """Run `ollama pull <model>` with a live status line, returning success."""
    from .. import ai as ai_mod

    state = {"line": ""}
    with console.status(
        Text(f"  Downloading {model}…", style=VIOLET),
        spinner="dots", spinner_style=VIOLET,
    ) as st:
        def _on_line(line: str) -> None:
            clean = line.strip()
            if clean:
                state["line"] = clean
                st.update(Text(f"  {model}  ·  {clean}", style=VIOLET))

        ok = ai_mod.pull_model_cli(model, on_line=_on_line)

    if ok:
        success(f"{model} downloaded")
    else:
        error(f"{model} download failed" + (f" — {state['line']}" if state["line"] else ""))
    return ok
