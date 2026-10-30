"""Tests for tools/install_dev_hooks.py, with real pushes to a local bare remote."""
import json
import os
import shlex
import shutil
import stat
import subprocess
import sys
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


def set_hooks_path(where: str, repo: Path, tmp_path: Path, monkeypatch) -> Path:
    """Put core.hooksPath into one config file and return that file.

    Global and system configuration are scratch files in tmp_path, so the
    user's own git configuration is never read or written. ``included`` puts
    the value in a file that the global configuration pulls in.
    """
    scratch = {name: tmp_path / ("%s.cfg" % name) for name in ("global", "system", "included")}
    for path in scratch.values():
        path.write_text("", encoding="utf-8")
    scratch["global"].write_text("[include]\n\tpath = %s\n" % scratch["included"], encoding="utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(scratch["global"]))
    monkeypatch.setenv("GIT_CONFIG_SYSTEM", str(scratch["system"]))
    monkeypatch.delenv("GIT_CONFIG_NOSYSTEM", raising=False)
    holder = {**scratch, "local": repo / ".git" / "config"}[where]
    with holder.open("a", encoding="utf-8") as handle:
        handle.write("[core]\n\thooksPath = .githooks\n")
    return holder


@pytest.mark.parametrize("where", ["local", "global", "system", "included"])
def test_install_names_the_file_that_sets_core_hooks_path_and_prints_the_command_that_removes_it(
    tmp_path, monkeypatch, where
):
    """The printed command must work: a value from an included file survives `git config --global --unset`."""
    repo = prepared_clone(tmp_path)
    holder = set_hooks_path(where, repo, tmp_path, monkeypatch)
    with pytest.raises(idh.InstallError, match="core.hooksPath is set") as refusal:
        idh.install(repo)
    message = str(refusal.value)
    assert str(holder) in message
    assert_nothing_installed(repo)
    subprocess.run(shlex.split(message.split("with: ", 1)[1]), cwd=str(repo), check=True)
    assert idh.install(repo).exists()


def test_install_refuses_an_empty_core_hooks_path(tmp_path):
    """An empty value is still a value: git then runs no hook, and the stub would land in the working tree."""
    repo = prepared_clone(tmp_path)
    git(repo, "config", "core.hooksPath", "")
    with pytest.raises(idh.InstallError, match="core.hooksPath is set"):
        idh.install(repo)
    assert_nothing_installed(repo)


def test_install_refuses_a_hooks_path_that_no_file_holds(tmp_path, monkeypatch):
    """A value given through the environment has no file to edit, so no command is printed."""
    repo = prepared_clone(tmp_path)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.hooksPath")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", ".githooks")
    with pytest.raises(idh.InstallError, match=r"in the command configuration \(command line\)") as refusal:
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


def test_a_push_is_refused_when_python_is_not_on_the_path(tmp_path, monkeypatch):
    """The stub exits 127 when it cannot start python3; a guard that skips the check then would fail open."""
    repo = prepared_clone(tmp_path)
    idh.install(repo)
    commit(repo, {"notes.txt": "clean\n"}, "notes")
    only_git = tmp_path / "only-git"
    only_git.mkdir()
    (only_git / "git").symlink_to(shutil.which("git"))
    monkeypatch.setenv("PATH", str(only_git))
    proc = push(repo)
    assert proc.returncode != 0
    assert "python3" in proc.stderr
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


def test_main_refuses_a_directory_outside_a_repository(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("LC_ALL", "C")  # the reason below is git's own wording, in English
    outside = tmp_path / "plain"
    outside.mkdir()
    assert idh.main([str(outside)]) == 1
    assert "not a git repository" in capsys.readouterr().err


def test_installer_runs_as_a_script_in_isolated_mode(tmp_path):
    """`python3 -I` leaves the script's folder off sys.path; the installer must find its imports itself."""
    repo = prepared_clone(tmp_path)
    script = REPO_ROOT / "tools" / "install_dev_hooks.py"
    proc = subprocess.run([sys.executable, "-I", str(script), str(repo)],
                          cwd=str(tmp_path), capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.splitlines()[0] == "installed %s" % (repo / ".git" / "hooks" / "pre-push")


def test_main_reports_a_missing_git_as_a_refusal(tmp_path, monkeypatch, capsys):
    """With no git on PATH the answer is exit 1 and the reason, not a traceback."""
    repo = prepared_clone(tmp_path)
    nowhere = tmp_path / "empty-path"
    nowhere.mkdir()
    monkeypatch.setenv("PATH", str(nowhere))
    assert idh.main([str(repo)]) == 1
    assert "cannot run git" in capsys.readouterr().err
