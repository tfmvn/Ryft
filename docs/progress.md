# Ryft 2.0 — Redesign Progress & Resume Brief

> **Purpose:** Single source of truth for where the Ryft 2.0 redesign stands.
> When you reopen this project, read this file first, then re-read the specific
> files it points to. It records what was done, what broke, what remains, and the
> exact next action.

---

## 0. The Mission (unchanged)

Redesign Ryft from the ground up into "the AI-native command center for software
projects" — not a Git client, not an AI wrapper, not a commit-message generator.
v1 (Ollama-only Git companion, v1.0.1) was complete; v2 scaffolding was started
but **orphaned** (never imported by the entry point). The job is to **finish v2**
so `python -m ryft` launches the new TUI and `ryft <cmd>` runs one-shot commands,
wired onto the strong v2 layers (providers / knowledge / services / config /
theme) with the duplicate code deleted.

**User's final instruction:** "finish ryft 2.0 … do everything on own ui … all i
need v2 at the end." i.e. build the new TUI (`ryft/ui/tui`) as the real app, unify
the architecture, deliver a working v2.

---

## 1. Architecture Decision (locked — do not revisit)

- **One config:** `ryft/core/config/schema.Config` is canonical. The v2 loader
  (`ryft/core/config/loader.py`) is the only loader. A back-compat `cfg.ollama`
  view is *derived* from provider roles so legacy `cfg.ollama.*` reads keep working.
- **One context:** `ryft/core/context.py::AppContext` is canonical. `ryft/models.py`
  is now a thin re-export hub; the v1 `Config`/`AppContext` dataclasses were deleted.
- **One git layer:** `ryft/git.py` (was v1 `git.py`, now also has `recent_commits`/
  `tags`). `ryft/commons/` was **deleted**; its fs helpers live in `ryft/fs.py`.
- **One AI path:** `ryft/ai.py` keeps the local `OllamaClient` for back-compat AND
  adds provider-registry helpers (`ask`, `embed_texts`, `generate_commit_message_ctx`)
  that work with any provider + any event loop (TUI-safe).
- **Providers/knowledge/services/plugins** are the strong v2 layers and are now
  wired by `core.lifecycle.build_context`.
- **UI:** `ryft/ui/tui` is the new default interactive shell ("own ui"). The legacy
  `_legacy_ui` renderer stays as a frozen toolkit (diff/pager/Live views) and is
  re-exported through `ryft/ui/__init__.py` so old commands keep working.
- **Design system:** `ryft/ui/theme/{tokens,palette}.py` + `ryft/ui/components.py`
  - new `ryft/ui/render.py` (on-theme Rich renderables). No Nerd Font; instant
  startup; Rich + prompt_toolkit only.

---

## 2. WHAT HAS BEEN DONE (this session)

### Phase 0 — Consolidation (COMPLETE)

1. **`ryft/providers/ollama.py`** — fixed `capabilities()` to return
   `{CAP_CHAT, CAP_STREAM, CAP_EMBED}` (was missing `CAP_CHAT`, a real bug).
2. **`ryft/git.py`** — merged `recent_commits(root, n=20)` and `tags(root)` from
   the duplicate `commons/git.py`.
3. **`ryft/fs.py`** (NEW) — filesystem helpers copied from `commons/fs.py`
   (`discover_files`, `is_binary_file`, `human_path`, `truncate`, `_is_ignored`).
4. Repointed all 5 `commons` importers to `ryft.git` / `ryft.fs`:
   `ryft/knowledge/indexer.py`, `ryft/services/git_monitor.py`,
   `ryft/ui/tui/dashboard.py`, `ryft/ui/tui/app.py`.
5. **Deleted `ryft/commons/`** and deleted stale `ryft.egg-info/`.
6. **`ryft/core/config/schema.py`** — added `OllamaConfig` dataclass (host/timeout/
   commit_workers/commit_model/analysis_model/review_model/model) and an `ollama`
   field on `Config`.
7. **`ryft/core/config/loader.py`** — imports `OllamaConfig`; `_from_src_py` populates
   `cfg.ollama`; added `_derive_ollama(cfg)` + `_strip_provider()` and call it in
   `load_config` so TOML configs also get `cfg.ollama`.
8. **`ryft/models.py`** — REWRITTEN as a re-export hub:
   `from .core.config.schema import (Config, OllamaConfig, ...)`,
   `from .core.context import AppContext`,
   `from .core.models import (ActivityEvent, ActivityFeed, CommandSpec, SyncStatus)`.
   → `from .models import Config/AppContext/...` still resolves everywhere.
9. **`ryft/core/context.py`** — `AppContext` kept canonical; added optional
   `ai`, `sync`, `sync_status` (SyncStatus), `console` fields for legacy compat.
