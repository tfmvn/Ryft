# Ryft — Plugin API

Everything user-extensible in Ryft is a plugin behind a small contract. A
plugin is **any** object (a plain module works) that exposes `meta` (a
`PluginMeta`) and a `register(api)` method. The manager discovers plugins,
builds a `PluginAPI` per plugin, calls `register`, then drains the collected
commands/providers/services/panels into the live runtime. A bad plugin never
breaks the others — it's logged and skipped.

---

## The contract

```python
from dataclasses import dataclass

@dataclass
class PluginMeta:
    name: str
    version: str = "0.1.0"
    description: str = ""
    author: str = ""
```

```python
from typing import Protocol

class RyftPlugin(Protocol):
    meta: PluginMeta
    def register(self, api: "PluginAPI") -> None: ...
```

`register(api)` is called exactly once at load. That's the whole lifecycle —
there is no separate `setup`/`teardown`. Use `api.log(...)` for status, and rely
on the activity feed for "loaded" confirmation.

---

## The `PluginAPI` facade

This is the **only** surface a plugin should touch. It exposes a read-only view
of the context plus registration methods; the manager connects the collected
items to the real registries after `register()` returns.

```python
class PluginAPI:
    ctx: AppContext          # read-only access to wiring
    meta: PluginMeta

    def register_command(self, spec: "CommandSpec") -> None
    def register_provider(self, name: str, provider) -> None
    def register_service(self, factory: "Callable[[AppContext], Service]") -> None
    def register_panel(self, panel) -> None
    def log(self, message: str) -> None
```

A plugin may only use the facade — it cannot import `ryft.ui` internals or
mutate `ctx` directly. This keeps plugins isolated and the core stable.

---

## Discovery & loading

1. **Entry points** in the `ryft.plugins` group (pip-installed packages).
2. **Directory scan** of `~/.config/ryft/plugins` and
   `<project>/.ryft/plugins`, plus any paths in `RYFT_PLUGIN_PATH`
   (colon-separated).
3. Each candidate must expose a valid `meta` and a `register(api)` method.
4. `register(api)` runs; the manager drains commands/providers/services/panels
   into the live registries. Failures are logged and reported by `ryft plugins`
   (a bad plugin never crashes the CLI).

```bash
ryft plugins        # list loaded plugins + their versions
```

> Note: there are no `plugins enable|disable|install` subcommands yet — drop a
> `*.py` file into `~/.config/ryft/plugins` (or set `RYFT_PLUGIN_PATH`), and it
> is picked up on the next run.

---

## Example: a command plugin

```python
# ~/.config/ryft/plugins/hello.py
from ryft.models import CommandSpec, PluginMeta


class HelloPlugin:
    meta = PluginMeta(name="hello", description="Say hi")

    def register(self, api):
        api.register_command(CommandSpec(
            name="hello",
            description="Greet the user",
            handler=lambda ctx, args: api.log("hi from hello plugin"),
        ))
```

## Example: a provider plugin

```python
from ryft.models import PluginMeta
from ryft.providers.base import AIProvider, ProviderHealth


class AcmeProvider:
    name = "acme"

    def capabilities(self):
        return {"chat", "stream"}

    def health(self) -> ProviderHealth:
        ...

    async def chat(self, messages, **opts):
        ...


class AcmePlugin:
    meta = PluginMeta(name="acme-ai")

    def register(self, api):
        api.register_provider("acme", AcmeProvider())
```

---

## Lifecycle & isolation

- Plugins load after core subsystems, before the TUI.
- A plugin that raises during `register` is disabled and listed as failed.
- Plugins run in the host process (no separate runtime) for startup speed;
  they must be cooperative (no blocking the UI thread).
- A convenience `Plugin` base class (`ryft.plugins.spec.Plugin`) is offered for
  authors who want to subclass instead of writing a bare object.
