# Ryft — Architecture

> Ryft is the AI-native operating system for a software project: Git, GitHub,
> AI, project knowledge, architecture explorer, session recorder, repository
> intelligence, release manager, code search, developer dashboard, terminal
> IDE, and automation engine — composed into one calm, fast terminal
> application.

This document describes the **v2** architecture: a ground-up redesign of the
v1.0.1 tool (a git companion with Ollama commit messages). It preserves the
parts of v1 that were already good and replaces the parts that limited growth.

---

## 1. Design principles

These are the non-negotiable constraints any future change must respect.

| Principle | What it means in practice |
| --- | --- |
| **No God classes** | Every module has one job. `AppContext` is a *bag of references*, not a god object. Providers, services, and commands are independent. |
| **Lazy everything** | Importing `ryft` must be instant and side-effect free. Heavy machinery (AI clients, indexers, the TUI) loads on demand. |
| **Pluggable by default** | AI, language intelligence, formatters, review engines, and dashboard widgets are plugins behind interfaces — nothing is hardcoded. |
| **Background, never blocking** | The UI thread never waits on git, AI, or indexing. All slow work runs in managed workers. |
| **One source of truth for state** | Git state is observed by the `git_monitor` service and surfaced as events; AI availability through provider health; knowledge through the store. |
| **Trusted config** | `.src.py` is user-authored Python (same trust as the old `.src` TOML). It is executed, not parsed, so it stays scriptable. |
| **Graceful degradation** | No AI? Templates. No GitHub token? Local-only. No embeddings? Grep. Every capability negotiates at runtime. |
| **Offline-first** | Cached AI responses, a local knowledge store, and a last-known-good dashboard survive network loss. |

---

## 2. Layered module map

