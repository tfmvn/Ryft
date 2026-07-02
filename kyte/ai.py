"""Local Ollama integration.

Architecture for speed:
- Separate clients per role: commit (small model), analysis, review (large model)
- build_commit_summary() sends <200 chars to Ollama instead of 4000-char raw diffs
- Fast-path: tiny changes (<= threshold) skip AI entirely
- Message cache: .kyte/cache.json avoids redundant AI calls for identical diffs
- Parallel generation via ThreadPoolExecutor (called from commands.py)
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

SUPPORTED_MODELS = [
    "qwen3:0.6b",
    "qwen2.5-coder:7b-instruct-q4_K_M",
    "qwen2.5:7b-instruct",
    "llama3.2:3b",
]

# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_COMMIT_MSG = (
    "You are a git commit message writer. "
    "Generate ONE conventional commit message. "
    "Return ONLY the commit message. "
    "No markdown. No explanation. No reasoning. No quotes. No thinking tags."
)

SYSTEM_REVIEW = (
    "You are a senior software engineer reviewing a code change. "
    "Be concise and concrete. Respond only with the requested structure, no preamble."
)

# ── Error ─────────────────────────────────────────────────────────────────────

class OllamaError(Exception):
    pass


# ── Client ────────────────────────────────────────────────────────────────────

@dataclass
class OllamaClient:
    host: str = "http://localhost:11434"
    model: str = SUPPORTED_MODELS[0]
    timeout: int = 60

    def generate(self, prompt: str, system: str | None = None) -> str:
        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "think": False,          # disable chain-of-thought / reasoning
            "options": {
                "num_predict": 80,   # commit messages are short — cap tokens hard
                "temperature": 0.2,
                "top_p": 0.9,
            },
        }
        if system:
            payload["system"] = system
        raw = self._post("/api/generate", payload)
        return raw.get("response", "").strip()

    def is_available(self) -> bool:
        try:
            self._get("/api/tags")
            return True
        except OllamaError:
            return False

    def list_models(self) -> list[str]:
        try:
            raw = self._get("/api/tags")
            return [m.get("name", "") for m in raw.get("models", [])]
        except OllamaError:
            return []

    def _post(self, path: str, payload: dict) -> dict:
        req = urllib.request.Request(
            f"{self.host}{path}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, TimeoutError) as exc:
            raise OllamaError(str(exc)) from exc
        except json.JSONDecodeError as exc:
            raise OllamaError(f"invalid JSON from Ollama: {exc}") from exc

    def _get(self, path: str) -> dict:
        req = urllib.request.Request(f"{self.host}{path}", method="GET")
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return json.loads(resp.read().decode())
        except (urllib.error.URLError, TimeoutError) as exc:
            raise OllamaError(str(exc)) from exc


def is_ollama_installed() -> bool:
    """True if the `ollama` binary is on PATH — distinct from connectivity,
    which additionally requires the daemon to be running."""
    return shutil.which("ollama") is not None


def missing_models(client: "OllamaClient", required: list[str]) -> list[str]:
    """Return the subset of *required* model names not present locally.
    Matches on the model family (before ':') too, so "qwen3" satisfies
    a requirement of "qwen3:0.6b" if some qwen3 tag is installed — but we
    prefer an exact match first."""
    installed = set(client.list_models())
    installed_bases = {m.split(":")[0] for m in installed}
    missing = []
    for model in required:
        if model in installed:
            continue
        if model.split(":")[0] in installed_bases:
            continue
        missing.append(model)
    return missing


def pull_model_cli(model: str, on_line: Callable[[str], None] | None = None) -> bool:
    """Run `ollama pull <model>`, streaming output line-by-line.

    Uses the `ollama` CLI (not the HTTP API) because it renders its own
    live progress bars, which is the clearest live-progress experience
    without us reimplementing a download progress renderer. Returns True
    on success.
    """
    if not is_ollama_installed():
        return False
    try:
        proc = subprocess.Popen(
            ["ollama", "pull", model],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except OSError:
        return False

    assert proc.stdout is not None
    for line in proc.stdout:
        if on_line:
            on_line(line.rstrip("\n"))
    proc.wait()
    return proc.returncode == 0


def make_commit_client(cfg_ollama) -> OllamaClient:
    return OllamaClient(
        host=cfg_ollama.host,
        model=cfg_ollama.commit_model,
        timeout=cfg_ollama.timeout,
    )

def make_analysis_client(cfg_ollama) -> OllamaClient:
    return OllamaClient(
        host=cfg_ollama.host,
        model=cfg_ollama.analysis_model,
        timeout=cfg_ollama.timeout,
    )

def make_review_client(cfg_ollama) -> OllamaClient:
    return OllamaClient(
        host=cfg_ollama.host,
        model=cfg_ollama.review_model,
        timeout=cfg_ollama.timeout,
    )


# ── Diff summariser ───────────────────────────────────────────────────────────

_DEF_LINE_RE = re.compile(
    r"^([+-])\s*(?:async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)"
)
_DECORATOR_RE = re.compile(r"^([+-])\s*@([A-Za-z_][A-Za-z0-9_.]*)")
_IMPORT_RE = re.compile(
    r"^([+-])\s*(?:from\s+([A-Za-z_][A-Za-z0-9_.]*)\s+import|import\s+([A-Za-z_][A-Za-z0-9_.]*))"
)

# Known libraries/decorators → human-readable keyword phrases. Lets the
# summary say "slash commands" instead of just "app_commands".
_KEYWORD_MAP: dict[str, list[str]] = {
    "discord":     ["discord"],
    "app_commands": ["slash commands", "app_commands"],
    "commands":    ["bot commands"],
    "flask":       ["flask", "web"],
    "fastapi":     ["fastapi", "api"],
    "django":      ["django", "web"],
    "click":       ["cli"],
    "argparse":    ["cli"],
    "pytest":      ["tests"],
    "unittest":    ["tests"],
    "asyncio":     ["async"],
    "requests":    ["http"],
    "httpx":       ["http"],
    "sqlalchemy":  ["database"],
    "numpy":       ["numerics"],
    "pandas":      ["data"],
    "torch":       ["ml"],
    "tensorflow":  ["ml"],
}

_STOPWORD_BASES = {"typing", "dataclasses", "pathlib", "collections", "abc"}


def _module_base(name: str) -> str:
    return name.split(".", 1)[0]


# Fallback for non-Python files — same loose symbol detector as before.
_GENERIC_SYM_RE = re.compile(
    r"^[+-](?:function |const |let |var |export )"
    r"([A-Za-z_][A-Za-z0-9_]*)",
    re.MULTILINE,
)


def build_commit_summary(file: str, diff: str) -> tuple[str, int, int]:
    """
    Parse the raw diff into a compact, *semantic* text summary suitable as
    AI input — never the raw diff itself.

    For Python files this extracts added/removed function & class names,
    decorators, and import-derived keywords, so the model has something to
    reason about beyond a line count. For everything else it falls back to
    a loose symbol scan.

    Returns (summary_text, additions, deletions).
    """
    adds = dels = 0
    for line in diff.splitlines():
        if line.startswith("+") and not line.startswith("+++"):
            adds += 1
        elif line.startswith("-") and not line.startswith("---"):
            dels += 1

    ext = os.path.splitext(file)[1].lstrip(".") or "file"
    lines = [f"File: {file}", f"+{adds}  -{dels}", f"Type: {ext}"]

    if ext == "py":
        added_defs:   list[str] = []
        removed_defs: list[str] = []
        seen_added:   set[str] = set()
        seen_removed: set[str] = set()
        keyword_bases: list[str] = []  # decorator/import roots, in order seen
        seen_bases:    set[str] = set()

        for raw in diff.splitlines():
            if not raw or raw[0] not in "+-":
                continue
            if raw.startswith(("+++", "---")):
                continue

            m = _DEF_LINE_RE.match(raw)
            if m:
                sign, name = m.group(1), m.group(2)
                if sign == "+" and name not in seen_added:
                    seen_added.add(name)
                    added_defs.append(name)
                elif sign == "-" and name not in seen_removed:
                    seen_removed.add(name)
                    removed_defs.append(name)
                continue

            m = _DECORATOR_RE.match(raw)
            if m:
                base = _module_base(m.group(2))
                if base not in seen_bases and base not in _STOPWORD_BASES:
                    seen_bases.add(base)
                    keyword_bases.append(base)
                continue

            m = _IMPORT_RE.match(raw)
            if m:
                mod = m.group(2) or m.group(3) or ""
                base = _module_base(mod)
                if base and base not in seen_bases and base not in _STOPWORD_BASES:
                    seen_bases.add(base)
                    keyword_bases.append(base)

        if added_defs:
            lines.append("\nAdded symbols:")
            for s in added_defs[:8]:
                lines.append(f"- {s}")
        if removed_defs:
            lines.append("\nRemoved symbols:")
            for s in removed_defs[:8]:
                lines.append(f"- {s}")

        # Translate bases into human-readable keywords, preferring the
        # mapped phrases (e.g. "app_commands" -> "slash commands").
        keywords: list[str] = []
        seen_kw: set[str] = set()
        for base in keyword_bases:
            for phrase in _KEYWORD_MAP.get(base, [base]):
                if phrase not in seen_kw:
                    seen_kw.add(phrase)
                    keywords.append(phrase)
        if keywords:
            lines.append("\nKeywords:")
            for kw in keywords[:6]:
                lines.append(f"- {kw}")

        if not added_defs and not removed_defs and not keywords:
            # No semantic signal extracted — say so explicitly rather than
            # silently falling back to a bare line-count summary.
            lines.append("\n(no function/class/import changes detected)")
    else:
        symbols: list[str] = []
        seen: set[str] = set()
        for m in _GENERIC_SYM_RE.finditer(diff):
            name = m.group(1)
            if name not in seen:
                seen.add(name)
                symbols.append(name)
        if symbols:
            lines.append("\nSymbols changed:")
            for s in symbols[:12]:
                lines.append(f"- {s}")

    return "\n".join(lines), adds, dels


# ── Message cache ─────────────────────────────────────────────────────────────

def _cache_path(root: Path) -> Path:
    d = root / ".kyte"
    d.mkdir(exist_ok=True)
    return d / "cache.json"


def _load_cache(root: Path) -> dict:
    p = _cache_path(root)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _save_cache(root: Path, cache: dict) -> None:
    try:
        _cache_path(root).write_text(
            json.dumps(cache, indent=2), encoding="utf-8"
        )
    except OSError:
        pass


def _diff_hash(diff: str) -> str:
    return hashlib.sha1(diff.encode()).hexdigest()[:16]


# ── Auto message (no AI) ──────────────────────────────────────────────────────

_TYPE_MAP = {
    ".py": "chore", ".js": "chore", ".ts": "chore",
    ".css": "style", ".scss": "style",
    ".md": "docs", ".rst": "docs", ".txt": "docs",
    ".json": "chore", ".toml": "chore", ".yaml": "chore", ".yml": "chore",
    ".sh": "chore", ".bash": "chore",
}

def _auto_message(file: str, adds: int, dels: int) -> str:
    ext  = os.path.splitext(file)[1].lower()
    typ  = _TYPE_MAP.get(ext, "chore")
    stem = os.path.splitext(os.path.basename(file))[0]
    scope = stem.replace("_", "-").replace(" ", "-")
    if adds > 0 and dels == 0:
        verb = "add"
    elif dels > 0 and adds == 0:
        verb = "remove"
    else:
        verb = "update"
    return f"{typ}({scope}): {verb} {file}"


# ── Public API ────────────────────────────────────────────────────────────────

def generate_commit_message(
    client: OllamaClient,
    enabled: bool,
    fallback_template: str,
    file: str,
    diff: str,
    root: Path | None = None,
    auto_threshold: int = 10,
    use_auto_small: bool = True,
) -> tuple[str, str]:
    """
    Returns (message, source).
    source ∈ {"ollama", "cache", "auto", "fallback"}

    Fallback hierarchy:
      1. cache hit  (same diff hash seen before)
      2. auto       (small change, skip AI)
      3. ollama     (AI with compact summary)
      4. fallback   (template string)
    """
    fallback_msg = fallback_template.format(file=file)

    summary, adds, dels = build_commit_summary(file, diff)
    total_lines = adds + dels

    # ── 1. cache ──────────────────────────────────────────────────────────────
    if root and diff.strip():
        cache = _load_cache(root)
        key   = _diff_hash(diff)
        if key in cache:
            return cache[key], "cache"

    # ── 2. fast-path: tiny change ─────────────────────────────────────────────
    if use_auto_small and total_lines <= auto_threshold:
        msg = _auto_message(file, adds, dels)
        if root and diff.strip():
            cache = _load_cache(root)
            cache[_diff_hash(diff)] = msg
            _save_cache(root, cache)
        return msg, "auto"

    # ── 3. AI ─────────────────────────────────────────────────────────────────
    if not enabled or not diff.strip():
        return fallback_msg, "fallback"

    prompt = (
        f"{summary}\n\n"
        "Write a one-line conventional commit message for this change."
    )
    try:
        message = client.generate(prompt, system=SYSTEM_COMMIT_MSG)
    except OllamaError:
        return fallback_msg, "fallback"

    # Strip any reasoning tags qwen3 might still emit
    message = re.sub(r"<think>.*?</think>", "", message, flags=re.DOTALL)
    message = message.strip().strip('"').splitlines()[0] if message else ""
    if not message:
        return fallback_msg, "fallback"

    # ── 4. cache write ────────────────────────────────────────────────────────
    if root and diff.strip():
        cache = _load_cache(root)
        cache[_diff_hash(diff)] = message
        _save_cache(root, cache)

    return message, "ollama"


def analyze_diff(client: OllamaClient, project: str, files: list[str], diff: str) -> str:
    from .utils import truncate
    files_block = "\n".join(f"  - {f}" for f in files[:50])
    prompt = (
        f"Project: {project}\n\nChanged files:\n{files_block}\n\n"
        f"Diff:\n{truncate(diff, 6000)}\n\n"
        "Respond in this format:\n\n"
        "Summary:\n<one sentence>\n\nChanges:\n<bullet list>\n\n"
        "Risks:\n<bullet list or 'None identified'>"
    )
    try:
        return client.generate(prompt, system=SYSTEM_REVIEW)
    except OllamaError as exc:
        raise OllamaError(f"Analysis failed: {exc}") from exc


def review_diff(client: OllamaClient, file: str, diff: str) -> str:
    from .utils import truncate
    prompt = (
        f"File: {file}\n\nDiff:\n{truncate(diff, 6000)}\n\n"
        "Review this change. Respond in this format:\n\n"
        "Quality:\n<one sentence>\n\nIssues:\n<bullet list or 'None'>\n\n"
        "Suggestions:\n<bullet list or 'None'>"
    )
    try:
        return client.generate(prompt, system=SYSTEM_REVIEW)
    except OllamaError as exc:
        raise OllamaError(f"Review failed: {exc}") from exc