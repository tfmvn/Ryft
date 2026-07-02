from pathlib import Path

import pytest

from ryft import config, onboarding, ui


def test_needs_onboarding_true_without_config(tmp_path):
    assert onboarding.needs_onboarding(tmp_path) is True


def test_needs_onboarding_false_with_config(tmp_path):
    config.init_config(tmp_path, "x")
    assert onboarding.needs_onboarding(tmp_path) is False


def test_run_onboarding_creates_config_on_accept(tmp_path, monkeypatch):
    monkeypatch.setattr(ui, "confirm", lambda *a, **k: True)
    cfg, created = onboarding.run_onboarding(tmp_path)
    assert created is True
    assert (tmp_path / ".src.py").exists()
    assert cfg.project.name == tmp_path.name


def test_run_onboarding_skips_file_on_decline(tmp_path, monkeypatch):
    monkeypatch.setattr(ui, "confirm", lambda *a, **k: False)
    cfg, created = onboarding.run_onboarding(tmp_path)
    assert created is False
    assert not (tmp_path / ".src.py").exists()
    # still returns a usable config with sane defaults
    assert cfg.ollama.commit_model == "qwen3:0.6b"
