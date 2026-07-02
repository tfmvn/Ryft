from pathlib import Path

import pytest

from ryft import commands, config, git, ui
from ryft.models import AppContext
from ryft.sync import SyncController
from ryft.utils import ActivityFeed


def _ctx_for(root: Path) -> AppContext:
    cfg = config.load_config(root)
    ctx = AppContext(config=cfg, ai=None, activity=ActivityFeed(), console=None)
    ctx.sync = SyncController(ctx)
    return ctx


def test_dispatch_argv_unknown_command_reports_without_slash(tmp_path):
    ctx = _ctx_for(tmp_path)
    commands.dispatch_argv(ctx, ["nope"])
    out = ui.console.file.getvalue()
    assert "Unknown command: nope" in out
    assert "/nope" not in out


def test_dispatch_argv_preserves_multi_word_argument(tmp_path, monkeypatch):
    """A value containing spaces (e.g. a quoted filename from the shell)
    must reach the handler as ONE argument, not be re-split on spaces."""
    ctx = _ctx_for(tmp_path)
    seen = {}

    def fake_diff(ctx, args):
        seen["args"] = args

    monkeypatch.setattr(commands.COMMANDS["diff"], "handler", fake_diff)
    commands.dispatch_argv(ctx, ["diff", "my dir/a file.py"])
    assert seen["args"] == ["my dir/a file.py"]


def test_dispatch_repl_still_uses_slash_prefixed_errors(tmp_path):
    ctx = _ctx_for(tmp_path)
    commands.dispatch(ctx, "/nope")
    out = ui.console.file.getvalue()
    assert "Unknown command: /nope" in out


def test_cmd_init_creates_config_on_accept(tmp_path, monkeypatch):
    monkeypatch.setattr(ui, "confirm", lambda *a, **k: True)
    ctx = _ctx_for(tmp_path)
    ctx.config.root = tmp_path
    commands.cmd_init(ctx, [])
    assert (tmp_path / config.CONFIG_FILENAME).exists()
    assert ctx.config.path is not None


def test_cmd_init_is_idempotent_when_already_valid(tmp_path, monkeypatch):
    config.init_config(tmp_path, "proj")
    ctx = _ctx_for(tmp_path)

    # Should report "already initialized" and NOT prompt to overwrite
    # unless the user is asked and explicitly declines.
    monkeypatch.setattr(ui, "confirm", lambda *a, **k: False)
    original = (tmp_path / config.CONFIG_FILENAME).read_text()
    commands.cmd_init(ctx, [])
    out = ui.console.file.getvalue()
    assert "already initialized" in out
    assert (tmp_path / config.CONFIG_FILENAME).read_text() == original