10. **`ryft/ai.py`** — kept `OllamaClient`/`build_commit_summary`/`generate_commit_message`
    etc.; ADDED: `import asyncio, threading`; `from .providers.base import Message,
    ProviderError`; `_run_block(coro)` (event-loop-safe runner); `ask(ctx, prompt,
    *, role="chat", system=None, **opts)`, `embed_texts(ctx, texts, *, role="embed")`,
    `generate_commit_message_ctx(ctx, file, diff, *, auto_threshold=10)` returning
    `(message, source)` with cache→auto→provider→fallback hierarchy.
11. **`ryft/config.py`** — REWRITTEN as facade over `ryft.core.config.loader`
    (`load_config`, `find_root`, `validate_config`, `init_config` re-exported);
    kept `is_ignored`; `set_model(cfg, model)` now updates both `cfg.ollama.commit_model`
    and `cfg.providers.roles.commit` and patches `ryft.toml` or `.src.py`.
12. **`ryft/core/lifecycle.py`** — `build_context(root=None, *, start_services=False)`
    now wires: `ctx.knowledge = KnowledgeStore(root/.ryft/knowledge.db)`,
    `ctx.plugins = PluginManager(ctx); ctx.plugins.load_all()`,
    `ctx.services = ServiceManager(ctx)`; starts services only if `start_services`.
13. **`ryft/plugins/manager.py`** — FIXED the registration gap in `_load_one`:
    drained `api._commands` are now registered into `ryft.commands.REGISTRY`,
    `api._providers` registered into `ctx.providers` (with role config if present),
    `api._services` built and registered into `ctx.services`. (Previously plugins
    loaded but did nothing.)
14. **`ryft/__main__.py`** — REWRITTEN: `--help`/`--version` short-circuit;
    `build_context(start_services=not argv)`; one-shot → `commands.dispatch_argv`;
    bare → `_run_tui` → `from .ui.tui import RyftTUI; RyftTUI(ctx).run()` then
    `shutdown(ctx)`.
15. **`ryft/ui/render.py`** (NEW) — on-theme Rich renderables: `build_diff(file,
    diff_text, width)`, `build_ai_output(text, title)`, `build_text(title, text)`,
    `build_code(title, code, lexer)`, `build_git_changes(changes)`,
    `build_doctor(checks)`. Colors from `ui.theme.palette.C`.
16. **`ryft/ui/__init__.py`** — re-exports the v2 modules (`components, render,
   theme`) **AND** the legacy renderer toolkit (`_legacy_ui`: `info, success, warn,
   error, confirm, render_*`, `LiveCommitView`, `RyftApp`, `console`, …) so existing
   `from .. import ui` callers keep working. **This closes the old BLOCKER A.**
17. **Smoke tests (this session):** `import ryft, ryft.ui, ryft.core.lifecycle,
   ryft.commands, ryft.providers, ryft.knowledge, ryft.services, ryft.plugins`
   → "imports ok"; `python -m ryft --version` → `ryft 1.0.1` (version NOT yet
   bumped); `python -m ryft doctor` → runs one-shot clean (11 ✓), which also
   exercises the full command-registry import without error.

### NOT YET DONE (still pending)

- The TUI `app.py` needs **two small targeted fixes** (palette ↑/↓ navigation,
  and wiring the palette `TextArea` to update `self.query` on typing) — it is
  NOT a full rewrite; see BLOCKER B.
- New v2 commands (Phase 3).
- Docs rewrite + real pytest suite + packaging (Phase 4).
- (`ryft/ui/__init__.py` re-export is DONE — that blocker is closed.)

---

## 3. CRITICAL BLOCKERS / KNOWN BROKEN STATES (read before resuming)

### BLOCKER A — `ryft/ui/__init__.py` re-export of `_legacy_ui`  ✅ RESOLVED (this session)

The re-export is applied. `ryft/ui/__init__.py` now does
`from .._legacy_ui import (info, success, warn, error, confirm, render_*, LiveCommitView,
RyftApp, console, …)` alongside `from . import components, render, theme`. Verified:
`python -m ryft doctor` runs one-shot (11 ✓) and exercises the full command-registry
import without error, so `ui.info` / `ui.render_*` / `ui.LiveCommitView` all resolve.
`_legacy_ui/__init__.py` already had a clean re-export list; the imported names match
exactly. It imports `ryft.commands` **lazily**, so there is no import cycle. **No
further action needed.**

### BLOCKER B — TUI fixes (two patches + 3 extra bug fixes)  ✅ RESOLVED this session

The assumption that `ui/tui/{app,dashboard,palette}.py` are immature stubs is
**wrong** — they were already substantially built (verified against source this
session):

