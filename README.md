# Ryft

**The AI-native command center for software projects.**

Ryft is a calm, fast terminal application that turns your project into a
queryable, AI-assisted workspace — git, AI chat, code search, architecture
explanation, live sync, and a dashboard, all behind one design system and one
command model. It runs two ways: an interactive terminal UI, and one-shot
commands safe for scripts and CI.

```bash
pip install ryft
ryft                 # interactive terminal UI (dashboard + command palette)
```

That's it. If this is the first time Ryft has been run in a folder with no
config, it walks you through a 10-second setup and drops you into a ready
session.

## What it does

- **AI chat about *your* project** — `ryft ask` talks to a configured provider
  (local Ollama by default; OpenAI-compatible, Anthropic, or Google if you
  configure them) using the `chat` role.
- **Code intelligence** — `ryft search` looks up the project's indexed symbols;
  `ryft explain <symbol>` explains a symbol using the knowledge store + AI;
  `ryft graph` shows the commit graph.
- **AI commit messages & reviews** — `ryft commit` writes conventional commit
  messages; `/review` and `/analyze` give a second pair of eyes on your diff.
- **Live sync** — `ryft watch` watches your folder and auto-commits on save;
  `ryft sync start|stop|status` controls the background watcher.
- **Release notes** — `ryft release` drafts notes from recent commits via AI.
- **`ryft doctor`** — a full health check (Python, git, remotes, branch,
  providers, models, config, permissions, repo state) with plain-English
  explanations and one-command auto-fixes (`ryft doctor fix`).
- **Dashboard** — `ryft dashboard` prints a glanceable summary: project, branch,
  git status, recent commits, providers, plugins, and runtime state.

## Usage

```bash
ryft                  # interactive terminal UI (dashboard + command palette)
ryft <command> [...]  # one command, then exit — safe for scripts and CI
ryft --help           # usage summary (no project needed)
ryft --version        # installed version
```

Running a single command (anything after `ryft`) never blocks on a prompt — if
there's no config yet it proceeds on sane defaults instead of asking, so it's
safe to call from scripts and CI. Run `ryft init` first if you want the
interactive setup walkthrough.

Inside the interactive session, everything is a slash command (also reachable
via the command palette with `:`):

```text
/status     project + repository status
/dashboard  print the live dashboard
/ask        conversational AI about this project
/search     look up indexed symbols
/explain    explain a symbol with project knowledge + AI
/commit     commit changed files, AI-written messages
/diff       GitHub-style diff (all files, or one in detail)
/review     AI code review of a changed file
/analyze    AI summary of everything that changed
/graph      commit graph
/timeline   recent commits as a timeline
/watch      auto-commit on save
/sync       background watcher: start | stop | status
/doctor     health check (+ /doctor fix auto-repair)
/config     show or (re)write the project config
/help       full command list (or /help <command>)
```

See `docs/COMMAND_REFERENCE.md` for the full set (36 commands),
`docs/ARCHITECTURE.md` for the design, and `docs/DEVELOPMENT.md` to contribute.

## Configuration

Ryft is configured with a `ryft.toml` (preferred), a `[tool.ryft]` table in
`pyproject.toml`, or a legacy `.src.py` at your project root. Plain Python
(`.src.py`) is *executed*, not parsed, so it stays scriptable.

```python
# .src.py — user-authored, trusted
class Project:
    name = "my-app"

class Ollama:
    commit_model = "qwen3:0.6b"
    analysis_model = "qwen2.5-coder:7b-instruct-q4_K_M"

class Git:
    branch = "main"
    remote = "origin"
```

Provider roles (`commit`, `analyze`, `review`, `chat`, `embed`, `agent`) map to
`provider:model` strings, so you can run commits on a tiny local model and
analysis on a larger one. Secrets are read from environment variables
(`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GITHUB_TOKEN`, …) and never stored in
config files.

## Development

```bash
pip install -e ".[dev]"
pytest              # fast, offline, no network
ryft                # opens the TUI in the current project
```

The codebase is a small set of focused modules:

| module | responsibility |
| --- | --- |
| `ryft/__main__.py` | entry point: `ryft` (TUI) \| `ryft <cmd>` (one-shot) |
| `ryft/core/` | `context`, `events`, `lifecycle`, and the v2 `config/` schema + loader |
| `ryft/providers/` | AI provider abstraction (registry + Ollama / OpenAI-compatible / Anthropic / Google) |
| `ryft/knowledge/` | SQLite knowledge store + symbol indexer + search |
| `ryft/services/` | managed background workers (git monitor, indexer, AI cache) |
| `ryft/plugins/` | plugin spec + manager + safe `PluginAPI` facade |
| `ryft/ui/` | design system (`theme/`), Rich render helpers, and the `tui/` app shell |
| `ryft/commands/` | the command registry + handlers |
| `ryft/ai.py`, `ryft/git.py`, `ryft/fs.py`, `ryft/formatter/`, `ryft/sync.py`, `ryft/pipeline.py` | cross-cutting helpers |

## License

MIT
