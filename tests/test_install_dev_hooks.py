"""Tests for tools/install_dev_hooks.py, with real pushes to a local bare remote."""
import json
import stat
import subprocess
from pathlib import Path

import pytest

import install_dev_hooks as idh
from support import REPO_ROOT, commit, git, init_repo, run_script

COPIED_FILES = ("tools/privacy_check.py", "tools/dev_guard.py", "lib/pe_guard/__init__.py", "lib/pe_guard/filters.py")


def prepared_clone(tmp_path: Path, name: str = "clone") -> Path:
    """A clone with a bare remote and a terms file, and no tools/ of its own.

    Without tools/ in the working tree the hook can only work by running the
    installed copy, as it must on a branch that does not have the tools.
    """
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    repo = init_repo(tmp_path / name)
    git(repo, "remote", "add", "origin", str(remote))
    terms = tmp_path / "terms.txt"
    terms.write_text("Zorblax\n", encoding="utf-8")
    git(repo, "config", "pe.privateTermsFile", str(terms))
    return repo


def push(repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "push", "-q", "origin", "HEAD:refs/heads/main"],
                          cwd=str(repo), capture_output=True, text=True)


def test_install_writes_an_executable_hook_with_the_marker(tmp_path):
    repo = prepared_clone(tmp_path)
    hook = idh.install(repo)
    assert hook == repo / ".git" / "hooks" / "pre-push"
    assert idh.HOOK_MARKER in hook.read_text(encoding="utf-8")
    assert hook.stat().st_mode & stat.S_IXUSR


def test_install_copies_the_checks_outside_the_working_tree(tmp_path):
    repo = prepared_clone(tmp_path)
    idh.install(repo)
    copy = idh.copy_dir(repo)
    assert copy == repo / ".git" / "pragmatic-engineering" / "step-zero"
    for relative in COPIED_FILES:
        assert (copy / relative).read_bytes() == (REPO_ROOT / relative).read_bytes(), relative


def test_refreshing_the_copy_leaves_the_rest_of_the_data_folder_alone(tmp_path):
    repo = prepared_clone(tmp_path)
    data = repo / ".git" / "pragmatic-engineering"
    data.mkdir()
    (data / "events.jsonl").write_text("{}\n", encoding="utf-8")
    idh.install(repo)
    idh.install(repo)
    assert sorted(p.name for p in data.iterdir()) == ["events.jsonl", "step-zero"]
    assert (data / "events.jsonl").read_text(encoding="utf-8") == "{}\n"


def test_reinstall_refreshes_a_stale_copy(tmp_path):
    repo = prepared_clone(tmp_path)
    idh.install(repo)
    copy = idh.copy_dir(repo)
    stale = copy / "tools" / "privacy_check.py"
    stale.write_text("raise SystemExit(0)\n", encoding="utf-8")
    idh.install(repo)
    assert stale.read_bytes() == (REPO_ROOT / "tools" / "privacy_check.py").read_bytes()
    assert not copy.with_name("step-zero.new").exists()
    assert not copy.with_name("step-zero.old").exists()


def test_installed_project_hook_runs_from_the_copy(tmp_path):
    repo = prepared_clone(tmp_path)
    idh.install(repo)
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git push --no-verify"}})
    proc = run_script(idh.copy_dir(repo) / "tools" / "dev_guard.py", [], cwd=repo, stdin=payload)
    assert proc.returncode == 2
    assert "--no-verify" in proc.stderr


def test_install_is_idempotent(tmp_path):
    repo = prepared_clone(tmp_path)
    first = idh.install(repo).read_text(encoding="utf-8")
    second = idh.install(repo).read_text(encoding="utf-8")
    assert first == second == idh.render_hook()


def test_install_refuses_a_foreign_pre_push(tmp_path):
    repo = prepared_clone(tmp_path)
    foreign = repo / ".git" / "hooks" / "pre-push"
    foreign.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    with pytest.raises(idh.InstallError, match="did not write"):
        idh.install(repo)
    assert foreign.read_text(encoding="utf-8") == "#!/bin/sh\nexit 0\n"


def test_install_refuses_when_a_custom_hooks_directory_is_configured(tmp_path):
    repo = prepared_clone(tmp_path)
    git(repo, "config", "core.hooksPath", ".githooks")
    with pytest.raises(idh.InstallError, match="git config --unset core.hooksPath"):
        idh.install(repo)


def test_installed_hook_blocks_a_real_push_with_a_private_term(tmp_path):
    repo = prepared_clone(tmp_path)
    idh.install(repo)
    commit(repo, {"notes.txt": "for Zorblax\n"}, "notes")
    proc = push(repo)
    assert proc.returncode != 0
    assert "privacy check: blocked" in proc.stderr
    remote_heads = git(tmp_path / "remote.git", "for-each-ref", "refs/heads")
    assert remote_heads == ""


def test_installed_hook_lets_a_clean_push_through(tmp_path):
    repo = prepared_clone(tmp_path)
    idh.install(repo)
    commit(repo, {"notes.txt": "clean\n"}, "notes")
    proc = push(repo)
    assert proc.returncode == 0, proc.stderr


def test_hook_runs_for_pushes_from_a_linked_worktree(tmp_path):
    repo = prepared_clone(tmp_path)
    idh.install(repo)
    commit(repo, {"a.txt": "base\n"}, "base")
    worktree = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", "-b", "side", str(worktree))
    commit(worktree, {"b.txt": "Zorblax\n"}, "side work")
    proc = push(worktree)
    assert proc.returncode != 0
    assert "privacy check: blocked" in proc.stderr


def test_install_in_path_with_spaces_and_apostrophe(tmp_path):
    repo = prepared_clone(tmp_path, name="it's my clone")
    idh.install(repo)
    commit(repo, {"notes.txt": "clean\n"}, "notes")
    proc = push(repo)
    assert proc.returncode == 0, proc.stderr


def test_main_prints_the_installed_path(tmp_path, capsys):
    repo = prepared_clone(tmp_path)
    assert idh.main([str(repo)]) == 0
    out = capsys.readouterr().out
    assert "pre-push" in out and "step-zero" in out
