import subprocess
from pathlib import Path

import pytest

from kyte import git


@pytest.fixture
def repo(tmp_path):
    git.init(tmp_path)
    subprocess.run(["git", "config", "user.email", "t@t.com"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "tester"], cwd=tmp_path, check=True)
    return tmp_path


def test_is_installed():
    assert git.is_installed() is True


def test_is_repo_false_for_plain_dir(tmp_path):
    assert git.is_repo(tmp_path) is False


def test_init_and_is_repo(repo):
    assert git.is_repo(repo) is True


def test_current_branch_before_first_commit(repo):
    # Before the first commit, some git versions report the branch name
    # anyway (init.defaultBranch); either way this must not raise.
    branch = git.current_branch(repo)
    assert isinstance(branch, str)


def test_changed_files_detects_untracked(repo):
    (repo / "a.py").write_text("x = 1\n")
    changes = git.changed_files(repo)
    assert any(c.path == "a.py" and c.status == "?" for c in changes)


def test_commit_file_and_diff(repo):
    f = repo / "a.py"
    f.write_text("x = 1\n")
    out = git.commit_file(repo, "a.py", "chore: add a.py")
    assert "chore: add a.py" in out or out != ""
    assert git.changed_files(repo) == []

    f.write_text("x = 1\ny = 2\n")
    diff = git.diff_for(repo, "a.py")
    assert "+y = 2" in diff


def test_diff_stat_counts_additions(repo):
    f = repo / "a.py"
    f.write_text("x = 1\n")
    git.commit_file(repo, "a.py", "init")
    f.write_text("x = 1\ny = 2\nz = 3\n")
    stats = git.diff_stat(repo)
    assert stats and stats[0][0] == "a.py"
    assert stats[0][1] == 2  # two added lines


def test_has_remote_false_by_default(repo):
    assert git.has_remote(repo) is False
    assert git.remote_url(repo) is None


def test_has_remote_true_after_add(repo):
    subprocess.run(["git", "remote", "add", "origin", "https://example.com/x.git"],
                    cwd=repo, check=True)
    assert git.has_remote(repo, "origin") is True
    assert git.remote_url(repo, "origin") == "https://example.com/x.git"


def test_is_locked_false_normally(repo):
    assert git.is_locked(repo) is False


def test_is_locked_true_with_stale_lock(repo):
    (repo / ".git" / "index.lock").write_text("")
    assert git.is_locked(repo) is True


def test_branch_exists_and_create_branch(repo):
    (repo / "a.py").write_text("x = 1\n")
    git.commit_file(repo, "a.py", "init")
    assert git.branch_exists(repo, "feature-x") is False
    git.create_branch(repo, "feature-x")
    assert git.branch_exists(repo, "feature-x") is True
    assert git.current_branch(repo) == "feature-x"


def test_log_no_commits_is_empty(repo):
    assert git.log(repo) == ""


def test_push_pull_raise_gitError_without_remote(repo):
    with pytest.raises(git.GitError):
        git.push(repo, "origin", "main")
