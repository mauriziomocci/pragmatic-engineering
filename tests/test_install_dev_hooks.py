"""Tests for tools/install_dev_hooks.py, with real pushes to a local bare remote."""
import json
import os
import shlex
import shutil
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


def assert_nothing_installed(repo: Path) -> None:
    """A refusal must come before the first write: no copy, and no stub in the working tree."""
    assert not (repo / ".git" / "pragmatic-engineering").exists()
    assert not (repo / "pre-push").exists()


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
    with pytest.raises(idh.InstallError, match="did not write") as refusal:
        idh.install(repo)
    assert foreign.read_text(encoding="utf-8") == "#!/bin/sh\nexit 0\n"
    assert_nothing_installed(repo)
    # a hand-chained hook that kept the marker line would be overwritten on the next install
    assert idh.HOOK_MARKER in str(refusal.value)


@pytest.mark.parametrize("target_has_the_marker", [False, True], ids=["dangling", "marked-target"])
def test_install_refuses_a_symlink_at_pre_push(tmp_path, target_has_the_marker):
    """Writing through a symlink would put the stub outside the git directory."""
    repo = prepared_clone(tmp_path)
    target = tmp_path / "elsewhere" / "team-pre-push"
    target.parent.mkdir()
    if target_has_the_marker:
        target.write_text(idh.render_hook(), encoding="utf-8")
    link = repo / ".git" / "hooks" / "pre-push"
    link.symlink_to(target)
    with pytest.raises(idh.InstallError, match="did not write"):
        idh.install(repo)
    assert link.is_symlink()
    assert target.exists() == target_has_the_marker
    assert_nothing_installed(repo)


def test_install_refuses_when_a_custom_hooks_directory_is_configured(tmp_path):
    repo = prepared_clone(tmp_path)
    git(repo, "config", "core.hooksPath", ".githooks")
    with pytest.raises(idh.InstallError, match="git config --unset core.hooksPath"):
        idh.install(repo)
    assert_nothing_installed(repo)


def test_install_refuses_an_empty_core_hooks_path(tmp_path):
    """An empty value is still a value: git then runs no hook, and the stub would land in the working tree."""
    repo = prepared_clone(tmp_path)
    git(repo, "config", "core.hooksPath", "")
    with pytest.raises(idh.InstallError, match="core.hooksPath is set"):
        idh.install(repo)
    assert_nothing_installed(repo)


@pytest.mark.parametrize("scope", ["global", "system"])
def test_install_prints_the_unset_command_of_the_scope_that_sets_core_hooks_path(tmp_path, monkeypatch, scope):
    """Scratch config files only: the user's own git configuration is never read or written."""
    repo = prepared_clone(tmp_path)
    for name in ("global", "system"):
        config = tmp_path / ("%s.cfg" % name)
        config.write_text("[core]\n\thooksPath = .githooks\n" if name == scope else "", encoding="utf-8")
        monkeypatch.setenv("GIT_CONFIG_%s" % name.upper(), str(config))
    monkeypatch.delenv("GIT_CONFIG_NOSYSTEM", raising=False)
    with pytest.raises(idh.InstallError, match="git config --%s --unset core.hooksPath" % scope):
        idh.install(repo)
    assert_nothing_installed(repo)


def test_install_refuses_a_hooks_path_that_no_git_config_command_unsets(tmp_path, monkeypatch):
    """A value given through the environment has the scope 'command'; there is no unset command to print."""
    repo = prepared_clone(tmp_path)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.hooksPath")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", ".githooks")
    with pytest.raises(idh.InstallError, match="set in the command configuration") as refusal:
        idh.install(repo)
    assert "--unset" not in str(refusal.value)
    assert_nothing_installed(repo)


def test_install_refuses_when_git_cannot_say_whether_core_hooks_path_is_set(tmp_path, monkeypatch):
    """A git too old for --show-scope answers 129; that must not be read as 'not set'."""
    repo = prepared_clone(tmp_path)
    fake = tmp_path / "bin" / "git"
    fake.parent.mkdir()
    fake.write_text(
        '#!/bin/sh\ncase "$*" in *--show-scope*) echo "error: unknown option" >&2; exit 129;; esac\n'
        'exec %s "$@"\n' % shlex.quote(shutil.which("git")),
        encoding="utf-8",
    )
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake.parent) + os.pathsep + os.environ["PATH"])
    with pytest.raises(idh.InstallError, match="cannot read core.hooksPath"):
        idh.install(repo)
    assert_nothing_installed(repo)


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


def test_a_push_is_refused_when_the_installed_copy_is_gone(tmp_path):
    """The stub fails closed: a missing copy stalls the push, it never lets it through."""
    repo = prepared_clone(tmp_path)
    idh.install(repo)
    shutil.rmtree(str(idh.copy_dir(repo)))
    commit(repo, {"notes.txt": "clean\n"}, "notes")
    proc = push(repo)
    assert proc.returncode != 0
    assert "privacy_check.py" in proc.stderr
    assert git(tmp_path / "remote.git", "for-each-ref") == ""
    idh.install(repo)
    assert push(repo).returncode == 0


@pytest.mark.parametrize("terms_lost", ["unset", "deleted"])
def test_a_push_is_refused_when_the_terms_file_is_unavailable(tmp_path, terms_lost):
    """The check exits 2 without a usable terms file; the stub must pass that status on, not map it to success."""
    repo = prepared_clone(tmp_path)
    idh.install(repo)
    commit(repo, {"notes.txt": "clean\n"}, "notes")
    if terms_lost == "unset":
        git(repo, "config", "--unset", "pe.privateTermsFile")
    else:
        (tmp_path / "terms.txt").unlink()
    proc = push(repo)
    assert proc.returncode != 0
    assert "privacy check: " in proc.stderr
    assert git(tmp_path / "remote.git", "for-each-ref") == ""


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
    lines = capsys.readouterr().out.splitlines()
    assert "installed %s" % (repo / ".git" / "hooks" / "pre-push") in lines
    assert "copied the checks to %s" % idh.copy_dir(repo) in lines


def test_main_refuses_a_foreign_pre_push(tmp_path, capsys):
    repo = prepared_clone(tmp_path)
    (repo / ".git" / "hooks" / "pre-push").write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    assert idh.main([str(repo)]) == 1
    captured = capsys.readouterr()
    assert "did not write" in captured.err
    assert captured.out == ""


def test_main_refuses_a_directory_outside_a_repository(tmp_path, capsys):
    outside = tmp_path / "plain"
    outside.mkdir()
    assert idh.main([str(outside)]) == 1
    assert capsys.readouterr().err.startswith("install_dev_hooks: ")


def test_main_reports_a_missing_git_as_a_refusal(tmp_path, monkeypatch, capsys):
    """With no git on PATH the answer is exit 1 and the reason, not a traceback."""
    repo = prepared_clone(tmp_path)
    nowhere = tmp_path / "empty-path"
    nowhere.mkdir()
    monkeypatch.setenv("PATH", str(nowhere))
    assert idh.main([str(repo)]) == 1
    assert "cannot run git" in capsys.readouterr().err