- `app.py` — `RyftTUI` with modes `dashboard | palette | help | result`; `:`/`Ctrl-P`
  → palette, `r` refresh, `?` help, `esc` back, `q` quit (dashboard); full-screen PTK
  `Application`; re-renders on `git.state.changed` via `events.subscribe`; renders
  through `to_fragments`. Imports cleanly. Uses verified APIs.
- `dashboard.py` — `build_dashboard(ctx, commands)` renders title + KPI strip +
  git/providers/activity/commands panels using the VERIFIED APIs
  (`gitsys.changed_files`→`[FileChange(path,status)]`, `gitsys.current_branch(root)`,
  `gitsys.recent_commits(root,n)`, `ctx.providers.health()`→`dict[name,
  ProviderHealth(available,detail)]`, `ctx.knowledge.symbol_count()`,
  `ctx.activity.recent(n)`→`[ActivityEvent(time_str,message,level)]`,
  `ctx.services.state()`→`dict[name,bool]`). **No changes needed.**
- `palette.py` — `filter_commands` + `build_palette(commands, query, selected)` are
  correct; the `selected` highlight renders, the app just never moves `selected`.

**All gaps fixed this session (`app.py`):** palette ↑/↓ nav bound on the input's
own key bindings (prepended so `BufferControl`'s default up/down/escape don't
swallow them), typing wired via `buffer.on_text_changed` → `self.query`, and
`escape` added to exit the palette. Nav handlers are real methods
(`_nav_up` / `_nav_down` / `_palette_esc`). Verified: constructing `RyftTUI`,
simulated type→filter, down/down/up nav, escape, and `to_fragments` on the real
dashboard + palette renderables all work.

**Three extra bugs surfaced and fixed while wiring the TUI:**
1. `ryft/ui/tui/render.py::to_fragments` used `split_format_codes`, **removed in
   prompt_toolkit 3.x** — now uses `to_formatted_text(ANSI(ansi))` (tested on
   PTK 3.0.52). Also `@kb.add(..., filter=lambda: ...)` rejects bare lambdas in
   3.x → all filters now wrap with `Condition(...)`.
2. `ryft/config.py::is_ignored` crashed on `cfg.ignore` (now an `IgnoreConfig`,
   not a list) — now accepts `IgnoreConfig | list | None`. Fixed `pipeline.scan`
   and `sync.py` which pass `cfg.ignore`.
3. `cmd_status` called the orphaned legacy `render_dashboard(ctx)` which did
   `ctx.ai.is_available()` (`ctx.ai` is now None) — repointed to the v2
   `build_dashboard`, printed via Rich.

The TUI **constructs a valid prompt_toolkit `Application`** (verified headless);
the only thing not exercised is a live interactive run (no TTY in this env). It
should be functionally complete.

### BLOCKER C — `ctx.sync` / `ctx.ai` are now optional (None)

The `sync` command (`ryft/sync.py`, `/watch` `/sync`) uses `ctx.sync` (a
`SyncController`). `build_context` does not create it. Either:

- create `ctx.sync = SyncController(ctx)` in lifecycle (needs `ryft/sync.py` +
  `ryft/pipeline.py` to work with v2 ctx — they mostly do), or
- adapt the sync command to use the service manager.
Verify `ryft/sync.py` + `ryft/pipeline.py` still import/run after the re-export.

### BLOCKER D — `ryft/onboarding.py` may reference legacy UI

`onboarding.py` uses `config` + `ui`; confirm it still works post re-export. It is
not on the critical path for `ryft`/`ryft <cmd>` (only `ryft init` triggers it);
low priority.

---

## 4. KEY API SHAPES (for writing commands/services without re-reading everything)

### AppContext (`ryft/core/context.py`)

`root: Path, config: Config, events: EventBus, providers: ProviderRegistry,
activity: ActivityFeed, knowledge: KnowledgeStore|None, services: ServiceManager|None,
plugins: PluginManager|None, ui: Any|None, ai/sync/console: Any|None,
sync_status: SyncStatus, running: bool`.
Method: `provider_for(role) -> (provider, model)` or `(None, "")`.

### Config (`ryft/core/config/schema.py`)

`Config` has: `project, git, formatter, sync, ignore(IgnoreConfig), providers
(ProvidersConfig), ollama(OllamaConfig, back-compat), github, services, theme,
root, path, version, source`.
`ProvidersConfig`: `roles(ProviderRoleConfig: commit/analyze/review/chat/embed/agent
= "provider:model"), ollama, openai, anthropic, google`.
`OllamaConfig`: `enabled, host, timeout, commit_workers, model, commit_model,
analysis_model, review_model`.

### ProviderRegistry (`ryft/providers/registry.py`)

