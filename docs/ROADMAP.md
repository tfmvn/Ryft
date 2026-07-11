# Ryft — Roadmap

A direction, not a contract. Each phase keeps the app runnable; nothing is
merged half-finished.

---

## Phase 0 — Foundation ✅ COMPLETE

- Layered architecture (`core`, `providers`, `knowledge`, `services`,
  `plugins`, `ui`, `commands`).
- Design system (`ui/theme`) used by every screen.
- Provider abstraction with Ollama + OpenAI-compatible + Anthropic + Google.
- Knowledge store (SQLite) + symbol indexer + grep/semantic search.
- Managed background services (git monitor, indexer, AI cache) + `SyncController`.
- Plugin system (entry points + path scan + `PluginAPI` facade).
- Full-screen TUI app shell (`RyftTUI`) + command palette + dashboard.
- 36-command registry (`ask`, `search`, `explain`, `doctor`, `commit`, …).
- Real pytest suite (26 tests); stray `tests/` theme files removed.

## Phase 1 — Intelligence

- Semantic search quality: reranking, hybrid retrieval, per-language chunking.
- `ryft ask` with project-aware retrieval (RAG) and citation of sources.
- `ryft explain` call-graph expansion across languages (tree-sitter).
- Multi-agent workflows (`agent` role): planning → implement → review.
- Conversation + repository memory persisted across sessions.

## Phase 2 — Integrations

- GitHub: issues/PRs/releases full sync, review queues, merge/rebase from TUI.
- GitLab, Bitbucket adapters (provider plugins).
- CI/CD status surfaces (GitHub Actions, CircleCI) on the dashboard.
- `ryft cloud`: optional encrypted sync of knowledge + sessions.

## Phase 3 — Automation

- Declarative `ryft.toml` automations (on-commit hooks, scheduled analysis).
- Background test/coverage monitoring feeding the dashboard.
- Release manager: changelog → version bump → tag → GitHub release.
- Dead-code / large-file / tech-debt detectors wired to the knowledge store.

## Phase 4 — Scale & polish

- Monorepo awareness (per-package indexing, focus).
- Plugin marketplace + signature verification.
- Theming: user-overridable palette via `ryft.toml [theme]`.
- Accessibility pass: screen-reader friendly output mode, high-contrast theme.
- Re-evaluate Textual if the dashboard outgrows the PTK shell.

---

## Non-goals

- A web UI (terminal-first, always).
- Replacing git (Ryft drives git; it is not a reimplementation).
- Lock-in: every provider/integration is swappable.
