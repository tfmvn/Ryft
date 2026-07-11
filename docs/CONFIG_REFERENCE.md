# Ryft — Configuration Reference

Ryft reads configuration from, in order of precedence (highest last):

1. Environment variables (`RYFT_*`).
2. A project config file.
3. Built-in defaults.

## Config file discovery

Ryft searches upward from the current directory for, in order:

1. `ryft.toml` — the v2 native format (preferred).
2. `pyproject.toml` with a `[tool.ryft]` table.
3. `.src.py` — the v1 format, **still supported** for backward compatibility.

The first file found defines the project root. This means existing v1 projects
keep working unchanged; you can migrate to `ryft.toml` at leisure with
`ryft config init`.

---

## `ryft.toml` schema

```toml
[project]
name = "my-app"

[git]
branch = "main"
remote = "origin"
fallback_commit_message = "chore: update {file}"
auto_commit_small_changes = true
small_change_threshold = 10

[formatter]
enabled = true
max_blank_lines = 2
remove_comments = true

[sync]
enabled = false
debounce_seconds = 30
push = true

[ignore]
patterns = ["*.log", ".env", "node_modules", "coverage"]

[providers]
# role -> "provider:model"
commit   = "ollama:qwen3:0.6b"
analyze  = "ollama:qwen2.5-coder:7b-instruct-q4_K_M"
review   = "ollama:qwen2.5-coder:7b-instruct-q4_K_M"
chat     = "anthropic:claude-opus-4-8"
embed    = "openai:text-embedding-3-small"

[providers.ollama]
host = "http://localhost:11434"
timeout = 60
commit_workers = 2

[providers.openai]
api_key_env = "OPENAI_API_KEY"
base_url = "https://api.openai.com/v1"

[providers.anthropic]
api_key_env = "ANTHROPIC_API_KEY"

[github]
token_env = "GITHUB_TOKEN"

[services]
indexer = true
git_monitor = true
ai_cache = true
```

---

## `.src.py` (v1, still supported)

```python
class Project:
    name = "my-app"

class Ollama:
    enabled = True
    commit_model = "qwen3:0.6b"
    analysis_model = "qwen2.5-coder:7b-instruct-q4_K_M"
    review_model = "qwen2.5-coder:7b-instruct-q4_K_M"
    host = "http://localhost:11434"
    timeout = 60
    commit_workers = 2

class Sync:
    enabled = False
    debounce_seconds = 30
    push = True

class Git:
    branch = "main"
    remote = "origin"
    fallback_commit_message = "chore: update {file}"
    auto_commit_small_changes = True
    small_change_threshold = 10

class Formatter:
    enabled = True
    max_blank_lines = 2
    remove_comments = True

IGNORE = ["*.log", ".env", "node_modules", "coverage"]
```

The loader maps the v1 `Ollama.*_model` fields onto the v2 `commit`/`analyze`/
`review` roles automatically.

---

## Environment variables

| Variable | Overrides |
| --- | --- |
| `RYFT_PROJECT_NAME` | `project.name` |
| `RYFT_GIT_BRANCH` | `git.branch` |
| `RYFT_OLLAMA_HOST` | `providers.ollama.host` |
| `OPENAI_API_KEY` | OpenAI key (via `api_key_env`) |
| `ANTHROPIC_API_KEY` | Anthropic key |
| `GITHUB_TOKEN` | GitHub token |
| `RYFT_NO_AI` | force offline/template paths |
| `RYFT_DEBUG` | verbose logging to `.ryft/ryft.log` |

---

## Key fields

| Path | Default | Meaning |
| --- | --- | --- |
| `git.small_change_threshold` | `10` | lines-changed below which AI is skipped |
| `formatter.remove_comments` | `true` | strip comments on format |
| `providers.commit` | `ollama:qwen3:0.6b` | model for commit messages |
| `services.indexer` | `true` | run background repo indexer |
| `ignore.patterns` | `[]` | extra ignore globs (joined with built-ins) |

---

## Validation

`ryft doctor` reports config validity. Invalid TOML/Python falls back to
defaults with a warning (never crashes the CLI); `fallback_commit_message`
supports a `{file}` placeholder.
