from pathlib import Path

import pytest

from kyte import config


def test_find_root_none_when_absent(tmp_path):
    assert config.find_root(tmp_path) is None


def test_find_root_walks_up_to_parent(tmp_path):
    (tmp_path / ".src.py").write_text("class Project:\n    name = 'x'\n")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert config.find_root(nested) == tmp_path


def test_load_config_defaults_when_missing(tmp_path):
    cfg = config.load_config(tmp_path)
    assert cfg.project.name == tmp_path.name
    assert cfg.ollama.commit_model == "qwen3:0.6b"
    assert cfg.git.branch == "main"
    assert cfg.path is None


def test_init_config_then_load_roundtrips(tmp_path):
    path = config.init_config(tmp_path, "myproj")
    assert path.exists()
    cfg = config.load_config(tmp_path)
    assert cfg.project.name == "myproj"
    assert cfg.path == path
    assert cfg.ollama.analysis_model.startswith("qwen2.5-coder")


def test_validate_config_missing(tmp_path):
    status, detail = config.validate_config(tmp_path)
    assert status == "missing"
    assert detail is None


def test_validate_config_valid(tmp_path):
    config.init_config(tmp_path, "ok")
    status, detail = config.validate_config(tmp_path)
    assert status == "valid"
    assert detail is None


def test_validate_config_invalid(tmp_path):
    (tmp_path / ".src.py").write_text("this is not python (((")
    status, detail = config.validate_config(tmp_path)
    assert status == "invalid"
    assert detail is not None


def test_set_model_updates_memory_and_disk(tmp_path):
    config.init_config(tmp_path, "proj")
    cfg = config.load_config(tmp_path)
    config.set_model(cfg, "llama3.2:3b")
    assert cfg.ollama.commit_model == "llama3.2:3b"

    reloaded = config.load_config(tmp_path)
    assert reloaded.ollama.commit_model == "llama3.2:3b"


def test_is_ignored_dotfiles_and_defaults(tmp_path):
    assert config.is_ignored(tmp_path / ".git", tmp_path, [])
    assert config.is_ignored(tmp_path / "__pycache__" / "x.pyc", tmp_path, [])
    assert not config.is_ignored(tmp_path / "src" / "main.py", tmp_path, [])
    assert config.is_ignored(tmp_path / "node_modules" / "x.js", tmp_path, ["node_modules"])
