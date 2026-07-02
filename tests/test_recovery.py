from pathlib import Path

import pytest

from ryft import config, git, recovery, ui
from ryft.models import AppContext


def _ctx_for(root: Path) -> AppContext:
    cfg = config.load_config(root)
    return AppContext(config=cfg, ai=None, activity=None, console=None)


def test_ensure_git_repo_declines(tmp_path, monkeypatch):
    monkeypatch.setattr(ui, "confirm", lambda *a, **k: False)
    assert recovery.ensure_git_repo(tmp_path) is False
    assert not git.is_repo(tmp_path)


def test_ensure_git_repo_accepts(tmp_path, monkeypatch):
    monkeypatch.setattr(ui, "confirm", lambda *a, **k: True)
    assert recovery.ensure_git_repo(tmp_path) is True
    assert git.is_repo(tmp_path)


def test_ensure_git_repo_noop_if_already_repo(tmp_path, monkeypatch):
    git.init(tmp_path)
    calls = []
    monkeypatch.setattr(ui, "confirm", lambda *a, **k: calls.append(1) or True)
    assert recovery.ensure_git_repo(tmp_path) is True
    assert calls == []  # never asked — already a repo


def test_ensure_config_creates_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(ui, "confirm", lambda *a, **k: True)
    ctx = _ctx_for(tmp_path)
    assert recovery.ensure_config(ctx) is True
    assert (tmp_path / ".src.py").exists()
    assert ctx.config.path is not None


def test_ensure_config_declines(tmp_path, monkeypatch):
    monkeypatch.setattr(ui, "confirm", lambda *a, **k: False)
    ctx = _ctx_for(tmp_path)
    assert recovery.ensure_config(ctx) is False
    assert not (tmp_path / ".src.py").exists()


def test_ensure_config_noop_when_already_valid(tmp_path, monkeypatch):
    config.init_config(tmp_path, "proj")
    calls = []
    monkeypatch.setattr(ui, "confirm", lambda *a, **k: calls.append(1) or True)
    ctx = _ctx_for(tmp_path)
    assert recovery.ensure_config(ctx) is True
    assert calls == []


def test_ensure_branch_creates_when_detached(tmp_path, monkeypatch):
    import subprocess
    git.init(tmp_path)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "a.py").write_text("x = 1\n")
    git.commit_file(tmp_path, "a.py", "init")

    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_path, check=True,
                          capture_output=True, text=True).stdout.strip()
    subprocess.run(["git", "checkout", sha], cwd=tmp_path, check=True, capture_output=True)
    assert git.current_branch(tmp_path) == "(detached)"

    monkeypatch.setattr(ui, "confirm", lambda *a, **k: True)
    assert recovery.ensure_branch(tmp_path, "develop") is True
    assert git.current_branch(tmp_path) == "develop"


def test_ensure_branch_noop_when_already_on_a_branch(tmp_path, monkeypatch):
    git.init(tmp_path)
    calls = []
    monkeypatch.setattr(ui, "confirm", lambda *a, **k: calls.append(1) or True)
    assert recovery.ensure_branch(tmp_path, "main") is True
    assert calls == []
