# .src.py

class Project:
    name = "Ryft"


class Ollama:
    enabled = True

    # Fast model for commit messages — keep this small (qwen3:0.6b is ideal).
    commit_model = "qwen3:0.6b"
    # Larger model for /analyze (full project diff review).
    analysis_model = "qwen2.5-coder:7b-instruct-q4_K_M"
    # Larger model for /review (per-file code review).
    review_model = "qwen2.5-coder:7b-instruct-q4_K_M"

    # Ollama API endpoint.
    host = "http://localhost:11434"
    # Seconds to wait for AI response.
    timeout = 60
    # Parallel commit message workers (2 is safe on 16GB RAM).
    commit_workers = 2


class Sync:
    enabled = False
    debounce_seconds = 30
    push = True


class Git:
    branch = "main"
    remote = "origin"
    fallback_commit_message = "chore: update {file}"

    # Skip AI for tiny changes (<= threshold lines changed).
    auto_commit_small_changes = True
    small_change_threshold = 10


class Formatter:
    enabled = True
    max_blank_lines = 2
    remove_comments = True


IGNORE = [
    "*.log",
    ".env",
    "node_modules",
    "coverage",
]