`list()`, `resolve(role) -> Resolved(provider, model) | None`,
`can(role, capability)`, `supports_stream(role)`, `supports_embed()`,
`health() -> dict[name, ProviderHealth]`, `register(provider)`,
`configure_roles({role: "provider:model"})`.
Roles/caps constants in `ryft/providers/base.py`: `ROLE_COMMIT/ANALYZE/REVIEW/CHAT/
EMBED/AGENT`, `CAP_CHAT/STREAM/EMBED/REASONING/TOOLS`. `build_registry(...)` is in
`ryft/providers/factory.py`. `ai.ask(ctx, prompt, role=, system=)` is the sync call.

### KnowledgeStore (`ryft/knowledge/store.py`)

`.symbol_count()`, `.all_symbols() -> [Symbol]`, `.search_symbols(term, limit=20)
-> [Symbol]`, `.recent_commits(n=50)`, `.similar(vector, k=10, model=None)
-> [(ref, kind, score)]`, `.close()`. DB at `.ryft/knowledge.db`.
`Indexer(ctx)` (`ryft/knowledge/indexer.py`): `.index(full=False) -> int`,
`.embed_all(batch=32) -> int`, `.close()`. NOTE: `Indexer` opens its OWN store
connection; for one-shot commands prefer `ctx.knowledge` directly.

### ServiceManager (`ryft/services/manager.py`)

`.start_all()`, `.stop_all()`, `.state() -> dict[name, bool]`, `.get(name)`,
`.register(svc)`, `.cache` (AICache), `.services` dict. Built-in services:
`GitMonitor` (name `"git_monitor"`, interval 3.0s) and `IndexerService`
(name `"indexer"`, interval 30s), constructed in `_wire` per `cfg.services` flags.

### Events (`ryft/core/events.py`)

`EventBus.subscribe(type, handler)`, `.emit(Event)`, `.clear()`. Typed constructors:
`git_state_changed(**kw)`, `index_progress`, `index_ready`, `ai_cache_hit`,
`provider_health_changed`, `activity_logged`, `plugin_loaded`, `service_state_changed`.
Wildcard `"*"` subscription supported.

### Command registry (`ryft/commands/__init__.py`)

`REGISTRY: dict[name, CommandSpec]`; `@register("name", description=, usage=,
examples=, aliases=)` decorator; `CommandSpec(name, handler, description, group=,
usage=, examples=, aliases=)` (from `ryft/core/models.py`); `dispatch(ctx, raw)`,
`dispatch_argv(ctx, argv)`. Side-effect imports: `commit, sync, doctor, config,
format, ai, help`. Handler signature: `fn(ctx, args: list[str]) -> None`.
Commands call `from .. import ui` then `ui.info/error/...` and `ui.render_*`.

### Design system

- `ryft/ui/theme/tokens.py`: `THEME` (Palette), `SPACE`, `UNIT=4`, `RADIUS=4`.
- `ryft/ui/theme/palette.py`: `ptk_style()`, `rich(name)`, `C` dict of hex aliases.
- `ryft/ui/components.py`: `panel, kpi, stat_bar, bar, pill, badge, table,
  empty_state, header_line`.
- `ryft/ui/render.py` (NEW): `build_diff, build_ai_output, build_text, build_code,
  build_git_changes, build_doctor`.
- `ryft/ui/tui/render.py`: `to_fragments(renderable, width)` — keeps Rich→ANSI→PTK
  fragments bridge. **Keep as-is.**
- Legacy renderer (`ryft/_legacy_ui/render.py`): `render_diff_summary`,
  `render_file_diff` (full-screen pager), `LiveCommitView`, `LivePushView`,
  `render_ai_output`, `render_doctor`, `render_models`, etc.

---

## 5. REMAINING WORK (execution order)

### Next (resume here)

1. ~~Apply BLOCKER A~~ ✅ DONE this session — `ryft/ui/__init__.py` re-exports
   `_legacy_ui`; verified `python -m ryft doctor` runs one-shot (11 ✓).
2. (Optional) Bump `__version__` in `ryft/__init__.py` (line 7) from `"1.0.1"` to
   `"2.0.0"` once the TUI patch lands; `python -m ryft --version` currently prints
   `1.0.1`.
3. **Patch `ryft/ui/tui/app.py`** with the two BLOCKER B fixes (↑/↓ nav + query
   wiring). This is the single biggest remaining item for a working TUI.

### Phase 2 — Finish the TUI (the "own ui") — mostly DONE, two patches

4. `ryft/ui/tui/dashboard.py` — **DONE**, do not touch. `build_dashboard(ctx, commands)`
   already renders title + KPI strip + git/providers/activity/commands panels using
   the verified APIs (BLOCKER B).
2. `ryft/ui/tui/palette.py` — **DONE**, do not touch. `filter_commands` +
   `build_palette(commands, query, selected)` are correct.
