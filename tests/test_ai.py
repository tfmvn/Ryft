from pathlib import Path

import pytest

from ryft import ai


DIFF = """diff --git a/foo.py b/foo.py
--- a/foo.py
+++ b/foo.py
@@ -1,2 +1,5 @@
+import requests
+
+def fetch():
+    return requests.get("x")
 x = 1
-y = 2
"""


def test_build_commit_summary_counts_lines():
    summary, adds, dels = ai.build_commit_summary("foo.py", DIFF)
    assert adds == 4
    assert dels == 1
    assert "foo.py" in summary


def test_build_commit_summary_extracts_added_symbols_and_keywords():
    summary, _, _ = ai.build_commit_summary("foo.py", DIFF)
    assert "fetch" in summary
    assert "http" in summary  # requests -> http keyword mapping


def test_build_commit_summary_generic_fallback_for_non_python():
    diff = "+function doThing() {}\n-const x = 1\n"
    summary, adds, dels = ai.build_commit_summary("foo.js", diff)
    assert "doThing" in summary


class _FakeClient:
    def __init__(self, response="feat(foo): add fetch helper"):
        self.response = response
        self.calls = 0

    def generate(self, prompt, system=None):
        self.calls += 1
        return self.response


def test_generate_commit_message_auto_path_for_small_change(tmp_path):
    diff = "+x = 1\n"  # 1 line, below threshold
    client = _FakeClient()
    msg, source = ai.generate_commit_message(
        client, enabled=True, fallback_template="chore: update {file}",
        file="a.py", diff=diff, root=tmp_path, auto_threshold=10, use_auto_small=True,
    )
    assert source == "auto"
    assert client.calls == 0


def test_generate_commit_message_uses_ai_for_large_change(tmp_path):
    diff = "\n".join(f"+line{i}" for i in range(20))
    client = _FakeClient("feat: big change")
    msg, source = ai.generate_commit_message(
        client, enabled=True, fallback_template="chore: update {file}",
        file="a.py", diff=diff, root=tmp_path, auto_threshold=10, use_auto_small=True,
    )
    assert source == "ollama"
    assert msg == "feat: big change"
    assert client.calls == 1


def test_generate_commit_message_cache_hit_skips_ai(tmp_path):
    diff = "\n".join(f"+line{i}" for i in range(20))
    client = _FakeClient("feat: first")
    ai.generate_commit_message(
        client, enabled=True, fallback_template="chore: update {file}",
        file="a.py", diff=diff, root=tmp_path, auto_threshold=10, use_auto_small=True,
    )
    client2 = _FakeClient("feat: should not be used")
    msg, source = ai.generate_commit_message(
        client2, enabled=True, fallback_template="chore: update {file}",
        file="a.py", diff=diff, root=tmp_path, auto_threshold=10, use_auto_small=True,
    )
    assert source == "cache"
    assert msg == "feat: first"
    assert client2.calls == 0


def test_generate_commit_message_fallback_when_disabled(tmp_path):
    diff = "\n".join(f"+line{i}" for i in range(20))
    client = _FakeClient()
    msg, source = ai.generate_commit_message(
        client, enabled=False, fallback_template="chore: update {file}",
        file="a.py", diff=diff, root=tmp_path, auto_threshold=10, use_auto_small=True,
    )
    assert source == "fallback"
    assert msg == "chore: update a.py"


def test_generate_commit_message_strips_think_tags(tmp_path):
    diff = "\n".join(f"+line{i}" for i in range(20))
    client = _FakeClient("<think>reasoning...</think>feat: clean message")
    msg, source = ai.generate_commit_message(
        client, enabled=True, fallback_template="chore: update {file}",
        file="a.py", diff=diff, root=tmp_path, auto_threshold=10, use_auto_small=True,
    )
    assert source == "ollama"
    assert "<think>" not in msg
    assert msg == "feat: clean message"


def test_missing_models_exact_and_family_match():
    class C:
        def list_models(self):
            return ["qwen3:0.6b", "llama3.2:3b"]
    c = C()
    missing = ai.missing_models(c, ["qwen3:0.6b", "qwen3:8b", "mistral:7b"])
    # qwen3:8b satisfied by family match on "qwen3"; mistral is truly missing
    assert missing == ["mistral:7b"]


def test_is_ollama_installed_reflects_which(monkeypatch):
    monkeypatch.setattr(ai.shutil, "which", lambda name: "/usr/bin/ollama" if name == "ollama" else None)
    assert ai.is_ollama_installed() is True
    monkeypatch.setattr(ai.shutil, "which", lambda name: None)
    assert ai.is_ollama_installed() is False


def test_pull_model_cli_returns_false_when_not_installed(monkeypatch):
    monkeypatch.setattr(ai, "is_ollama_installed", lambda: False)
    assert ai.pull_model_cli("qwen3:0.6b") is False
