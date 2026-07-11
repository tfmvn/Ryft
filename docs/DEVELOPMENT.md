# Ryft — Development Guide

## Layout

See `ARCHITECTURE.md`. The package is `ryft/`; docs are `docs/`; tests are
`tests/`.

## Setup

```bash
pip install -e ".[dev]"
ryft            # opens the TUI in the current project
```

## Running

```bash
ryft                      # interactive TUI
ryft doctor               # one-shot health check
ryft commit               # one-shot commit
python -m ryft --version  # version
```

## Testing

```bash
pytest                    # fast, offline, no network
```

Tests cover config loading (incl. `.src.py` backward-compat), provider
registry construction + capability detection, git helpers against the real
repo, the knowledge store/search round-trip, the Rich→prompt_toolkit fragment
bridge, and read-only one-shot command dispatch. They never require Ollama or
network.

## Coding style

- `from __future__ import annotations` at the top of every module.
- Type hints on **every** function signature.
- Dataclasses for data; protocols/ABCs for seams; no God classes.
- Lazy imports for heavy or circular deps; keep module-level import instant.
- Docstrings on every public symbol; comment *why*, not *what*.
- No dead code, no duplicated logic, no silent `except: pass`.
- Secrets come from env (`*_env` config keys), never stored in config files.

## Adding a command

```python
# ryft/commands/mycmd.py
from . import register

@register("mycmd", description="...", usage=["/mycmd"], examples=["/mycmd"])
def cmd_mycmd(ctx, args):
    ...
```

`register` takes `name`, `description`, and optional `usage` / `examples` /
`aliases` — there is **no** `group` kwarg. Drop the module into
`ryft/commands/` and add a side-effect import in `commands/__init__.py` so the
registry picks it up.

## Adding a provider

Implement `AIProvider` (see `PROVIDER_API.md`); register via entry point or
plugin. No change to core required.

## Adding a plugin

Implement `RyftPlugin` (see `PLUGIN_API.md`); drop in
`~/.config/ryft/plugins` or ship an entry point. Use only the `PluginAPI`
facade.

## Contribution guide

- One logical change per PR; conventional commits.
- `ryft doctor` must pass; `pytest` must be green.
- Public APIs get docstrings; user-facing changes update `docs/`.
- Keep startup instant and the UI non-blocking.

## Architecture decisions worth remembering

- Trusted `.src.py` is *executed*, not parsed — keeps it scriptable.
- Git state is observed by the `git_monitor` service and surfaced as events;
  the dashboard re-renders on events rather than polling per paint.
- AI gets a compact *semantic* diff summary, never raw 4k diffs.
- The UI is two modes (TUI + one-shot Rich) sharing one design system.
- We stayed on prompt_toolkit + Rich (no Textual) — see `ARCHITECTURE.md`.