```text
ryft/
├── __init__.py            # __version__ = "2.0.0"
├── __main__.py            # entry: `ryft` (TUI) | `ryft <cmd>` (one-shot)
├── ai.py                  # ai.ask / ai.embed_texts + local Ollama client
├── git.py                 # every git invocation goes through here
├── fs.py                  # file discovery, binary detection, paths
├── config.py              # facade over core.config.loader + is_ignored/set_model
├── formatter/             # comment stripping / blank-line collapsing
├── pipeline.py            # format → message → commit pipeline
├── sync.py                # file-watch → format → commit → push (SyncController)
├── recovery.py            # shared auto-repair helpers (used by doctor)
├── onboarding.py          # first-run setup flow
├── logging_setup.py       # logging to <root>/.ryft/ryft.log
│
├── core/                  # cross-cutting, depends on nothing above it
│   ├── context.py         # AppContext — the central wiring object
│   ├── events.py          # EventBus + typed events
│   ├── lifecycle.py       # build_context() / shutdown()
│   ├── models.py          # ActivityEvent / SyncStatus / CommandSpec
│   └── config/            # v2 schema + loaders (backward-compat w/ .src.py)
│       ├── schema.py      # Config + sub-configs
│       └── loader.py      # ryft.toml / pyproject [tool.ryft] / .src.py
│
├── providers/             # AI providers (pluggable, interface-first)
│   ├── base.py            # AIProvider protocol, Message, Usage, StreamChunk
│   ├── registry.py        # ProviderRegistry + capability detection
│   ├── factory.py         # build providers from config
│   ├── ollama.py          # local Ollama
│   ├── openai_compatible.py  # base for any /v1 endpoint (OpenAI, LM Studio, …)
│   ├── anthropic.py       # Anthropic (Messages API)
│   └── google.py          # Google Gemini
│
├── knowledge/             # repository intelligence (offline store)
│   ├── store.py           # SQLite-backed index (symbols, commits)
│   ├── symbols.py         # symbol extraction (ast + generic)
│   ├── indexer.py         # builds/updates the store (used by a service)
│   └── search.py          # grep + semantic search
│
├── services/              # managed background workers
│   ├── manager.py         # ServiceManager (start/stop/health)
│   ├── base.py            # Service / Worker base classes
│   ├── git_monitor.py     # watches git state, emits events
│   ├── indexer.py         # continuously re-indexes the repo
│   └── ai_cache.py        # caches + evicts AI responses
│
├── plugins/               # plugin system
│   ├── spec.py            # Plugin protocol + metadata
│   ├── manager.py         # discovery (entry points + path) + load
│   └── api.py             # PluginAPI facade (safe surface for plugins)
│
├── _legacy_ui/            # frozen renderer toolkit (diff/pager/Live views)
│   ├── activity.py  colors.py  dashboard.py  icons.py
│   ├── pager.py  prompt.py  render.py  __init__.py
│
├── ui/
│   ├── theme/             # DESIGN SYSTEM (palette, tokens, components)
│   │   ├── palette.py     # colors (semantic + raw) + ptk_style()
│   │   ├── tokens.py      # spacing/typography/radius/borders
│   │   └── components.py   # Panel, Box, Bar, Table, Tree, Badge, KPI
│   ├── tui/               # full-screen TUI app shell (PTK + Rich)
│   │   ├── app.py         # RyftTUI — layout, focus, key routing
│   │   ├── dashboard.py   # the home screen (panels)
│   │   ├── palette.py     # command palette overlay
│   │   └── render.py      # Rich renderable → prompt_toolkit fragments
│   ├── render.py          # Rich render helpers (diff viewer, etc.)
│   └── __init__.py        # re-exports v2 modules + _legacy_ui toolkit
│
├── commands/              # the command hierarchy (registry + handlers)
│   ├── __init__.py        # register()/dispatch()/dispatch_argv()/REGISTRY
│   ├── commit.py  config.py  doctor.py  format.py  help.py
│   ├── insight.py         # ask, search, explain, release, memory
│   ├── sync.py             # watch, sync
│   ├── ai.py              # analyze, review, message, model
│   └── system.py          # providers, plugins, github, cloud, dashboard,
│                          #   graph, timeline, sessions, status, root,
│                          #   tree, files, activity, init, log, diff, git,
│                          #   push, pull, exit
│
└── lang/                  # language intelligence (formatting/extraction)
    ├── base.py  python_lang.py  lua_lang.py  json_lang.py
    ├── legacy.py  normalize.py  stubs.py
```

### Dependency rule

Arrows point downward and inward only:

```text
__main__ → commands → (ui | providers | knowledge | services)
commands → core (context/events/config)
ui → core, providers, knowledge
services → core, providers, knowledge, git, fs
plugins → plugins/api (PluginAPI) → (everything safe)
```

`core`, `git`, and `fs` depend on nothing internal. `ryft/ui/__init__.py`
re-exports both the v2 modules (`components`, `render`, `theme`) and the frozen
`_legacy_ui` renderer toolkit; `_legacy_ui` imports `ryft.commands` **lazily**
so there is no import cycle. Providers never import UI. This keeps startup
instant and tests trivial.

---

## 3. Core runtime

### 3.1 `AppContext`

A plain dataclass that holds *references* to the long-lived subsystems. It is
constructed once at startup and threaded through every command and service.
It is **not** a god object — it holds no business logic, only wiring.

```python
@dataclass
class AppContext:
    root: Path
    config: Config
    events: EventBus
    providers: ProviderRegistry
    activity: ActivityFeed = field(default_factory=ActivityFeed)
    knowledge: Any | None = None      # KnowledgeStore, attached at build
    services: Any | None = None       # ServiceManager, attached at build
    plugins: Any | None = None        # PluginManager, attached at build
    ui: Any | None = None             # set when the TUI is active
    ai: Any | None = None             # legacy compat; None in v2
    sync: Any | None = None           # SyncController, attached at build
    sync_status: SyncStatus = field(default_factory=SyncStatus)
    running: bool = True
```

`build_context()` attaches `knowledge`, `plugins`, `services`, and `sync` after
constructing the bag; they are typed `Any | None` so one-shot commands that
never touch them stay import-light.

