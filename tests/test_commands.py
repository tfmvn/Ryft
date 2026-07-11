"""Tests for the command registry and one-shot dispatch (offline, read-only)."""

import pytest

from ryft.commands import REGISTRY, dispatch_argv
from ryft.core.lifecycle import build_context


SAFE_COMMANDS = [
    ["graph", "3"],
    ["timeline", "3"],
    ["providers"],
    ["plugins"],
    ["dashboard"],
    ["status"],
    ["memory"],
    ["config"],
    ["doctor"],
    ["help"],
]


@pytest.fixture(scope="module")
def ctx():
    c = build_context()
    yield c

    c.running = False


def test_registry_has_core_commands() -> None:
    for name in (
        "commit",
        "status",
        "doctor",
        "config",
        "format",
        "ask",
        "search",
        "explain",
        "release",
        "memory",
        "providers",
        "plugins",
        "github",
        "cloud",
        "dashboard",
        "graph",
        "timeline",
        "sessions",
        "watch",
        "sync",
        "help",
    ):
        assert name in REGISTRY, f"missing command: {name}"


def test_dispatch_readonly_commands(ctx, capsys) -> None:
    for argv in SAFE_COMMANDS:
        capsys.readouterr()
        dispatch_argv(ctx, argv)
        out = capsys.readouterr().out
        assert out.strip(), f"command {argv} produced no output"