3. `ryft/ui/tui/app.py` — **TARGETED PATCH only** (do NOT rewrite): apply the two
   fixes from BLOCKER B — (a) `up`/`down` key bindings that move + clamp
   `self.selected`; (b) wire `self.input.buffer.on_text_changed` to update
   `self.query`, reset `self.selected = 0`, and `_refresh()`. Modes, layout,
   `to_fragments` rendering, `git.state.changed` re-render, and `:`/Ctrl-P palette
   entry are already implemented and correct. After the patch the TUI should be
   functionally complete (still needs a human live run to confirm).

### Phase 3 — Commands (new + port)

7. New v2 commands (each `@register` in its own `ryft/commands/*.py`, imported by
   `commands/__init__.py`):
   - `ask` — `ai.ask(ctx, query, role="chat")` → `ui.render.build_text`.
   - `search` — `ctx.knowledge.search_symbols(q)`; if `ctx.providers.supports_embed()`
     also `ctx.knowledge.similar(ai.embed_texts(ctx,[...]),k)`.
   - `explain <symbol>` — `ctx.knowledge.search_symbols` → `ai.ask(role="analyze")`.
   - `review [files]` — for each changed file: `git.diff_for` → `ai.ask(role="review")`
     → `ui.render.build_ai_output`.
   - `commit [--push]` — `ai.generate_commit_message_ctx` + `git.commit_file`
     (+ optional `git.push`); mirror v1 `commands/commit.py` logic.
   - `graph` — `git log --graph --oneline --decorate` rendered as text.
   - `timeline` — `ctx.knowledge.recent_commits` / `git.recent_commits` → table.
   - `doctor` — port `ryft/doctor.py` to v2 ctx; `ui.render.build_doctor`.
   - `memory` — knowledge stats (symbol count, files, commits, embeddings).
   - `sessions` — `ctx.activity.all()` + plugin/provider/service state.
   - `release` — recent commits → `ai.ask(role="chat")` release notes.
   - `providers` — list configured providers + role assignments + `.health()`.
   - `plugins` — `ctx.plugins.plugins` (loaded `PluginMeta`s).
   - `github` — read `cfg.github.token_env`; if token, REST list PRs/issues; else
     explain. (Honest about missing creds.)
   - `cloud` — list provider/agent plugins; stub explanation.
   - `dashboard` — print `build_dashboard` (one-shot) or relaunch TUI.
   - `config` — port `ryft/commands/config.py`; show effective config.
   - `help` — list registry; `help <cmd>` → spec.usage/examples.
2. Verify v1 commands still work post re-export: `commit, sync, doctor, config,
   format, ai, help` (see BLOCKER C for sync).

### Phase 4 — Docs / Tests / Packaging

9. Rewrite `docs/ARCHITECTURE.md`, `COMMAND_REFERENCE.md`, `PROVIDER_API.md`,
   `PLUGIN_API.md`, `CONFIG_REFERENCE.md`, `DESIGN_SYSTEM.md` to MATCH the shipped
   tree (currently aspirational — they describe unbuilt features). Add
   `docs/MODULE_MAP.md`, `DEVELOPMENT.md`, `CONTRIBUTING.md`, `ROADMAP.md`.
2. Add a REAL pytest suite under `tests/` (delete stray `LS_COLORS` + `theme.yml`):
    `test_git.py` (helpers against the real repo), `test_config.py` (loader + env
    overlay, `_derive_ollama`), `test_providers.py` (registry role mapping, CAP_CHAT
    fix), `test_knowledge.py` (upsert/search round-trip), `test_render.py` (Rich→
    PTK fragment bridge). `test_formatter.py` is still TODO.
3. Refresh `pyproject.toml` (version 2.0.0; ensure `ryft = ryft.__main__:main`;
    dependencies prompt-toolkit/rich/watchdog/tomli-or-3.11; add pytest dev dep).
4. `python -m pytest` green; `python -m ryft --version` → 2.0.0; `python -m ryft
    doctor` clean; `python -m ryft` launches TUI.

---

## 6. FILE STATUS TABLE