### 3.2 `EventBus`

A tiny typed pub/sub. Workers and commands communicate through events, never
by calling each other directly. Examples: `GitStateChanged`,
`IndexProgress`, `AiCacheHit`, `ProviderHealthChanged`, `ActivityLogged`.

This decouples the dashboard (a subscriber) from the services that produce
state, so the UI can re-render without polling.

### 3.3 Lifecycle

`build_context(root, start_services=False)` resolves the project root, loads
config, builds the provider registry, and attaches the knowledge store, plugin
manager, service manager, and sync controller. Background services start only
when `start_services=True` (the bare TUI); one-shot commands never spawn worker
threads. First-run onboarding is driven separately by `ryft init` /
`onboarding.py`, not by `build_context`. `shutdown(ctx)` is cooperative and
idempotent: it sets `ctx.running = False`, stops services, and shuts down
plugins.

---

## 4. Providers (AI abstraction)

One interface, many implementations. A provider *declares* its capabilities
(`chat`, `stream`, `embed`, `reasoning`, `tools`) and the registry negotiates
which provider to use for a given role.

```python
class AIProvider(Protocol):
    name: str
    async def chat(self, messages, **opts) -> ChatResult: ...
    async def stream(self, messages, **opts) -> AsyncIterator[StreamChunk]: ...
    async def embed(self, texts) -> list[list[float]]: ...
    def health(self) -> ProviderHealth: ...
```

- **Ollama** — local, zero-cost, default for commit messages.
- **OpenAI-compatible** — one base client serving OpenAI, Together, OpenRouter,
  Groq, Fireworks, DeepInfra, NVIDIA NIM, and any `/v1` endpoint.
- **Anthropic** — Messages API (extended thinking, tool use).
- **Google** — Gemini.
- **Future** — any provider behind an entry-point plugin.

Roles (`commit`, `analyze`, `review`, `chat`, `embed`, `agent`) map to
provider + model via config, so a user can run commits on a tiny local model
and architecture reviews on a frontier model.

---

## 5. Knowledge (repository intelligence)

A SQLite store under `.ryft/knowledge.db` holds an efficient, queryable model
of the repo:

- **symbols** — functions, classes, methods, constants (extracted via `ast` for
  Python, generic heuristics for other languages).
- **commits** — recent git history, captured so timeline/search don't shell out.
- **embeddings** — optional, for semantic search (provider-backed, cached
  locally); `ryft search` uses them when the `embed` role is available and
  falls back to a symbol-name lookup otherwise.

The `indexer` service keeps it fresh in the background. `ryft search` and
`ryft explain` (symbol lookup + AI explanation) read from the store without
hitting the network. Issues/PRs/releases and doc indexing are roadmap items.

---

## 6. Services (background workers)

`ServiceManager` owns a set of named workers, each in its own thread/loop:

| Service | Responsibility | Emits |
| --- | --- | --- |
| `git_monitor` | detects branch/status/remote changes | `GitStateChanged` |
| `indexer` | re-indexes the repo on a debounce | `IndexProgress`, `IndexReady` |
| `ai_cache` | caches + evicts AI responses | `AiCacheHit` |

All are async/threaded and never block the UI. They degrade to no-ops when
their dependency is unavailable (e.g. no GitHub token → issue sync disabled).

---

## 7. Plugins

Everything user-extensible is a plugin behind a protocol. Plugins are
discovered via **Python entry points** (`ryft.plugins`) and **path scanning**
(`~/.config/ryft/plugins`, `<project>/.ryft/plugins`, `RYFT_PLUGIN_PATH`). A
`PluginAPI` facade exposes only the safe surface (`ctx`, `log`,
`register_command`, `register_provider`, `register_service`, `register_panel`)
so a plugin can extend Ryft without reaching into internals.

Built-in plugin *kinds* (by what they register): command, provider, service,
dashboard-panel. The manager drains registered items into the live registries
after the plugin's `register(api)` runs.
ai-provider.

---

## 8. UI (design system + TUI)

