# Ryft — Command Reference

Two invocation styles:

```bash
ryft                  # interactive terminal UI (dashboard + command palette)
ryft <command> [...]  # one-shot, non-interactive (scripts/CI safe)
```

Inside the TUI, every command is also reachable through the **command palette**
(`:`) and as a `/slash` command. One-shot commands never block on a prompt.

This lists every registered command (36 total). Names, usage strings, and
descriptions are taken directly from the registry.

---

## AI & knowledge

### `ryft ask <question>`

Ask the configured AI a question (uses the `chat` role). The answer is rendered
through the AI-output view. Example: `ryft ask "why is the build failing?"`

### `ryft search <term>`

Search the project's indexed symbols. Uses semantic search when the `embed`
role is configured and available, otherwise a symbol-name lookup.

### `ryft explain <symbol>`

Explain a symbol using project knowledge + AI: finds the symbol in the
knowledge store, builds context from its signature/doc, and asks the `analyze`
role to explain it.

### `ryft memory`

Show what Ryft has learned about this project: indexed symbol count, recent
commit count, configured providers, and service state.

### `ryft release [n]`

Generate release notes from the last `n` commits (default set by the command)
via the `chat` role.

---

## Git & workflow

### `ryft status`

Show project + repository status (renders the v2 dashboard summary).

### `ryft dashboard`

Print the live dashboard (one-shot): project, branch, git status, recent
commits, providers, plugins, and runtime state.

### `ryft commit [file ...]`

Commit changed files with an AI-written conventional message. With no argument
commits all changed files; pass paths to commit a subset.
Usage: `/commit`, `/commit <file> [file ...]`

### `ryft message [file]`

Generate a commit message for one file **without** committing.

### `ryft diff [file]`

Show a diff — a summary for all files, or one file in detail (pager in the TUI).

### `ryft log [n]`

Show recent commit history.

### `ryft graph [n]`

Show the commit graph (`git log --graph --oneline --decorate`).

### `ryft timeline [n]`

Recent commits rendered as a timeline.

### `ryft push [remote] [branch]` / `ryft pull [remote] [branch]`

Push committed changes to / pull the latest changes from the remote.

### `ryft git <sub> [args...]`

Run a git-flavored subcommand: `status`, `diff`, `log`, `push`, `pull`,
`commit`. Example: `/git diff src/app.py`

### `ryft watch`

Watch this folder and auto-commit on save (foreground; Ctrl+C to stop).

### `ryft sync start|stop|status`

Control the background sync watcher.

---

## AI review & formatting

### `ryft analyze`

AI review of the full project diff.

### `ryft review [file]`

AI code review of one changed file.

### `ryft format [target]`

Format files — the whole project, changed files, or one path.
Usage: `/format`, `/format .`, `/format changed`, `/format <path>`

### `ryft model [list|current|<name>]`

List available models, show the current commit model, or set it.

---

## Health & configuration

### `ryft doctor [fix]`

Health check + auto-repair. `ryft doctor fix` runs the auto-repairs.

### `ryft config [init]`

Show the project's configuration, or `ryft config init` to (re)write it.

### `ryft init`

Set up Ryft in this project (runs the onboarding flow).

### `ryft providers`

Show configured AI providers, their role assignments, and health.

### `ryft plugins`

List loaded plugins.

---

## Integrations & runtime

### `ryft github`

GitHub status / open PRs. Needs `GITHUB_TOKEN`; derives owner/repo from the
git remote.

### `ryft cloud`

Show cloud / agent-capable providers (providers advertising `tools`/`reasoning`
or usable for the `agent`/`chat` roles).

### `ryft sessions`

Show the live activity feed and runtime state.

### `ryft activity`

Show the full activity log.

---

## Project navigation

### `ryft root`

Show the resolved project root.

### `ryft files`

List tracked, non-ignored files.

### `ryft tree`

Show a directory tree of tracked, non-ignored files.

---

## Shell

### `ryft help [command]`

Show all commands, or details for one command. Usage: `/help`, `/help <command>`

### `ryft exit`

Exit the Ryft shell (interactive mode only).

---

## Global flags

| Flag | Effect |
| --- | --- |
| `--help`, `-h`, `help` | usage and exit (no project needed) |
| `--version`, `-V` | version and exit |

Environment toggles (see `CONFIG_REFERENCE.md`): `RYFT_NO_AI` forces
offline/template paths; `RYFT_DEBUG` enables verbose logging to
`.ryft/ryft.log`.

One-shot commands never block on a prompt; if required state (e.g. a repo) is
missing they either auto-repair or exit with a clear message and a suggested
fix.