| File | Status | Notes |
|---|---|---|
| `ryft/__main__.py` | ✅ rewritten | lifecycle + TUI default |
| `ryft/core/context.py` | ✅ extended | canonical AppContext + legacy fields |
| `ryft/core/models.py` | ✅ canonical | ActivityEvent/SyncStatus/CommandSpec/ActivityFeed |
| `ryft/core/lifecycle.py` | ✅ extended | wires knowledge/plugins/services |
| `ryft/core/config/schema.py` | ✅ extended | +OllamaConfig, +Config.ollama |
| `ryft/core/config/loader.py` | ✅ extended | +_derive_ollama |
| `ryft/models.py` | ✅ re-export hub | deletes v1 dup Config/AppContext |
| `ryft/git.py` | ✅ merged | +recent_commits/tags |
| `ryft/fs.py` | ✅ new | from commons/fs |
| `ryft/commons/` | ❌ DELETED | merged into git+fs |
| `ryft/ai.py` | ✅ extended | +ask/embed_texts/generate_commit_message_ctx |
| `ryft/config.py` | ✅ fixed | facade over loader; `is_ignored` accepts `IgnoreConfig` |
| `ryft/plugins/manager.py` | ✅ fixed | registers into live registries |
| `ryft/ui/render.py` | ✅ new | on-theme Rich renderables |
| `ryft/ui/__init__.py` | ✅ done | re-exports v2 + legacy `_legacy_ui` |
| `ryft/ui/tui/app.py` | ✅ done | BLOCKER B fixes (↑/↓ nav, query wiring, escape) |
| `ryft/ui/tui/dashboard.py` | ✅ done | complete; do not touch |
| `ryft/ui/tui/palette.py` | ✅ done | complete; do not touch |
| `ryft/ui/tui/render.py` | ✅ fixed | `to_fragments` uses `to_formatted_text(ANSI)` (PTK 3.x) |
| `ryft/providers/*` | ✅ strong | CAP_CHAT fixed; best layer |
| `ryft/knowledge/*` | ✅ strong | real + complete |
| `ryft/services/*` | ✅ strong | wired but idle until started |
| `ryft/commands/commit.py` | ✅ fixed | `status` repointed to v2 `build_dashboard` |
| `ryft/commands/insight.py` | ✅ NEW | ask, search, explain, release, memory |
| `ryft/commands/system.py` | ✅ NEW | providers, plugins, github, cloud, dashboard, graph, timeline, sessions |
| `ryft/commands/*` (v1) | ✅ verified | all import + run one-shot post re-export |
| `ryft/sync.py`,`pipeline.py` | ✅ verified | `is_ignored(IgnoreConfig)` fixed; `scan()` runs |
| `ryft/doctor.py` | ✅ verified | runs one-shot (11 ✓) |
| `ryft/onboarding.py` | ✅ verified | BLOCKER D (imports + find_root resolve) |
| `ryft/_legacy_ui/*` | ✅ frozen | renderer toolkit; re-exported via ui |
| `ryft/__init__.py` | ✅ done | `__version__` → 2.0.0 |
| `docs/*` | ❌ stale | rewrite Phase 4 |
| `tests/*` | ❌ stray | add real suite Phase 4 |
| `pyproject.toml` | ✅ done | `version = { attr = "ryft.__version__" }` — dynamic, reads 2.0.0 |
| `ryft.egg-info/` | ❌ DELETED | rebuild on install |

---

## 7. QUICK RESUME COMMANDS (run after reopening)

```bash
cd /mnt/data/Projects/AI/Ryft
python -m ryft --version          # expect 2.0.0 after version bump
python -m ryft doctor             # one-shot smoke test (post BLOCKER A)
python -c "import ryft, ryft.core, ryft.providers, ryft.knowledge, ryft.services, ryft.plugins; print('imports ok')"
```

