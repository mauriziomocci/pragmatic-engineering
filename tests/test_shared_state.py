"""The record of what the worktrees share, for team-lead: the closed list, the pure comparison and derivations, the
reader in a real repository, and the commands.

The comparison through ``verify_delivery.py`` (exit 4) is tested in ``test_verify_delivery.py``; here the module is
imported, and its reader runs in a repository made for each test, as the current folder.
"""
import json
import os
import shutil
import socket
import sys
from pathlib import Path

import pytest

from support import REPO_ROOT, commit, git, init_repo, run_script

sys.path.insert(0, str(REPO_ROOT / "skills" / "team-lead"))
import shared_state  # noqa: E402

SCRIPT = REPO_ROOT / "skills" / "team-lead" / "shared_state.py"
SHA = "1" * 40
OTHER_SHA = "2" * 40


def record(items, team=("w",), integration="main", copied=()):
    return shared_state.Record(integration, frozenset(team), dict(items), frozenset(copied))


def now(items, admin_folders=()):
    return shared_state.Observation(dict(items), frozenset(admin_folders))


def ref(name):
    return ("ref", "refs/heads/" + name)


def changed(before, after):
    return [change.item for change in shared_state.differences(before, after)]


# --- the closed list, in the docstring and in the constants --------------------------------------------------------


def test_every_name_of_the_closed_list_is_in_the_docstring():
    doc = " ".join(shared_state.__doc__.split())
    names = (shared_state.VOLATILE + shared_state.NOT_VOLATILE + shared_state.ADMIN_COMPARED
             + shared_state.CONFIG_MAY_GAIN + shared_state.EXCLUDE_MAY_GAIN + shared_state.NEW_WORKTREE_ENTRIES)
    assert [name for name in names if "``%s``" % name not in doc] == []
    assert "``*%s``" % shared_state.LOCK in doc and "``%s``" % shared_state.HOST_BRANCH in doc
    assert "``-sync``" in doc and "zero or more digits" in doc


# --- differences: what may change, and what is compared ------------------------------------------------------------


def test_a_changed_value_is_listed_with_its_recorded_and_its_found_value():
    [change] = shared_state.differences(record({ref("main"): SHA}), now({ref("main"): OTHER_SHA}))
    assert json.loads(change.line()) == {"item": ["ref", "refs/heads/main"], "recorded": SHA, "found": OTHER_SHA}


def test_team_refs_absent_from_the_record_may_appear_and_move():
    found = {ref(name): SHA for name in ("w", "w-sync", "w-sync2", "worktree-agent-x")}
    assert changed(record({}), now(found)) == []


@pytest.mark.parametrize("name", ["w-sync3", "worktree-agent-old"])
def test_a_team_like_ref_in_the_record_stays_compared(name):
    assert changed(record({ref(name): SHA}), now({ref(name): OTHER_SHA})) == [ref(name)]


@pytest.mark.parametrize("name", ["wx", "w-syncx", "w-sync-1", "x-sync"])
def test_a_name_that_only_looks_like_a_team_ref_is_compared(name):
    assert changed(record({}), now({ref(name): SHA})) == [ref(name)]


def test_a_ref_outside_the_team_that_appears_or_disappears_is_listed():
    before = record({ref("gone"): SHA, ("ref", "refs/tags/v1"): SHA})
    after = now({ref("new"): SHA, ("ref", "refs/stash"): SHA})
    assert sorted(changed(before, after)) == sorted([ref("gone"), ("ref", "refs/tags/v1"), ref("new"),
                                                     ("ref", "refs/stash")])


def test_a_symbolic_target_counts_even_with_the_same_value():
    before = record({ref("main"): SHA})
    assert changed(before, now({ref("main"): SHA + " -> refs/heads/w-sync3"})) == [ref("main")]


def worktree(head=SHA, branch="refs/heads/main", prunable=False):
    return (head, branch, prunable)


@pytest.mark.parametrize("found", [worktree(branch=None), worktree(branch="refs/heads/w-sync2"),
                                   worktree(branch="refs/heads/worktree-agent-a")])
def test_a_new_worktree_detached_or_on_a_team_ref_may_appear(found):
    assert changed(record({}), now({("worktree", "/new"): found})) == []


