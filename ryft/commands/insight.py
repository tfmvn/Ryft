"""v2 insight commands: /ask, /search, /explain, /release, /memory.

These run through the provider registry (``ai.ask``) and the project knowledge
store, so they work with whatever providers are configured — not just local
Ollama — and never block the TUI event loop (``ai.ask`` is event-loop-safe).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console, Group
from rich.text import Text

from . import register
from .. import ai, git
from ..ui.render import build_ai_output, build_text
from ..ui.theme.palette import C

if TYPE_CHECKING:
    from ..models import AppContext

_console = Console()


@register(
    "ask",
    description="Ask the configured AI a question (uses the chat role)",
    usage=["/ask <question>"],
    examples=["/ask why is the build failing?"],
)
def cmd_ask(ctx: "AppContext", args: list[str]) -> None:
    from .. import ui

    if not args:
        ui.error("usage: /ask <question>")
        return
    try:
        answer = ai.ask(ctx, " ".join(args), role="chat")
    except Exception as exc:  # ProviderError or connection failure
        ui.error(f"ask failed: {exc}")
        return
    _console.print(build_ai_output(answer, "ask"))


@register(
    "search",
    description="Search the project's indexed symbols (semantic if embedded)",
    usage=["/search <term>"],
)
def cmd_search(ctx: "AppContext", args: list[str]) -> None:
    from .. import ui

    if not args:
        ui.error("usage: /search <term>")
        return
    term = " ".join(args)
    if ctx.knowledge is None:
        ui.error("knowledge store unavailable")
        return

    symbols = ctx.knowledge.search_symbols(term, limit=15)
    lines: list[Text] = [
        Text(f"symbol search: {term}", style=f"bold {C['primary']}"),
        Text(""),
    ]
    if not symbols:
        lines.append(Text("  no matching symbols", style=C["dim"]))
    for s in symbols:
        lines.append(
            Text(f"  {s.kind:<8} ", style=C["cyan"])
            + Text(s.name, style=f"bold {C['text']}")
            + Text(f"  {s.file}:{s.line}", style=C["dim"])
        )

    # Semantic layer: only when an embed provider is actually configured.
    if ctx.providers.supports_embed():
        try:
            vectors = ai.embed_texts(ctx, [term])
            if vectors:
                hits = ctx.knowledge.similar(vectors[0], k=5)
                if hits:
                    lines.append(Text(""))
                    lines.append(Text("semantic neighbors", style=f"bold {C['teal']}"))
                    for ref, kind, score in hits:
                        lines.append(
                            Text(f"  {kind:<8} {ref}  ({score:.2f})", style=C["dim"])
                        )
        except Exception:
            pass

    _console.print(Group(*lines))


@register(
    "explain",
    description="Explain a symbol using project knowledge + AI",
    usage=["/explain <symbol>"],
)
def cmd_explain(ctx: "AppContext", args: list[str]) -> None:
    from .. import ui

    if not args:
        ui.error("usage: /explain <symbol>")
        return
    term = " ".join(args)
    if ctx.knowledge is None:
        ui.error("knowledge store unavailable")
        return
    syms = ctx.knowledge.search_symbols(term, limit=5)
    if not syms:
        ui.error(f"no symbol matching '{term}'")
        return
    s = syms[0]
    context = (
        f"{s.kind} {s.name} (in {s.file}:{s.line})\n\n"
        f"signature:\n{s.signature}\n\ndoc:\n{s.doc}\n"
    )
    try:
        answer = ai.ask(
            ctx,
            context + "\nExplain what this does and any notable edge cases.",
            role="analyze",
        )
    except Exception as exc:
        ui.error(f"explain failed: {exc}")
        return
    _console.print(build_text(f"explain · {s.name}", answer))


@register(
    "release",
    description="Generate release notes from recent commits via AI",
    usage=["/release", "/release <n>"],
)
def cmd_release(ctx: "AppContext", args: list[str]) -> None:
    from .. import ui

    n = 20
    if args and args[0].isdigit():
        n = int(args[0])
    commits = git.recent_commits(ctx.config.root, n)
    if not commits:
        ui.success("no commits yet")
        return
    changelog = "\n".join(f"- {c['subject']} ({c['hash']})" for c in commits)
    try:
        notes = ai.ask(
            ctx,
            f"Recent commits:\n{changelog}\n\n"
            "Write concise release notes grouped by feature / fix / chore.",
            role="chat",
        )
    except Exception as exc:
        ui.error(f"release failed: {exc}")
        return
    _console.print(build_text("release notes", notes))


@register("memory", description="Show what Ryft has learned about this project")
def cmd_memory(ctx: "AppContext", args: list[str]) -> None:
    symbols = ctx.knowledge.symbol_count() if ctx.knowledge is not None else 0
    commits = (
        len(ctx.knowledge.recent_commits(1000)) if ctx.knowledge is not None else 0
    )
    providers = len(ctx.providers.list())
    services = len(ctx.services.state()) if ctx.services is not None else 0
    lines = [
        Text("project memory", style=f"bold {C['primary']}"),
        Text(""),
        Text(f"  indexed symbols : {symbols}"),
        Text(f"  known commits   : {commits}"),
        Text(f"  providers       : {providers}"),
        Text(f"  services        : {services}"),
    ]
    _console.print(Group(*lines))
