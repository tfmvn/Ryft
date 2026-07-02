import subprocess
from pathlib import Path

import pytest

from ryft import config, doctor, git
from ryft.models import AppContext, Config


def _ctx_for(root: Path) -> AppContext:
    cfg = config.load_config(root)
    return AppContext(config=cfg, ai=None, activity=None, console=None)


def test_repo_check_fail_without_git(tmp_path):
    ctx = _ctx_for(tmp_path)
    checks = doctor.run_doctor(ctx)
    repo_check = next(c for c in checks if c.name == "Current repository")
    assert repo_check.status == "fail"
    assert repo_check.auto_fix is not None


def test_repo_check_ok_with_git(tmp_path):
    git.init(tmp_path)
    ctx = _ctx_for(tmp_path)
    checks = doctor.run_doctor(ctx)
    repo_check = next(c for c in checks if c.name == "Current repository")
    assert repo_check.status == "ok"


def test_remote_and_branch_skip_without_repo(tmp_path):
    ctx = _ctx_for(tmp_path)
    checks = doctor.run_doctor(ctx)
    remote = next(c for c in checks if c.name == "Remote origin")
    branch = next(c for c in checks if c.name == "Current branch")
    assert "skipped" in remote.detail
    assert "skipped" in branch.detail


def test_config_check_missing_has_auto_fix(tmp_path):
    ctx = _ctx_for(tmp_path)
    checks = doctor.run_doctor(ctx)
    cfg_check = next(c for c in checks if c.name == "Configuration")
    assert cfg_check.status == "warn"
    assert cfg_check.auto_fix is not None


def test_config_check_valid(tmp_path):
    config.init_config(tmp_path, "proj")
    ctx = _ctx_for(tmp_path)
    checks = doctor.run_doctor(ctx)
    cfg_check = next(c for c in checks if c.name == "Configuration")
    assert cfg_check.status == "ok"


def test_config_check_invalid(tmp_path):
    (tmp_path / ".src.py").write_text("not valid python (((")
    ctx = _ctx_for(tmp_path)
    checks = doctor.run_doctor(ctx)
    cfg_check = next(c for c in checks if c.name == "Configuration")
    assert cfg_check.status == "fail"


def test_permissions_check_fail_when_unwritable(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor.os, "access", lambda path, mode: False)
    ctx = _ctx_for(tmp_path)
    checks = doctor.run_doctor(ctx)
    perm = next(c for c in checks if c.name == "Permissions")
    assert perm.status == "fail"


def test_repo_state_flags_stale_lock(tmp_path):
    git.init(tmp_path)
    (tmp_path / ".git" / "index.lock").write_text("")
    ctx = _ctx_for(tmp_path)
    checks = doctor.run_doctor(ctx)
    state = next(c for c in checks if c.name == "Repository state")
    assert state.status == "fail"


def test_summarize_counts():
    class C:
        def __init__(self, s): self.status = s
    checks = [C("ok"), C("ok"), C("warn"), C("fail")]
    ok, warn, fail = doctor.summarize(checks)
    assert (ok, warn, fail) == (2, 1, 1)


def test_config_auto_fix_creates_file(tmp_path, monkeypatch):
    from ryft import ui
    monkeypatch.setattr(ui, "confirm", lambda *a, **k: True)

    ctx = _ctx_for(tmp_path)
    checks = doctor.run_doctor(ctx)
    cfg_check = next(c for c in checks if c.name == "Configuration")
    assert cfg_check.auto_fix() is True
    assert (tmp_path / ".src.py").exists()
    assert ctx.config.path is not None