@pytest.mark.parametrize("branch", ["main", "w-sync3", "worktree-agent-old"])
def test_a_new_worktree_on_a_branch_outside_the_team_is_listed(branch):
    """A recorded ``-sync`` or ``worktree-agent-`` branch is no team ref: a new worktree on it is a difference."""
    before = record({ref(branch): SHA})
    after = now({ref(branch): SHA, ("worktree", "/new"): worktree(branch="refs/heads/" + branch)})
    assert changed(before, after) == [("worktree", "/new")]


def test_a_recorded_worktree_that_moves_or_disappears_is_listed_unless_it_was_prunable():
    before = record({("worktree", "/a"): worktree(), ("worktree", "/b"): worktree(),
                     ("worktree", "/c"): worktree(prunable=True)})
    after = now({("worktree", "/a"): worktree(head=OTHER_SHA)})
    assert changed(before, after) == [("worktree", "/a"), ("worktree", "/b")]


def test_a_file_that_appears_changes_or_disappears_is_listed():
    before = record({("file", "hooks/a"): "sha256 1", ("file", "hooks/b"): "sha256 1"})
    after = now({("file", "hooks/a"): "sha256 2", ("file", "shallow"): "sha256 1"})
    assert changed(before, after) == [("file", "hooks/a"), ("file", "hooks/b"), ("file", "shallow")]


def test_the_files_of_a_recorded_admin_folder_go_only_with_the_folder():
    before = record({("file", "worktrees/x/gitdir"): "sha256 1", ("file", "worktrees/y/config.worktree"): "sha256 1",
                     ("file", "worktrees/y/gitdir"): "sha256 1"})
    after = now({("file", "worktrees/y/gitdir"): "sha256 1"}, admin_folders=("y",))
    assert changed(before, after) == [("file", "worktrees/y/config.worktree")]


def config(text):
    name, _, value = text.partition("=")
    return ("config", name, shared_state.digest(value))


def test_config_may_gain_only_the_worktree_extension():
    before = record({config("core.bare=false"): 1})
    after = now({config("core.bare=false"): 1, config("extensions.worktreeconfig=true"): 1,
                 config("merge.x.driver=spy"): 1})
    assert changed(before, after) == [config("merge.x.driver=spy")]
    assert changed(before, now({})) == [config("core.bare=false")]


def worktree_config(text, folder="worker"):
    return ("worktree-config", folder) + config(text)[1:]


def test_a_new_worktree_config_may_hold_the_host_entries_and_the_copied_ones():
    copied = {config("x.y=z")[1:]}
    allowed = {worktree_config("core.untrackedcache=true"): 1, worktree_config("core.longpaths=true"): 1,
               worktree_config("x.y=z"): 1}
    assert changed(record({}, copied=copied), now(allowed)) == []
    spy = worktree_config("filter.spy.clean=spy")
    assert changed(record({}, copied=copied), now({**allowed, spy: 1})) == [spy]


def test_exclude_may_gain_only_lines_under_a_claude_folder():
    before = record({("exclude", "*.log"): 1})
    after = now({("exclude", "*.log"): 1, ("exclude", ".claude/worktrees/"): 1, ("exclude", "**/.claude/x"): 1,
                 ("exclude", "build/"): 1})
    assert changed(before, after) == [("exclude", "build/")]


def test_config_values_are_kept_as_digests_only():
    assert "s3cret" not in shared_state.digest("s3cret") and shared_state.digest("a") != shared_state.digest("b")


# --- derivations: no read of git ------------------------------------------------------------------------------------


def test_team_adds_names_and_refuses_the_integration_and_a_recorded_branch():
    base = record({ref("main"): SHA, ref("old"): SHA})
    assert shared_state.with_team(base, ["w2"]).team == {"w", "w2"}
    for name in ("main", "old"):
        with pytest.raises(shared_state.RecordError, match=name):
            shared_state.with_team(base, [name])


def test_merged_moves_the_integration_and_the_head_of_the_worktrees_on_it():
    base = record({ref("main"): SHA, ("worktree", "/c"): worktree(), ("worktree", "/d"): worktree(branch=None)})
    moved = shared_state.merged(base, OTHER_SHA)
    assert moved.items[ref("main")] == OTHER_SHA
    assert moved.items[("worktree", "/c")] == worktree(head=OTHER_SHA)
    assert moved.items[("worktree", "/d")] == worktree(branch=None)


