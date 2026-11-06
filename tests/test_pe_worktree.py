"""Tests for lib/pe_worktree.py: the temporary worktree that two skill scripts share, in temporary repositories."""
import tempfile
from pathlib import Path

import pytest

from pe_worktree import WorktreeError, temporary_worktree
from support import commit, git, init_repo


def worktree_entries(repo: Path) -> int:
    return len(git(repo, "worktree", "list").splitlines())


def test_the_temporary_worktree_is_removed_on_success_and_on_failure(tmp_path, monkeypatch):
    repo = init_repo(tmp_path / "repo")
    tip = commit(repo, {"a.txt": "one\n"}, "one")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))  # tempfile caches its folder: the variables come too late
    monkeypatch.chdir(repo)

    with temporary_worktree(tip, "pe-test-") as folder:
        assert (Path(folder) / "a.txt").read_text(encoding="utf-8") == "one\n"
        assert Path(folder).parent == scratch and Path(folder).name.startswith("pe-test-")
        assert worktree_entries(repo) == 2
    assert worktree_entries(repo) == 1 and not Path(folder).exists()

    with pytest.raises(RuntimeError):
        with temporary_worktree(tip, "pe-test-") as failed:
            raise RuntimeError("the body failed")
    assert worktree_entries(repo) == 1 and not Path(failed).exists() and list(scratch.iterdir()) == []


def test_a_worktree_that_cannot_be_added_raises_the_typed_error(tmp_path, monkeypatch):
    repo = init_repo(tmp_path / "repo")
    commit(repo, {"a.txt": "one\n"}, "one")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    monkeypatch.chdir(repo)
    with pytest.raises(WorktreeError):
        with temporary_worktree("no-such-revision", "pe-test-"):
            pytest.fail("the body must not run")
    assert worktree_entries(repo) == 1 and list(scratch.iterdir()) == []  # the folder made first is not left