**Golden rule for the next session:** do NOT start greenfield, and do NOT rewrite
the TUI files (they're ~85% done). The remaining work is: (1) patch `app.py` with
the two BLOCKER B fixes (the `_legacy_ui` re-export is already done), (2) add the
new v2 commands (Phase 3), (3) docs + tests + version bump (Phase 4). Re-read a file
immediately before editing it (Edit requires a Read in-session).

---

## 8. SESSION 2 LOG — finished this session

All of the prior "pending" one-shot/command work is now DONE. TUI is functionally
complete (verified headless; only a live interactive TTY run is unexercised). Version
bumped to 2.0.0. 14 new v2 commands added and verified.

### 8.1 BLOCKER B — TUI navigation  ✅ RESOLVED

`ryft/ui/tui/app.py`:
- Imports `Condition` + `merge_key_bindings`.
- After `self.input.text = ""`: subscribe `on_text_changed` → `_on_query_changed`
  (sets `self.query`, resets `selected`, `_refresh()`).
- Build `_palette_kb` (up/down/escape, filtered on `mode == "palette"`) and merge
  onto `self.input.control.key_bindings`. Handlers: `_nav_up`, `_nav_down`
  (bounded against `palette_ui.filter_commands(...)` length), `_palette_esc`
  (mode → dashboard, clears result, `_swap_layout`).
- Fixed existing `enter` palette binding to use `Condition(...)` (PTK 3.x rejects
  bare callables in `filter=`).

### 8.2 Three extra bug fixes (verified)

1. **`ryft/ui/tui/render.py`** — `to_fragments` now `FormattedText(to_formatted_text(ANSI(ansi)))`.
   `split_format_codes` was removed in PTK 3.0.52 and `ANSI` is no longer a
   `FormattedText` subclass. (Was raising `cannot import name 'split_format_codes'`
   and `'ANSI' object has no attribute 'formatted_text'`.)
2. **`ryft/config.py`** — `is_ignored(path, root, extra_patterns=())` now unwraps
   `IgnoreConfig` via `extra_patterns.patterns`. (Was raising `'IgnoreConfig' object
   is not iterable` from `pipeline.scan`.)
3. **`ryft/commands/commit.py`** — `cmd_status` no longer calls the legacy
   `render_dashboard` (which died on `ctx.ai.is_available()` since `ctx.ai` is None
   in v2). It now prints `build_dashboard(ctx, list(REGISTRY.values()))` via Rich.

### 8.3 New v2 command modules (verified one-shot)

- `ryft/commands/insight.py` — `ask`, `search`, `explain`, `release`, `memory`.
- `ryft/commands/system.py` — `providers`, `plugins`, `github`, `cloud`, `dashboard`,
  `graph`, `timeline`, `sessions`. (`github` parses owner/repo from remote and fetches
  open PRs via `urllib` when `GITHUB_TOKEN` is present.)
- `ryft/commands/__init__.py` now imports both new modules.
- `ryft/git.py` gained `graph(root, n)` (ASCII `--graph --oneline --decorate`).
- `ryft/__init__.py` → `__version__ = "2.0.0"`. `pyproject.toml` already reads it via
  `version = { attr = "ryft.__version__" }` (dynamic), so no string edit needed.

### 8.4 Verification (all green)

```text
python -m ryft --version            → ryft 2.0.0
python -m ryft doctor               → 11 ✓
status / dashboard                  → v2 design system renders
graph 8, timeline 5, providers, plugins, memory (605 symbols / 31 commits),
github (parsed tfmvn/Ryft, fetched PRs), cloud
ask "Reply with exactly: OK"        → OK
explain configure_logging           → full explanation (slow 7B model, not a hang)
registry                            → 35 commands; all 13 planned new names present
Application(bare run)               → constructs OK headless (no TTY run)
```

Known non-bug: `search "RyftTUI"` / `explain RyftApp` say "no matching symbols"
because the knowledge DB (605 symbols / 75 files) is **stale** — it predates
`ryft/ui/tui/*`. Re-index to pick up the new tree (Phase 4 / re-run indexer).

### 8.5 Still open (do NOT treat as broken)

- **Phase 4** — stale `docs/*.md` (rewrite to match shipped tree), real `tests/` suite
  (delete stray `LS_COLORS` + `theme.yml`), optional `.ryft/knowledge.db` re-index.
- Live interactive TUI run (arrows/escape) — cannot be done without a TTY in this env.

---

## 9. SESSION 3 LOG — finished this session

Continued from Session 2 (which closed BLOCKER B + 3 bug fixes + 14 commands).

### 9.1 BLOCKER C — `ctx.sync` for /watch, /sync  ✅ RESOLVED

`ryft/core/lifecycle.py::build_context` now constructs `ctx.sync = SyncController(ctx)`
(cheap: no threads/observer until `.start()`). Verified: `ryft sync status` → `stopped`;
`SyncController` lifecycle builds, `is_running` toggles correctly. `start()` correctly
reports `watchdog is not installed` when the optional dep is missing (declared in
`pyproject.toml` — install to enable live watching).

### 9.2 BLOCKER D — onboarding  ✅ VERIFIED

`ryft/onboarding.py` imports cleanly post re-export: `Config` comes from
`ryft.core.config.schema` via the `models.py` hub; `config.find_root/load_config/
init_config/validate_config` come from the `ryft/config.py` facade; `ui.render_*`,
`ui.OnboardingProgress`, `ui.confirm`, `ui.info` come from `_legacy_ui` (re-exported
via `ryft/ui`). `find_root(Path.cwd())` resolves to the repo root.

### 9.3 Knowledge store re-indexed (correctness fix)

The `.ryft/knowledge.db` was stale (605 symbols / pre-`ryft/ui/tui/*`), so `search` /
`explain` couldn't find current code. Ran `Indexer(ctx).index(full=True)` → **102 files,
661 symbols**. Verified `search RyftTUI` → `ryft/ui/tui/app.py:33`, `search build_dashboard`
→ `dashboard.py:19`, `search SyncController` → `sync.py:163`, `search cmd_explain` →
`insight.py:99`. Core v2 AI features now reflect the real tree.

### 9.4 Status

v2 is functionally complete and verified one-shot:

- TUI builds (BLOCKER B fixed); live-TTY run still unexercised (no TTY here).
- 36-command registry, all new names present and runnable.
- BLOCKERs A, B, C, D all closed.
- Knowledge store current (661 symbols, re-indexed this session).
- `py -m ryft --version` → 2.0.0.
- `pyproject.toml` entry point correct: `ryft = "ryft.__main__:main"`.

### 9.5 Real pytest suite added ✅

Deleted the stray `tests/LS_COLORS` + `tests/theme.yml`; added a real, offline,
deterministic suite (`conftest.py` puts repo root on `sys.path`):

- `tests/test_config.py` — `find_root`, `load_config`, `is_ignored` (list /
  `IgnoreConfig` / `None`), `set_model` role update.
- `tests/test_providers.py` — `build_registry`, `health`, `ollama` advertises
  `CAP_CHAT` (the v2 capability fix), `can` / `supports_embed`.
- `tests/test_git.py` — `is_repo`, `recent_commits`, `graph`, `current_branch`.
- `tests/test_knowledge.py` — `upsert_symbols` / `search_symbols` round-trip,
  miss, `remove_file` count.
- `tests/test_render.py` — `build_text` returns `Group`; `to_fragments` ANSI→
  `FormattedText` bridge (the PTK 3.x fix) works with styled + plain text.
- `tests/test_commands.py` — registry contains all 36 commands; read-only
  one-shot dispatch (`graph/timeline/providers/plugins/dashboard/status/memory/
  config/doctor/help`) produces output and raises nothing.

**Result:** `python -m pytest tests/ -q` → **26 passed** (0.28s, no TTY needed).
Run from repo root. The lone warning is pytest_asyncio's get_event_loop_policy
deprecation (its plugin is auto-loaded; our tests are sync).

---

## 10. SESSION 4 LOG — docs sweep (done this session)

The user's instruction: *"update all .md files according to need and check if
anything is left."* All nine repo docs (`README.md` + the eight `docs/*.md`,
excluding this working file) were reviewed against the **shipped tree** and
corrected. No source code was changed.