@pytest.mark.parametrize("value", ["main", SHA[:12], "A" * 40])
def test_merged_takes_only_a_full_commit_id(value):
    with pytest.raises(shared_state.RecordError, match="full commit id"):
        shared_state.merged(record({ref("main"): SHA}), value)


def test_accept_records_the_printed_found_value_and_reads_nothing():
    """The item changed again after the listing: the value the user saw is recorded, so the new change still shows."""
    base = record({ref("main"): SHA, ref("gone"): SHA})
    printed = [change.line() for change in shared_state.differences(base, now({ref("main"): OTHER_SHA}))]
    accepted = shared_state.accepted(base, printed)
    assert ref("gone") not in accepted.items and accepted.items[ref("main")] == OTHER_SHA
    assert changed(accepted, now({ref("main"): "3" * 40})) == [ref("main")]


def test_accept_brings_a_worktree_back_as_it_was_printed():
    printed = shared_state.differences(record({}), now({("worktree", "/new"): worktree()}))[0].line()
    assert shared_state.accepted(record({}), [printed]).items[("worktree", "/new")] == worktree()


@pytest.mark.parametrize("line", ["", "[1]", '{"item": ["nothing", "x"], "found": 1}', '{"item": [], "found": 1}',
                                  '{"found": 1}'])
def test_accept_refuses_what_exit_4_did_not_print(line):
    with pytest.raises(shared_state.RecordError, match="not an item"):
        shared_state.accepted(record({}), [line])