The UI is two modes sharing one design system:

1. **Interactive `ryft`** — a full-screen TUI app shell (PTK + Rich) with a
   header, a focusable multi-panel body (dashboard, git, activity, services,
   providers, knowledge, timeline), a status bar, and a command palette
   (`Ctrl+P` / `:`). Keyboard-first; mouse optional.
2. **One-shot `ryft <cmd>`** — Rich stdout output, no app shell, safe for
   scripts/CI (never blocks on a prompt).

The design system (`ui/theme`) is the single source of truth for color,
spacing, typography, borders, and components. Every screen uses it.

> **Framework decision:** we evaluated Textual and chose to stay on
> prompt_toolkit + Rich. Rationale: instant startup, tiny dependency surface,
> full reuse of the existing PTK `Application`/pager investment, and a
> synchronous event loop that matches the rest of the codebase. Textual's
> asyncio model and heavier runtime were not worth orphaning the existing UI.
> Textual remains a documented future option if the dashboard grows complex
> enough to justify it.

---

## 9. Command hierarchy

Commands are natural verbs, not git commands. The full set (36 commands) is in
`docs/COMMAND_REFERENCE.md`; a representative slice:

```text
ryft                         → interactive TUI dashboard
ryft dashboard               → print the live dashboard (one-shot)
ryft ask "<q>"               → conversational AI about the project (chat role)
ryft search "<term>"         → look up the project's indexed symbols
ryft explain <symbol>        → explain a symbol using knowledge + AI
ryft commit [file ...]       → commit with an AI-written conventional message
ryft review [file]           → AI code review of a changed file
ryft analyze                 → AI summary of everything that changed
ryft diff [file]             → GitHub-style diff (all files, or one in detail)
ryft graph [n]               → commit graph
ryft timeline [n]            → recent commits as a timeline
ryft watch                   → auto-commit on save
ryft sync start|stop|status  → background file-watch sync
ryft doctor [fix]            → health check + auto-repair
ryft release [n]             → release notes from recent commits (AI)
ryft memory                  → what Ryft has learned about the project
ryft providers               → configured providers, roles, and health
ryft github                  → GitHub status / open PRs (needs GITHUB_TOKEN)
ryft config [init]           → show or (re)write the project config
ryft help [command]          → full command index or one command's details
```

The registry (`commands/__init__.py`) is decorator-based:

```python
from . import register

@register("doctor", description="Health check + auto-repair ('/doctor fix')",
          usage=["/doctor", "/doctor fix"])
def cmd_doctor(ctx, args):
    ...
```

(There is no `group` kwarg — grouping is by module, decided by which submodule
registers each handler.)

---

## 10. Performance budget

| Concern | Target | Mechanism |
| --- | --- | --- |
| Cold `import ryft` | < 30 ms | lazy imports; no network at import |
| `ryft doctor` (offline) | < 200 ms | no AI calls unless asked |
| Dashboard paint | < 16 ms | event-driven, cached git state |
| AI commit message | < 2 s (local) | small model, compact semantic summary, diff-hash cache |
| Repo index (10k files) | < 5 s, incremental | SQLite + debounced re-index |
| Idle memory | < 80 MB | workers sleep; no retained render trees |

---

## 11. What changed vs v1

| v1 | v2 |
| --- | --- |
| Ollama client only | `providers/` — Ollama, OpenAI-compatible, Anthropic, Google behind one interface |
| Hardcoded commands | Registry (36 commands) + plugin-provided commands |
| No knowledge | `knowledge/` SQLite store + symbol index + search |
| One-off watchdog sync | `services/` managed workers + event bus, plus `SyncController` |
| Splash + toolbar | Full-screen TUI app shell (`RyftTUI`) + command palette |
| Two render paths, no system | `ui/theme` design system; `_legacy_ui` frozen + re-exported |
| No tests | `tests/` pytest suite (config / providers / git / knowledge / render / commands) |
| Stray `tests/` theme files | removed; 26 real tests added |