### 10.1 Inaccuracies fixed

- **Command count**: docs said "40 commands" → actual registry is **36**
  (verified via `len(ryft.commands.REGISTRY)`). Corrected in README,
  ARCHITECTURE, COMMAND_REFERENCE.
- **ARCHITECTURE module map**: rewritten to the real tree — adds `core/`,
  `lang/`, `formatter/`, `pipeline.py`, `sync.py`, `_legacy_ui/`, `ui/theme`,
  `ui/tui` (`RyftTUI` not `TuiApp`); removes non-existent `integrations/`,
  `utils/`, `tui/panels.py`, `together.py`. Dependency rule updated
  (no `integrations`/`utils` dirs).
- **AppContext**: updated to the real dataclass (optional `knowledge`/
  `services`/`plugins`/`sync`, `activity`, `sync_status`); `build_context`
  does **not** run onboarding (driven by `ryft init`).
- **Providers**: `together.py`/adapter classes don't exist — built-ins are
  Ollama, OpenAI-compatible (incl. LM Studio at `:1234/v1`), Anthropic, Google.
- **Plugins**: `PluginMeta` has no `type`/`requires`; lifecycle is
  `register(api)` (no `setup`/`teardown`); `PluginAPI` exposes
  `register_command/register_provider/register_service/register_panel/log`
  (no `add_dashboard_widget`/`register_search`/`register_review`). Discovery is
  entry points + `~/.config/ryft/plugins` + `<project>/.ryft/plugins` +
  `RYFT_PLUGIN_PATH` (no `enable|disable|install` subcommands yet).
- **COMMAND_REFERENCE**: full rewrite to the real 36 commands; removed
  nonexistent `ryft work`, `graph [deps|calls|files]`, `release [draft|cut]`,
  `github`/`cloud` subcommands, and `--no-ai`/`--config` global flags (only
  `--help`/`--version` exist).
- **DEVELOPMENT**: `@register` example dropped the nonexistent `group=` kwarg;
  test description and `StatusCache` reference corrected.
- **CONFIG_REFERENCE**: `RYFT_OLlama_HOST` → `RYFT_OLLAMA_HOST` (actual env
  var); confirmed `config init` writes `ryft.toml` (accurate).
- **Stray `StatusCache`** references (design-principles table, progress Phase-4
  TODO) → `git_monitor` service.
- **ROADMAP**: Phase 0 marked ✅ COMPLETE.

### 10.2 Lint

All docs pass markdownlint (MD022/MD032/MD040/MD060/MD004) after the sweep —
added fence languages, spaced compact table pipes, added blank lines around
headings/lists, fixed one `+` false-positive bullet.

### 10.3 What is genuinely left (not a doc defect)

- **`test_formatter.py`** (validator round-trip) is still TODO — the other five
  suites exist and pass (26 tests).
- **Live interactive TUI run** (arrows/escape) is still unexercised (no TTY in
  this env); the `Application` constructs headless.
- **DESIGN_SYSTEM.md** was read and is already accurate (design spec) — not
  changed.
- CODE is unchanged this session; `36 commands` + `26 passed` re-verified.