# --- the reader, in a real repository -------------------------------------------------------------------------------


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A repository on ``main`` with one commit, as the current folder, with a home folder of its own."""
    path = init_repo(tmp_path / "repo")
    commit(path, {"a.py": "a = 1\n"}, "base")
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.chdir(path)
    return path


def common(repo: Path) -> Path:
    return Path(git(repo, "rev-parse", "--path-format=absolute", "--git-common-dir").strip())


def test_refs_are_read_by_name_with_their_symbolic_target(repo):
    git(repo, "branch", "b")
    git(repo, "symbolic-ref", "refs/heads/s", "refs/heads/b")
    tip = git(repo, "rev-parse", "HEAD").strip()
    items = shared_state.observe().items
    assert items[ref("b")] == tip and items[ref("s")] == tip + " -> refs/heads/b"


def ignores_case(folder: Path) -> bool:
    (folder / "Probe").write_text("", encoding="utf-8")
    return (folder / "pROBE").exists()


def test_a_loose_ref_that_differs_only_by_case_is_what_the_packed_one_reads(repo, tmp_path):
    """``for-each-ref`` still shows the packed ``main``; the lookup reads the loose file."""
    if not ignores_case(tmp_path):
        pytest.skip("the file system tells letter cases apart, so a loose Main never reads as main")
    old = git(repo, "rev-parse", "HEAD").strip()
    git(repo, "pack-refs", "--all")
    new = commit(repo, {"b.py": "b = 1\n"}, "next")
    git(repo, "update-ref", "refs/heads/main", old)
    git(repo, "pack-refs", "--all")
    (common(repo) / "refs" / "heads" / "Main").write_text(new + "\n", encoding="utf-8")
    items = shared_state.observe().items
    assert items[ref("main")] == new and items[ref("Main")] == new


def test_worktrees_are_read_with_head_branch_and_prunable(repo, tmp_path):
    git(repo, "worktree", "add", "-q", "--detach", str(tmp_path / "gone"))
    git(repo, "worktree", "add", "-q", "-b", "b", str(tmp_path / "kept"))
    tip = git(repo, "rev-parse", "HEAD").strip()
    shutil.rmtree(str(tmp_path / "gone"))
    by_name = {Path(key[1]).name: value for key, value in shared_state.observe().items.items() if key[0] == "worktree"}
    assert by_name["repo"] == (tip, "refs/heads/main", False)
    assert by_name["kept"] == (tip, "refs/heads/b", False)
    assert by_name["gone"][1:] == (None, True)


def test_the_common_folder_is_read_without_its_volatile_part(repo):
    folder = common(repo)
    (folder / "objects" / "info" / "alternates").write_text("/elsewhere\n", encoding="utf-8")
    (folder / "info" / "attributes").write_text("* -text\n", encoding="utf-8")
    (folder / "config.lock").write_text("x", encoding="utf-8")
    (folder / "FETCH_HEAD").write_text("x", encoding="utf-8")
    files = {key[1] for key in shared_state.observe().items if key[0] == "file" and not os.path.isabs(key[1])}
    assert {"objects/info/alternates", "info/attributes", "description"} <= files
    volatile = ("objects/", "refs/", "logs/", "index", "HEAD", "COMMIT_EDITMSG", "config", "info/exclude",
                "config.lock", "FETCH_HEAD")
    assert [path for path in files if path.startswith(volatile)] == ["objects/info/alternates"]


@pytest.mark.skipif(sys.platform == "win32", reason="a symlink needs a privilege on Windows")
def test_a_symlink_is_read_by_its_target(repo):
    hook = common(repo) / "hooks" / "post-checkout"
    hook.symlink_to("a.sh")
    assert shared_state.observe().items[("file", "hooks/post-checkout")] == "symlink a.sh"


@pytest.mark.skipif(not hasattr(socket, "AF_UNIX") or sys.platform == "win32",
                    reason="no Unix socket file here: on Windows one is a reparse point, not tried")
def test_a_socket_is_read_by_its_kind(repo, monkeypatch):
    monkeypatch.chdir(common(repo))  # a relative name: a temporary folder's full path can pass the length of one
    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind("s")
        monkeypatch.chdir(repo)
        assert shared_state.observe().items[("file", "s")] == "socket"


def test_config_entries_are_read_by_name_and_digest_and_no_value_is_kept(repo):
    git(repo, "config", "remote.origin.url", "https://user:s3cret@example.com/r.git")
    items = shared_state.observe().items
    assert items[config("remote.origin.url=https://user:s3cret@example.com/r.git")] == 1
    assert "s3cret" not in json.dumps([list(key) for key in items])


def test_exclude_is_read_by_lines(repo):
    (common(repo) / "info" / "exclude").write_text("*.log\n.claude/worktrees/\n*.log\n", encoding="utf-8")
    items = shared_state.observe().items
    assert items[("exclude", "*.log")] == 2 and items[("exclude", ".claude/worktrees/")] == 1


def test_admin_folders_give_their_three_files_or_else_the_entries_of_their_config(repo, tmp_path):
    git(repo, "config", "extensions.worktreeConfig", "true")
    git(repo, "worktree", "add", "-q", "--detach", str(tmp_path / "old"))
    git(repo, "worktree", "add", "-q", "--detach", str(tmp_path / "new"))
    git(tmp_path / "old", "config", "--worktree", "x.old", "1")
    git(tmp_path / "new", "config", "--worktree", "x.new", "2")
    first = shared_state.observe()
    assert first.admin_folders == {"old", "new"}
    assert {key[1] for key in first.items if key[0] == "file" and key[1].startswith("worktrees/")} == {
        "worktrees/%s/%s" % (folder, name) for folder in ("old", "new") for name in ("commondir", "gitdir",
                                                                                        "config.worktree")}
    later = shared_state.observe(record({key: value for key, value in first.items.items()
                                         if "worktrees/new/" not in str(key)}))
    assert [key for key in later.items if key[0] == "worktree-config"] == [worktree_config("x.new=2", "new")]
    assert ("file", "worktrees/new/gitdir") not in later.items and ("file", "worktrees/old/gitdir") in later.items


def outside(items):
    """The files read outside the common folder, by their real path."""
    return {Path(key[1]).resolve() for key in items if key[0] == "file" and os.path.isabs(key[1])}


def test_configuration_files_are_read_present_or_absent(repo, tmp_path):
    git(repo, "config", "include.path", "../extra.cfg")
    git(repo, "config", "includeIf.gitdir:/nowhere/.path", str(tmp_path / "never.cfg"))
    named = [repo / "extra.cfg", tmp_path / "never.cfg", Path(os.environ["HOME"]) / ".gitconfig"]
    assert {path.resolve() for path in named} & outside(shared_state.observe().items) == set()
    for path in named:
        path.write_text("[x]\n", encoding="utf-8")
    global_config = Path(os.environ["GIT_CONFIG_GLOBAL"])
    assert {path.resolve() for path in named + [global_config]} <= outside(shared_state.observe().items)


def test_a_hooks_folder_outside_every_worktree_is_read_and_one_inside_is_not(repo, tmp_path):
    hooks = tmp_path / "hooks"
    hooks.mkdir()
    (hooks / "pre-commit").write_text("#!/bin/sh\n", encoding="utf-8")
    (repo / ".husky").mkdir()
    (repo / ".husky" / "pre-commit").write_text("#!/bin/sh\n", encoding="utf-8")
    git(repo, "config", "core.hooksPath", str(hooks))
    assert (hooks / "pre-commit").resolve() in outside(shared_state.observe().items)
    git(repo, "config", "core.hooksPath", ".husky")
    assert [path for path in outside(shared_state.observe().items) if "husky" in str(path)] == []


# --- the commands ---------------------------------------------------------------------------------------------------


def run(repo: Path, *args: str):
    return run_script(SCRIPT, list(args), repo, env={"HOME": os.environ["HOME"], "USERPROFILE": os.environ["HOME"]})


def load(repo: Path) -> "shared_state.Record":
    return shared_state.load(repo / ".pe" / "shared-state.json")


def usage_error(proc, mention: str) -> None:
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "shared_state:" in proc.stderr and mention in proc.stderr, proc.stderr


def test_start_records_and_lists_the_worktrees_outside_the_team(repo, tmp_path):
    git(repo, "worktree", "add", "-q", "--detach", str(tmp_path / "loose"))
    git(repo, "worktree", "add", "-q", "-b", "other", str(tmp_path / "busy"))
    git(repo, "worktree", "add", "-q", "--detach", str(tmp_path / "gone"))
    (tmp_path / "gone" / ".git").unlink()
    proc = run(repo, "start", "--integration", "main", "--team", "w1", "w2")
    assert proc.returncode == 0, proc.stderr
    lines = proc.stdout.splitlines()
    assert any(line.endswith("repo main") for line in lines) and any(line.endswith("busy other") for line in lines)
    assert any(line.endswith("loose detached") for line in lines)
    assert any(line.endswith("gone detached prunable") for line in lines)
    saved = load(repo)
    assert saved.integration == "main" and saved.team == {"w1", "w2"} and ref("other") in saved.items
    assert (repo / ".pe" / ".gitignore").read_text(encoding="utf-8") == "*\n"
    assert git(repo, "status", "--porcelain").strip() == ""


@pytest.mark.parametrize("team", ["main", "other"])
def test_start_refuses_a_team_name_that_is_the_integration_or_a_branch_already_there(repo, team):
    git(repo, "branch", "other")
    usage_error(run(repo, "start", "--integration", "main", "--team", "w1", team), team)
    assert not (repo / ".pe" / "shared-state.json").exists()


def test_start_refuses_an_integration_that_is_no_branch(repo):
    usage_error(run(repo, "start", "--integration", "nope", "--team", "w1"), "nope")


def test_team_adds_a_new_name_and_refuses_a_recorded_branch_or_the_integration(repo):
    git(repo, "branch", "other")
    assert run(repo, "start", "--integration", "main", "--team", "w1").returncode == 0
    assert run(repo, "team", "w2").returncode == 0
    assert load(repo).team == {"w1", "w2"}
    for name in ("other", "main"):
        usage_error(run(repo, "team", name), name)
    assert load(repo).team == {"w1", "w2"}


def test_merged_records_the_new_integration_tip(repo):
    assert run(repo, "start", "--integration", "main", "--team", "w1").returncode == 0
    tip = commit(repo, {"b.py": "b = 1\n"}, "integrated")
    assert run(repo, "merged", tip).returncode == 0
    assert load(repo).items[ref("main")] == tip
    usage_error(run(repo, "merged", "main"), "full commit id")


def test_accept_records_the_printed_item(repo):
    assert run(repo, "start", "--integration", "main", "--team", "w1").returncode == 0
    line = json.dumps({"item": ["ref", "refs/tags/v1"], "recorded": None, "found": SHA})
    assert run(repo, "accept", line).returncode == 0
    assert load(repo).items[("ref", "refs/tags/v1")] == SHA
    usage_error(run(repo, "accept", "refs/tags/v1"), "not an item")


@pytest.mark.parametrize("command", [["team", "w2"], ["merged", SHA], ["accept", "{}"]])
def test_without_a_record_a_command_says_how_a_run_begins_and_what_to_do_inside_one(repo, command):
    proc = run(repo, *command)
    usage_error(proc, "no record at")
    assert "`shared_state.py start` begins a new run; in a run, stop and go to the user" in proc.stderr
