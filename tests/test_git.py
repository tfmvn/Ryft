"""Tests for the git layer (ryft.git) against the real repo."""

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def test_is_repo_true() -> None:
    from ryft import git

    assert git.is_repo(REPO) is True


def test_recent_commits_returns_list() -> None:
    from ryft import git

    commits = git.recent_commits(REPO, 5)
    assert isinstance(commits, list)
    assert commits
    assert "hash" in commits[0]
    assert "subject" in commits[0]


def test_graph_returns_nonempty_string() -> None:
    from ryft import git

    out = git.graph(REPO, 5)
    assert isinstance(out, str)
    assert out.strip()


def test_current_branch_nonempty() -> None:
    from ryft import git

    assert git.current_branch(REPO)
