# Kyte

A calm, fast terminal companion for git — AI commit messages, live sync,
formatting, and health checks, wrapped in a premium terminal UI.

```bash
pip install kyte
kyte
```

That's it. If this is the first time Kyte has been run in this folder, it
will walk you through a 10-second setup and drop you straight into a
ready-to-use session.

## What it does

- **AI commit messages** — a small local model (via [Ollama](https://ollama.com))
  writes conventional commit messages from your diff. Tiny changes skip the
  AI entirely; identical diffs are cached.
- **Live sync** — `kyte watch` watches your project and automatically
  formats, messages, commits, and (optionally) pushes on save.
- **Formatting** — strips comments and collapses blank lines for Python and
  Lua, safely (it verifies the result still parses before writing).
- **AI review & analysis** — `/review` and `/analyze` for a second pair of
  eyes on your changes, using a larger local model.
- **`kyte doctor`** — a full health check (Python, git, remotes, branch,
  Ollama, models, config, permissions, repo state) with plain-English
  explanations and one-command auto-fixes (`kyte doctor fix`).

## Usage

Kyte works two ways:

```bash
kyte              # interactive session — type /help for commands
kyte doctor       # run one command and exit, e.g. from a script or CI
kyte commit
kyte watch
```

Inside the interactive session, everything is a slash command:

```
/status            project status at a glance
/commit             commit all changed files, AI messages generated in parallel
/push  /pull        publish or fetch
/diff  /diff <file>  GitHub-style diff, scrollable
/review <file>       AI code review
/analyze             AI summary of everything that changed
/sync start|stop     background watch mode
/doctor  /doctor fix  health check + auto-repair
/config init          write a .src.py with the defaults
/help                 full command list
```

## Configuration

Kyte is configured with a `.src.py` file at your project root — plain
Python, not YAML/TOML, so it's just as easy to script as it is to read:

```python
class Project:
    name = "my-app"

class Ollama:
    commit_model = "qwen3:0.6b"
    analysis_model = "qwen2.5-coder:7b-instruct-q4_K_M"

class Git:
    branch = "main"
    remote = "origin"
```

If no `.src.py` exists, Kyte offers to create one the first time you run
it — you're never left guessing what to do next.

## Development

```bash
pip install -e .
pytest
```

The codebase is a small set of focused modules:

| module          | responsibility                                   |
|------------------|---------------------------------------------------|
| `config.py`      | `.src.py` discovery, loading, validation          |
| `git.py`         | every git invocation goes through here            |
| `ai.py`          | Ollama client, diff summarizer, commit messages   |
| `formatter.py`   | comment stripping / blank-line collapsing         |
| `doctor.py`      | health checks                                     |
| `recovery.py`    | shared auto-repair helpers (used by doctor + commands) |
| `onboarding.py`  | first-run setup flow                              |
| `sync.py`        | file-watch → format → commit → push pipeline      |
| `commands.py`    | the command registry / dispatcher                 |
| `ui.py`          | the terminal UI (Rich + Prompt Toolkit)           |

## License

MIT
