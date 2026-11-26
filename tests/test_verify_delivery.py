"""The delivery check of team-lead against git: every case builds its own repository and its own worker worktree.

The script runs from the coordinator's checkout (``repo``, on the branch ``integration``) and reads the worker's
branch ``w``, checked out in ``worktree``. Every case starts from a record of the shared state taken by
``shared_state.py start`` before the worker exists, with ``w`` as the team, a branch ``shared`` and a tag ``v1``
outside it, and a home folder of its own. Every path inside a command line is written with ``as_posix()``: the
suite also runs on Windows, where a backslash is an escape for the command splitter.
"""
import json
import os
import shlex
import shutil
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

import pytest

from support import REPO_ROOT, commit, common, git, init_repo, run_script, submodule_in

SCRIPT = REPO_ROOT / "skills" / "team-lead" / "verify_delivery.py"
SHARED_STATE = REPO_ROOT / "skills" / "team-lead" / "shared_state.py"
BRIEF = "# Brief\n\nOWNED: src/a/*\nOWNED: tests/test_a*.py\nTESTS: tests/test_a*.py\n"
# A test is a script that exits with a non-zero code when its assertion falls, run from the root of a worktree.
FEATURE_TEST = "import sys\n\nsys.path.insert(0, 'src/a')\nimport feature\n\nassert feature.VALUE == 1\n"
CHANGED = "verify_delivery: shared state changed: "


@dataclass
class Delivery:
    """The coordinator's checkout, the worker's worktree on ``w``, the brief, and the home folder of both scripts."""

    repo: Path
    worktree: Path
    brief: Path
    home: Path

    def tip(self) -> str:
        return git(self.worktree, "rev-parse", "HEAD").strip()

    def work(self, files: Dict[str, str], message: str = "work") -> str:
        return commit(self.worktree, files, message)

    def integrate(self, files: Dict[str, str], message: str = "integration moves") -> str:
        """A commit on the integration branch, recorded with ``merged`` as the coordinator does after a merge."""
        sha = commit(self.repo, files, message)
        self.shared("merged", sha)
        return sha

    def worktree_entries(self) -> int:
        return len(git(self.repo, "worktree", "list").splitlines())

    def merge_keeping_own_side(self, path: str) -> str:
        """Merge ``integration`` into ``w`` and, on the conflict on ``path``, keep the worker's side."""
        subprocess.run(["git", "merge", "--no-edit", "integration"], cwd=str(self.worktree), capture_output=True)
        git(self.worktree, "checkout", "--ours", "--", path)
        git(self.worktree, "add", path)
        git(self.worktree, "commit", "-q", "--no-edit")
        return self.tip()

    def integrate_a_resolved_merge(self) -> str:
        """Another worker's delivery lands on ``integration`` as a merge that keeps the integration's side."""
        self.shared("team", "other")
        git(self.repo, "branch", "other", "integration")
        git(self.repo, "checkout", "-q", "other")
        commit(self.repo, {"src/b/b.py": "b = 'other'\n"}, "other worker")
        git(self.repo, "checkout", "-q", "integration")
        commit(self.repo, {"src/b/b.py": "b = 'integration'\n"}, "integration moves")
        subprocess.run(["git", "merge", "--no-edit", "other"], cwd=str(self.repo), capture_output=True)
        git(self.repo, "checkout", "--ours", "--", "src/b/b.py")
        git(self.repo, "add", "src/b/b.py")
        git(self.repo, "commit", "-q", "--no-edit")
        merge = git(self.repo, "rev-parse", "HEAD").strip()
        self.shared("merged", merge)
        return merge

    def red_command(self) -> str:
        return shlex.join([Path(sys.executable).as_posix(), "tests/test_a.py"])

    def env(self) -> Dict[str, str]:
        return {"HOME": str(self.home), "USERPROFILE": str(self.home)}

    def run(self, extra: Iterable[str] = (), replace: Optional[Dict[str, Optional[str]]] = None):
        """Run the script with the usual arguments; ``replace`` swaps a value, or drops the option with ``None``."""
        arguments: Dict[str, Optional[str]] = {
            "--integration": "integration",
            "--branch": "w",
            "--tip": self.tip(),
            "--worktree": self.worktree.as_posix(),
            "--brief": self.brief.as_posix(),
        }
        arguments.update(replace or {})
        flat = [word for pair in arguments.items() if pair[1] is not None for word in pair]
        return run_script(SCRIPT, [*flat, *extra], self.repo, env=self.env())

    def shared(self, *args: str) -> None:
        proc = run_script(SHARED_STATE, list(args), self.repo, env=self.env())
        assert proc.returncode == 0, proc.stderr

    def accept_listed(self) -> None:
        """What the test changed in the shared state on purpose is accepted as the user would, after an exit 4."""
        proc = self.run()
        assert proc.returncode == 4, proc.stdout + proc.stderr
        self.shared("accept", *listed(proc))


def make_delivery(tmp_path: Path, before_start: Callable[[Path], None] = lambda repo: None,
                  init: Iterable[str] = ()) -> Delivery:
    """The one way a case gets its record: ``before_start`` shapes the repository before it is recorded."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main", *init)
    git(repo, "checkout", "-q", "-b", "integration")
    commit(repo, {"src/a/a.py": "a = 1\n", "src/b/b.py": "b = 1\n"}, "base")
    git(repo, "branch", "shared")
    git(repo, "tag", "v1")
    before_start(repo)
    home = tmp_path / "home"
    home.mkdir()
    brief = tmp_path / "brief.md"
    brief.write_text(BRIEF, encoding="utf-8")
    delivery = Delivery(repo, tmp_path / "worker", brief, home)
    delivery.shared("start", "--integration", "integration", "--team", "w")
    git(repo, "worktree", "add", "-q", "-b", "w", str(delivery.worktree), "integration")
    return delivery


@pytest.fixture
def delivery(tmp_path):
    return make_delivery(tmp_path)


def listed(proc) -> List[str]:
    """The lines of the changes that an exit 4 printed, each whole, as ``accept`` takes it."""
    return [line for line in proc.stderr.splitlines() if line.startswith(CHANGED)]


def printed(line: str) -> dict:
    return json.loads(line[len(CHANGED):])


def changed_items(proc) -> List[List[Optional[str]]]:
    assert proc.returncode == 4, proc.stdout + proc.stderr
    assert "it goes to the user, never to the worker" in proc.stderr, proc.stderr
    return [printed(line)["item"] for line in listed(proc)]


def refused(proc, reason: str) -> None:
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert reason in proc.stderr, proc.stderr


def usage_error(proc, mention: str = "") -> None:
    """Exit 2 is also what Python answers for a script it cannot find: the script's own prefix tells them apart."""
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "verify_delivery:" in proc.stderr and mention in proc.stderr, proc.stderr


# --- exit 0: accepted ------------------------------------------------------------------------------------------


def test_a_clean_delivery_inside_its_area_exits_0(delivery):
    delivery.work({"src/a/new.py": "x = 1\n"})
    proc = delivery.run()
    assert proc.returncode == 0, proc.stderr


def test_a_path_that_git_would_quote_is_matched_as_it_is(delivery):
    """Without ``-z`` git prints a non-ASCII path quoted and escaped, and no glob matches it."""
    delivery.work({"src/a/caff\u00e8.py": "x = 1\n"})
    proc = delivery.run()
    assert proc.returncode == 0, proc.stderr


def test_a_tag_named_like_the_branch_does_not_stand_in_for_it(delivery):
    """Git reads ``w`` as the tag before the branch: the branch is always read as ``refs/heads/w``."""
    declared = delivery.work({"src/a/new.py": "x = 1\n"})
    delivery.work({"src/a/newer.py": "y = 1\n"})
    git(delivery.repo, "tag", "w", declared)
    delivery.accept_listed()
    refused(delivery.run(replace={"--tip": declared}), "not to the declared tip")


@pytest.mark.parametrize("kind", ["tag", "ref-under-refs"])
def test_a_tag_or_a_ref_named_like_the_integration_is_ignored(delivery, kind):
    """A tag ``integration``, or ``refs/integration``, at the delivery tip would empty the diff if git read it."""
    delivery.work({"src/b/stray.py": "s = 1\n"})
    if kind == "tag":
        git(delivery.repo, "tag", "integration", delivery.tip())
    else:
        git(delivery.repo, "update-ref", "refs/integration", delivery.tip())
    delivery.accept_listed()
    refused(delivery.run(), "outside the OWNED lines")


@pytest.mark.parametrize("option", ["--reviewed", "--tip"])
@pytest.mark.parametrize("value", ["w", "refs/heads/w", ""], ids=["branch", "full-ref", "empty"])
def test_the_tip_and_the_reviewed_tip_take_only_a_full_commit_id(delivery, option, value):
    """A branch is what the worker moves: ``--reviewed w`` would read the new tip and find nothing unread."""
    delivery.work({"src/a/new.py": "x = 1\n"})
    usage_error(delivery.run(replace={option: value}) if option == "--tip" else delivery.run((option, value)),
                "full commit id")


def test_a_tip_behind_the_reviewed_tip_exits_3(delivery):
    """The worker resets its branch below the commit that fixed a finding and declares the older tip."""
    older = delivery.work({"src/a/new.py": "x = 1\n"})
    reviewed = delivery.work({"src/a/fix.py": "f = 1\n"})
    git(delivery.worktree, "reset", "-q", "--hard", older)
    proc = delivery.run(("--reviewed", reviewed))
    assert proc.returncode == 3 and older in proc.stderr and "does not descend" in proc.stderr, proc.stderr


@pytest.mark.parametrize("spelling", ["full-ref", "sha"])
def test_a_full_ref_or_a_sha_still_names_the_integration_when_a_tag_shadows_it(delivery, spelling):
    delivery.work({"src/a/new.py": "x = 1\n"})
    git(delivery.repo, "tag", "integration", delivery.tip())
    delivery.accept_listed()
    integration = "refs/heads/integration" if spelling == "full-ref" else git(delivery.repo, "rev-parse",
                                                                              "refs/heads/integration").strip()
    proc = delivery.run(replace={"--integration": integration})
    assert proc.returncode == 0, proc.stderr


def test_a_run_without_red_leaves_the_index_of_the_worker_as_it_was(delivery):
    """``git status`` refreshes the index of the worktree it reads unless it is told not to take optional locks."""
    delivery.work({"src/a/new.py": "x = 1\n"})
    index = Path(git(delivery.worktree, "rev-parse", "--absolute-git-dir").strip()) / "index"
    os.utime(str(delivery.worktree / "src/a/new.py"), (1_000_000_000, 1_000_000_000))  # stale stat data, same content
    before = index.read_bytes()
    assert delivery.run().returncode == 0
    assert index.read_bytes() == before


def test_a_clean_sync_merge_exits_0(delivery):
    delivery.work({"src/a/new.py": "x = 1\n"})
    delivery.integrate({"src/b/more.py": "m = 1\n"})
    git(delivery.worktree, "merge", "-q", "--no-edit", "integration")
    assert git(delivery.repo, "rev-list", "--merges", "--count", "w").strip() == "1"
    proc = delivery.run()
    assert proc.returncode == 0, proc.stderr


# --- exit 1: refused, each with its reason -----------------------------------------------------------------------


def test_a_delivery_the_integration_has_overtaken_is_judged_on_its_own_changes(delivery):
    """Another worker's file landed on ``integration`` since this branch left it; that file is not this delivery's."""
    delivery.work({"src/a/new.py": "x = 1\n"})
    delivery.integrate({"src/b/other.py": "o = 1\n"})
    proc = delivery.run()
    assert proc.returncode == 0, proc.stderr


def test_an_overtaken_delivery_with_its_red_is_judged_on_its_own_test_files(delivery):
    delivery.work({"src/a/feature.py": "VALUE = 1\n", "tests/test_a.py": FEATURE_TEST})
    delivery.integrate({"src/b/other.py": "o = 1\n"})
    proc = delivery.run(("--red", delivery.red_command()))
    assert proc.returncode == 0, proc.stderr


def test_a_tip_other_than_the_declared_one_exits_1(delivery):
    declared = delivery.work({"src/a/new.py": "x = 1\n"})
    delivery.work({"src/a/newer.py": "y = 1\n"})
    refused(delivery.run(replace={"--tip": declared}), "not to the declared tip")


def test_a_file_outside_the_owned_lines_exits_1(delivery):
    """Counted on the whole diff from ``integration``: a later commit inside the area does not hide an earlier one."""
    delivery.work({"src/b/stray.py": "s = 1\n"}, "outside")
    delivery.work({"src/a/new.py": "x = 1\n"}, "inside")
    proc = delivery.run()
    refused(proc, "outside the OWNED lines")
    assert "src/b/stray.py" in proc.stderr and "src/a/new.py" not in proc.stderr


def test_a_file_moved_in_from_another_area_exits_1(delivery):
    """Without ``--no-renames`` the move names only its destination, inside the area, and would pass."""
    git(delivery.worktree, "mv", "src/b/b.py", "src/a/b.py")
    git(delivery.worktree, "commit", "-q", "-m", "move")
    proc = delivery.run()
    refused(proc, "outside the OWNED lines")
    assert "src/b/b.py" in proc.stderr


@pytest.mark.parametrize("dirt", ["tracked", "untracked"])
def test_a_dirty_worktree_exits_1(delivery, dirt):
    """``status.showUntrackedFiles=no`` hides an untracked file from ``--porcelain`` unless the script asks for all."""
    git(delivery.repo, "config", "status.showUntrackedFiles", "no")
    delivery.accept_listed()
    delivery.work({"src/a/new.py": "x = 1\n"})
    if dirt == "tracked":
        (delivery.worktree / "src/a/a.py").write_text("a = 2\n", encoding="utf-8")
    else:
        (delivery.worktree / "src/a/left.py").write_text("l = 1\n", encoding="utf-8")
    refused(delivery.run(), "worktree is not clean")


def write_pe_folder(delivery: Delivery, with_gitignore: bool) -> None:
    folder = delivery.worktree / ".pe"
    folder.mkdir()
    (folder / "delivery.md").write_text("STATUS: COMPLETE\n", encoding="utf-8")
    if with_gitignore:
        (folder / ".gitignore").write_text("*\n", encoding="utf-8")


def test_a_pe_folder_without_its_gitignore_exits_1(delivery):
    delivery.work({"src/a/new.py": "x = 1\n"})
    write_pe_folder(delivery, with_gitignore=False)
    refused(delivery.run(), "worktree is not clean")


def test_a_pe_folder_with_its_gitignore_does_not_count(delivery):
    delivery.work({"src/a/new.py": "x = 1\n"})
    write_pe_folder(delivery, with_gitignore=True)
    proc = delivery.run()
    assert proc.returncode == 0, proc.stderr


# --- exit 3: a merge that needs the review -------------------------------------------------------------------------


def conflicting_resolution(delivery: Delivery) -> str:
    """The worker and the integration change ``a.py`` differently; the merge keeps the worker's side."""
    delivery.work({"src/a/a.py": "a = 'worker'\n"})
    delivery.integrate({"src/a/a.py": "a = 'integration'\n"})
    return delivery.merge_keeping_own_side("src/a/a.py")


def test_a_merge_that_keeps_one_side_exits_3_before_review_and_0_after(delivery):
    tip = conflicting_resolution(delivery)
    assert delivery.run().returncode == 3
    assert delivery.run(("--reviewed", tip)).returncode == 0


def test_a_resolution_after_the_reviewed_tip_exits_3(delivery):
    reviewed = conflicting_resolution(delivery)
    delivery.integrate({"src/a/a.py": "a = 'integration again'\n"}, "integration moves again")
    later = delivery.merge_keeping_own_side("src/a/a.py")
    assert delivery.run(("--reviewed", reviewed)).returncode == 3
    assert delivery.run(("--reviewed", later)).returncode == 0


def test_an_ordinary_commit_after_the_reviewed_tip_exits_3_and_is_listed(delivery):
    """After the review, what the reviewer did not read is any commit, not only a merge."""
    reviewed = delivery.work({"src/a/new.py": "x = 1\n"})
    later = delivery.work({"src/a/more.py": "y = 1\n"})
    proc = delivery.run(("--reviewed", reviewed))
    assert proc.returncode == 3 and later in proc.stderr, proc.stderr


def test_the_reviewed_tip_itself_and_a_clean_sync_after_it_exit_0(delivery):
    reviewed = delivery.work({"src/a/new.py": "x = 1\n"})
    assert delivery.run(("--reviewed", reviewed)).returncode == 0
    delivery.integrate({"src/b/more.py": "m = 1\n"})
    git(delivery.worktree, "merge", "-q", "--no-edit", "integration")
    assert delivery.run(("--reviewed", reviewed)).returncode == 0


def test_without_reviewed_ordinary_commits_do_not_ask_for_a_review(delivery):
    delivery.work({"src/a/new.py": "x = 1\n"})
    delivery.work({"src/a/more.py": "y = 1\n"})
    assert delivery.run().returncode == 0


def test_a_reviewed_merge_already_in_the_integration_is_not_flagged_again(delivery):
    """Another worker's resolution, merged into ``integration`` before this delivery synced, was read by its own review."""
    reviewed = delivery.work({"src/a/new.py": "x = 1\n"})
    delivery.integrate_a_resolved_merge()
    git(delivery.worktree, "merge", "-q", "--no-edit", "integration")
    for extra in ((), ("--reviewed", reviewed)):
        proc = delivery.run(extra)
        assert proc.returncode == 0, proc.stderr


def test_a_refusal_wins_over_a_review_request(delivery):
    delivery.work({"src/b/stray.py": "s = 1\n"})
    conflicting_resolution(delivery)
    refused(delivery.run(), "outside the OWNED lines")


# --- exit 2: usage -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "replace",
    [
        {"--tip": None},
        {"--brief": "no-such-brief.md"},
        {"--integration": "no-such-revision"},
        {"--integration": "-x"},
        {"--tip": "-x"},
        {"--worktree": "no-such-folder"},
    ],
    ids=["missing-argument", "brief-that-is-not-a-file", "revision-that-is-no-commit", "integration-with-a-dash",
         "tip-with-a-dash", "worktree-that-is-not-a-folder"],
)
def test_usage_errors_exit_2(delivery, replace):
    delivery.work({"src/a/new.py": "x = 1\n"})
    usage_error(delivery.run(replace=replace))


@pytest.mark.parametrize(
    "option, value",
    [("--branch", "w~1"), ("--integration", "integration~0"), ("--reviewed", "integration^{commit}"),
     ("--tip", "w~0"), ("--branch", "w..integration"), ("--integration", "HEAD")],
)
def test_a_name_that_is_not_a_plain_branch_name_exits_2(delivery, option, value):
    """Revision syntax is not a branch name: ``w~1`` would be the base, and the declared tip could be made to match."""
    delivery.work({"src/b/stray.py": "s = 1\n"})
    replace = {option: value}
    if option == "--branch":
        replace["--tip"] = git(delivery.repo, "rev-parse", "integration").strip()
    usage_error(delivery.run(replace=replace))


def test_a_tag_spelled_like_a_full_branch_ref_is_no_branch(delivery):
    """Git would find ``refs/tags/refs/heads/ghost`` for the name ``refs/heads/ghost``; no branch is called ``ghost``."""
    delivery.work({"src/a/new.py": "x = 1\n"})
    git(delivery.repo, "tag", "refs/heads/ghost", delivery.tip())
    usage_error(delivery.run(replace={"--integration": "ghost"}), "not a branch")


def test_an_abbreviated_sha_is_no_commit_id(delivery):
    tip = delivery.work({"src/a/new.py": "x = 1\n"})
    usage_error(delivery.run(replace={"--tip": tip[:10]}))


def test_the_refs_heads_prefix_of_a_branch_is_optional(delivery):
    delivery.work({"src/a/new.py": "x = 1\n"})
    proc = delivery.run(replace={"--branch": "refs/heads/w", "--integration": "refs/heads/integration"})
    assert proc.returncode == 0, proc.stderr


def test_a_replaced_commit_is_read_as_it_is(delivery):
    """``git replace`` changes what git reads for a sha; the script reads the commits themselves."""
    delivery.work({"src/b/stray.py": "s = 1\n"})
    tip = delivery.tip()
    clean = git(delivery.repo, "commit-tree", "-p", "integration", "-m", "clean",
                git(delivery.repo, "rev-parse", "integration^{tree}").strip()).strip()
    git(delivery.repo, "replace", tip, clean)
    delivery.accept_listed()
    refused(delivery.run(), "outside the OWNED lines")


def test_a_brief_without_owned_lines_exits_2(delivery):
    delivery.work({"src/a/new.py": "x = 1\n"})
    delivery.brief.write_text("# Brief\n\nTESTS: tests/test_a*.py\n", encoding="utf-8")
    usage_error(delivery.run(), "OWNED:")


def test_a_reviewed_revision_that_is_no_commit_exits_2(delivery):
    delivery.work({"src/a/new.py": "x = 1\n"})
    usage_error(delivery.run(("--reviewed", "no-such-revision")))


# --- --red: the tests fail on the integration tip and pass at the delivery tip ---------------------------------------


def add_feature_with_its_test(delivery: Delivery) -> None:
    delivery.work({"src/a/feature.py": "VALUE = 1\n", "tests/test_a.py": FEATURE_TEST})


def add_test_that_passes_on_the_base(delivery: Delivery) -> None:
    delivery.work({"tests/test_a.py": "assert True\n"})


def add_test_without_its_feature(delivery: Delivery) -> None:
    delivery.work({"tests/test_a.py": FEATURE_TEST})


def test_tests_that_fail_on_the_integration_tip_and_pass_at_the_tip_exit_0(delivery):
    add_feature_with_its_test(delivery)
    proc = delivery.run(("--red", delivery.red_command()))
    assert proc.returncode == 0, proc.stderr


def test_a_test_that_passes_on_the_integration_tip_exits_1(delivery):
    add_test_that_passes_on_the_base(delivery)
    refused(delivery.run(("--red", delivery.red_command())), "passes on the integration tip")


# A delivery that changes no code is never red by construction: the code its tests cover is on the base already.
# The script cannot tell a ticked task file from code, so the pointer carries its condition.
NO_CODE_POINTER = "if the delivery changes no code, "
TEAM_BRIEF = BRIEF + "OWNED: tasks.md\n"  # every worker ticks its own tasks in its delivery


def test_a_delivery_that_changes_no_code_is_told_how_its_red_is_proven(delivery):
    delivery.brief.write_text(TEAM_BRIEF, encoding="utf-8")
    delivery.integrate({"tasks.md": "- [ ] T1 tighten the test of a\n"})
    git(delivery.worktree, "merge", "-q", "--no-edit", "integration")
    delivery.work({"tests/test_a.py": "assert True\n", "tasks.md": "- [x] T1 tighten the test of a\n"})
    proc = delivery.run(("--red", delivery.red_command()))
    refused(proc, NO_CODE_POINTER)
    assert "without --red" in proc.stderr and "team-lead" in proc.stderr, proc.stderr


def test_the_pointer_of_a_never_red_refusal_states_its_condition(delivery):
    """A delivery with code whose tests were never red lacks its red: the pointer must not read as leave to skip it."""
    delivery.work({"src/a/new.py": "x = 1\n", "tests/test_a.py": "assert True\n"})
    refused(delivery.run(("--red", delivery.red_command())), "they were never red; " + NO_CODE_POINTER)


def test_a_test_that_fails_at_the_tip_exits_1(delivery):
    add_test_without_its_feature(delivery)
    refused(delivery.run(("--red", delivery.red_command())), "fails at the delivery tip")


def test_red_without_a_changed_test_file_exits_1(delivery):
    delivery.work({"src/a/new.py": "x = 1\n"})
    refused(delivery.run(("--red", delivery.red_command())), "no changed test file matches a `TESTS:` line")


def test_a_test_file_deleted_at_the_tip_is_left_out_of_the_red(delivery):
    """``git checkout <tip> -- <file>`` fails on a file the tip no longer has."""
    delivery.integrate({"tests/test_a_old.py": "assert True\n"})
    git(delivery.worktree, "merge", "-q", "--no-edit", "integration")
    git(delivery.worktree, "rm", "-q", "tests/test_a_old.py")
    git(delivery.worktree, "commit", "-q", "-m", "drop the old test")
    add_feature_with_its_test(delivery)
    proc = delivery.run(("--red", delivery.red_command()))
    assert proc.returncode == 0, proc.stderr


def test_red_without_tests_lines_exits_2(delivery):
    add_feature_with_its_test(delivery)
    delivery.brief.write_text("OWNED: src/a/*\nOWNED: tests/test_a*.py\n", encoding="utf-8")
    usage_error(delivery.run(("--red", delivery.red_command())), "TESTS:")


def test_a_test_command_that_cannot_start_exits_2(delivery):
    add_feature_with_its_test(delivery)
    usage_error(delivery.run(("--red", "no-such-program-for-the-red")), "cannot start")


def test_a_red_refusal_carries_the_last_lines_of_the_output_of_the_command(delivery):
    """The reason reaches the worker: without the output it names no test and no assertion."""
    noisy = "".join("print('noise line %d')\n" % number for number in range(30)) + "raise SystemExit('LAST-WORDS')\n"
    delivery.work({"tests/test_a.py": noisy})
    proc = delivery.run(("--red", delivery.red_command()))
    refused(proc, "fails at the delivery tip")
    assert "LAST-WORDS" in proc.stderr and "noise line 29" in proc.stderr
    assert "noise line 5\n" not in proc.stderr  # only the last 20 lines


def test_a_red_that_never_failed_carries_the_output_of_the_command_too(delivery):
    delivery.work({"tests/test_a.py": "print('RAN-AND-PASSED')\n"})
    refused(delivery.run(("--red", delivery.red_command())), "RAN-AND-PASSED")


@pytest.mark.parametrize("command", ['pytest "tests', "", "   "], ids=["unbalanced-quote", "empty", "blank"])
def test_a_test_command_that_cannot_be_read_exits_2_with_its_reason(delivery, command):
    add_feature_with_its_test(delivery)
    usage_error(delivery.run(("--red", command)), "--red")


@pytest.mark.parametrize(
    "scenario, command, code",
    [
        (add_feature_with_its_test, None, 0),
        (add_test_that_passes_on_the_base, None, 1),
        (add_test_without_its_feature, None, 1),
        (add_feature_with_its_test, "no-such-program-for-the-red", 2),
    ],
    ids=["accepted", "passes-on-the-base", "fails-at-the-tip", "cannot-start"],
)
def test_the_temporary_worktrees_are_gone_on_every_exit(delivery, scenario, command, code):
    scenario(delivery)
    proc = delivery.run(("--red", command or delivery.red_command()))
    assert proc.returncode == code, proc.stderr
    assert (code != 2) or "cannot start" in proc.stderr
    assert delivery.worktree_entries() == 2  # the checkout and the worker's own


def test_no_text_says_that_the_script_changes_nothing_or_that_the_command_is_confined():
    """With ``--red`` the script adds and removes worktrees and prunes, and the command inherits the environment."""
    claims = ("changes nothing", "no others", "nessun'altra")
    whole = [SCRIPT, REPO_ROOT / "skills" / "team-lead" / "SKILL.md"]
    about_it = [line for name in ("README.md", "README.it.md")
                for line in (REPO_ROOT / name).read_text(encoding="utf-8").splitlines() if "verify_delivery" in line]
    for text in [path.read_text(encoding="utf-8") for path in whole] + about_it:
        assert [claim for claim in claims if claim in text] == []


# --- exit 4: the shared state changed since the record ---------------------------------------------------------------

# A program that a git setting runs counts each call in the file it is given, and copies its input as a filter would.
SPY = "import sys\nwith open(sys.argv[1], 'a') as calls:\n    calls.write('x\\n')\nsys.stdout.write(sys.stdin.read())\n"


def spy(folder: Path):
    """The command line of a spy and the file where it counts its calls."""
    script, counter = folder / "spy.py", folder / "spy-calls"
    script.write_text(SPY, encoding="utf-8")
    return shlex.join([Path(sys.executable).as_posix(), script.as_posix(), counter.as_posix()]), counter


def calls(counter: Path) -> int:
    return len(counter.read_text(encoding="utf-8").splitlines()) if counter.exists() else 0


def ref(name: str) -> List[str]:
    return ["ref", name]


def test_a_branch_outside_the_team_that_moves_exits_4_with_its_recorded_and_found_value(delivery):
    before = git(delivery.repo, "rev-parse", "shared").strip()
    tip = delivery.work({"src/a/new.py": "x = 1\n"})
    git(delivery.repo, "branch", "-f", "shared", tip)
    proc = delivery.run()
    assert changed_items(proc) == [ref("refs/heads/shared")]
    assert printed(listed(proc)[0]) == {"item": ref("refs/heads/shared"), "recorded": before, "found": tip}


def test_a_loose_ref_beside_the_packed_one_it_shadows_exits_4_even_once_packed(delivery):
    """Where the file system ignores case, a loose ``Integration`` is what ``integration`` and its checkout read."""
    tip = delivery.work({"src/a/new.py": "x = 1\n"})
    git(delivery.repo, "pack-refs", "--all")
    (common(delivery.repo) / "refs" / "heads" / "Integration").write_text(tip + "\n", encoding="utf-8")
    items = changed_items(delivery.run())
    assert ref("refs/heads/Integration") in items
    if (common(delivery.repo) / "refs" / "heads" / "integration").exists():  # the loose file answers both names
        assert ref("refs/heads/integration") in items and [item[0] for item in items].count("worktree") == 1
    git(delivery.repo, "pack-refs", "--all")
    assert ref("refs/heads/Integration") in changed_items(delivery.run())


def test_a_branch_made_symbolic_with_the_same_value_exits_4(delivery):
    git(delivery.repo, "branch", "w-sync3", "shared")
    git(delivery.repo, "symbolic-ref", "refs/heads/shared", "refs/heads/w-sync3")
    assert changed_items(delivery.run()) == [ref("refs/heads/shared")]


def test_a_new_tag_and_a_stash_exit_4(delivery):
    git(delivery.repo, "tag", "v2")
    (delivery.repo / "src/b/b.py").write_text("b = 2\n", encoding="utf-8")
    git(delivery.repo, "stash", "-q")
    assert changed_items(delivery.run()) == [ref("refs/stash"), ref("refs/tags/v2")]


def test_the_head_of_the_coordinators_checkout_moved_exits_4(delivery):
    git(delivery.repo, "checkout", "-q", "--detach")
    [item] = changed_items(delivery.run())
    assert item[0] == "worktree" and Path(item[1]).name == "repo"


def test_a_new_worktree_on_a_branch_outside_the_team_exits_4(delivery, tmp_path):
    git(delivery.repo, "worktree", "add", "-q", str(tmp_path / "stray"), "shared")
    [item] = changed_items(delivery.run())
    assert item[0] == "worktree" and Path(item[1]).name == "stray"


def test_a_recorded_worktree_that_disappears_exits_4(tmp_path):
    delivery = make_delivery(tmp_path, lambda repo: git(repo, "worktree", "add", "-q", "--detach",
                                                        str(tmp_path / "kept")))
    git(delivery.repo, "worktree", "remove", str(tmp_path / "kept"))
    items = changed_items(delivery.run())
    assert [Path(item[1]).name for item in items if item[0] == "worktree"] == ["kept"]


def append(path: Path, text: str) -> None:
    with path.open("a", encoding="utf-8") as appended:
        appended.write(text)


COMMON_CHANGES = {
    "config": (lambda repo, folder: git(repo, "config", "x.y", "z"), ["config", "x.y"]),
    "shallow": (lambda repo, folder: (folder / "shallow").write_text("0" * 40 + "\n"), ["file", "shallow"]),
    "alternates": (lambda repo, folder: (folder / "objects" / "info" / "alternates").write_text("/x\n"),
                   ["file", "objects/info/alternates"]),
    "attributes": (lambda repo, folder: (folder / "info" / "attributes").write_text("* -text\n"),
                   ["file", "info/attributes"]),
    "exclude": (lambda repo, folder: append(folder / "info" / "exclude", "build/\n"), ["exclude", "build/"]),
    "hook": (lambda repo, folder: (folder / "hooks" / "post-checkout").write_text("#!/bin/sh\n"),
             ["file", "hooks/post-checkout"]),
    "new-file": (lambda repo, folder: (folder / "stray").write_text("x"), ["file", "stray"]),
}


@pytest.mark.parametrize("change", sorted(COMMON_CHANGES))
def test_a_change_in_the_common_folder_outside_the_closed_list_exits_4(delivery, change):
    write, expected = COMMON_CHANGES[change]
    write(delivery.repo, common(delivery.repo))
    assert [item[:2] for item in changed_items(delivery.run())] == [expected]


def worktree_config_on(repo: Path) -> None:
    git(repo, "config", "extensions.worktreeConfig", "true")


@pytest.mark.parametrize("form", ["filter", "include"])
def test_a_filter_in_the_workers_own_config_exits_4_before_its_status_runs_it(tmp_path, form):
    delivery = make_delivery(tmp_path, worktree_config_on)
    command, counter = spy(tmp_path)
    if form == "filter":
        git(delivery.worktree, "config", "--worktree", "filter.spy.clean", command)
    else:
        included = tmp_path / "included.cfg"
        git(tmp_path, "config", "--file", included.as_posix(), "filter.spy.clean", command)
        git(delivery.worktree, "config", "--worktree", "include.path", included.as_posix())
    (delivery.worktree / ".gitattributes").write_text("* filter=spy\n", encoding="utf-8")
    os.utime(str(delivery.worktree / "src/a/a.py"), (1_000_000_000, 1_000_000_000))
    items = changed_items(delivery.run())
    assert [item[:3] for item in items] == [["worktree-config", "worker",
                                             "filter.spy.clean" if form == "filter" else "include.path"]]
    assert calls(counter) == 0


def test_a_configuration_file_that_appears_exits_4(tmp_path):
    later = tmp_path / "later.cfg"
    delivery = make_delivery(tmp_path, lambda repo: git(repo, "config", "include.path", later.as_posix()))
    later.write_text("[x]\n", encoding="utf-8")
    (delivery.home / ".gitconfig").write_text("[y]\n", encoding="utf-8")
    names = {Path(item[1]).name for item in changed_items(delivery.run()) if item[0] == "file"}
    assert names == {"later.cfg", ".gitconfig"}


HOOK_WRITER = (
    "import os, subprocess\n"
    "common = subprocess.run(['git', 'rev-parse', '--path-format=absolute', '--git-common-dir'], "
    "capture_output=True, text=True).stdout.strip()\n"
    "hook = os.path.join(common, 'hooks', 'post-checkout')\n"
    "with open(hook, 'w') as written:\n"
    "    written.write('#!/bin/sh\\necho x >> %s\\n')\n"
    "os.chmod(hook, 0o755)\n"
)
DRIVER_WRITER = "import subprocess\nsubprocess.run(['git', 'config', 'merge.spy.driver', %r])\n"


def test_a_hook_planted_once_the_temporary_worktree_is_added_exits_4_before_the_checkout_runs_it(
        delivery, tmp_path, monkeypatch, capsys):
    """The script runs here, in this process, so that the change lands between ``worktree add`` and ``checkout``."""
    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    import verify_delivery

    counter, added = tmp_path / "hook-calls", verify_delivery.temporary_worktree

    @contextmanager
    def then_a_hook(revision, prefix):
        with added(revision, prefix) as folder:
            hook = common(delivery.repo) / "hooks" / "post-checkout"
            hook.write_text("#!/bin/sh\necho x >> %s\n" % counter.as_posix(), encoding="utf-8")
            hook.chmod(0o755)
            yield folder

    monkeypatch.setattr(verify_delivery, "temporary_worktree", then_a_hook)
    monkeypatch.chdir(delivery.repo)
    for name, value in delivery.env().items():
        monkeypatch.setenv(name, value)
    add_feature_with_its_test(delivery)
    arguments = ["--integration", "integration", "--branch", "w", "--tip", delivery.tip(), "--worktree",
                 delivery.worktree.as_posix(), "--brief", delivery.brief.as_posix(), "--red", delivery.red_command()]
    assert verify_delivery.main(arguments) == 4
    assert '["file", "hooks/post-checkout"]' in capsys.readouterr().err and calls(counter) == 0


def test_a_hook_that_the_test_command_writes_exits_4_before_the_next_worktree_is_added(delivery, tmp_path):
    counter = tmp_path / "hook-calls"
    # before the assertion: it runs on the integration tip, where the test then fails, so the next worktree is the tip's
    delivery.work({"src/a/feature.py": "VALUE = 1\n",
                   "tests/test_a.py": HOOK_WRITER % counter.as_posix() + FEATURE_TEST})
    items = changed_items(delivery.run(("--red", delivery.red_command())))
    assert [item[:2] for item in items] == [["file", "hooks/post-checkout"]]
    assert calls(counter) == 0 and delivery.worktree_entries() == 2


def test_a_merge_driver_that_the_test_command_sets_exits_4_before_the_merges_are_read(tmp_path):
    delivery = make_delivery(tmp_path, lambda repo: (common(repo) / "info" / "attributes").write_text(
        "* merge=spy\n", encoding="utf-8"))
    command, counter = spy(tmp_path)
    conflicting_resolution(delivery)
    # after the assertion: it runs only at the delivery tip, the last command before the merges are read
    delivery.work({"src/a/feature.py": "VALUE = 1\n",
                   "tests/test_a.py": FEATURE_TEST + DRIVER_WRITER % (command + " %O %A %B")})
    items = changed_items(delivery.run(("--red", delivery.red_command())))
    assert [item[:2] for item in items] == [["config", "merge.spy.driver"]]
    assert calls(counter) == 0


def test_a_tag_made_between_a_comparison_and_merged_stays_a_difference(delivery):
    delivery.work({"src/a/new.py": "x = 1\n"})
    assert delivery.run().returncode == 0
    git(delivery.repo, "tag", "late")
    delivery.integrate({"src/b/more.py": "m = 1\n"})
    assert changed_items(delivery.run()) == [ref("refs/tags/late")]


@pytest.mark.parametrize("branch", ["worktree-agent-old", "w-sync3"])
def test_a_recorded_team_like_branch_that_moves_exits_4(tmp_path, branch):
    delivery = make_delivery(tmp_path, lambda repo: git(repo, "branch", branch))
    git(delivery.repo, "branch", "-f", branch, delivery.work({"src/a/new.py": "x = 1\n"}))
    assert changed_items(delivery.run()) == [ref("refs/heads/" + branch)]


@pytest.mark.parametrize("branch", ["worktree-agent-old", "w-sync3"])
def test_a_new_worktree_on_a_recorded_team_like_branch_exits_4(tmp_path, branch):
    """Only a team ref absent from the record frees a new worktree on it."""
    delivery = make_delivery(tmp_path, lambda repo: git(repo, "branch", branch))
    git(delivery.repo, "worktree", "add", "-q", str(tmp_path / "late"), branch)
    [item] = changed_items(delivery.run())
    assert item[0] == "worktree" and Path(item[1]).name == "late"


def test_a_new_file_in_a_hooks_folder_outside_the_repository_exits_4(tmp_path):
    hooks = tmp_path / "hooks"

    def outside_hooks(repo: Path) -> None:
        hooks.mkdir()
        (hooks / "pre-commit.sample").write_text("#!/bin/sh\n", encoding="utf-8")
        git(repo, "config", "core.hooksPath", hooks.as_posix())

    delivery = make_delivery(tmp_path, outside_hooks)
    (hooks / "post-checkout").write_text("#!/bin/sh\n", encoding="utf-8")
    [item] = changed_items(delivery.run())
    assert item[0] == "file" and Path(item[1]).name == "post-checkout"


def test_a_recorded_branch_and_tag_deleted_exit_4(delivery):
    git(delivery.repo, "branch", "-D", "shared")
    git(delivery.repo, "tag", "-d", "v1")
    assert changed_items(delivery.run()) == [ref("refs/heads/shared"), ref("refs/tags/v1")]


def test_a_branch_made_without_team_exits_4(delivery):
    git(delivery.repo, "branch", "w2")
    assert changed_items(delivery.run()) == [ref("refs/heads/w2")]


def test_after_an_accept_a_change_not_listed_is_still_a_difference(delivery):
    git(delivery.repo, "tag", "v2")
    delivery.accept_listed()
    git(delivery.repo, "tag", "v3")
    assert changed_items(delivery.run()) == [ref("refs/tags/v3")]


def test_an_item_changed_again_after_its_listing_stays_a_difference_once_accepted(delivery):
    """``accept`` records the value the user saw, not the one there when it runs."""
    git(delivery.repo, "tag", "v2")
    lines = listed(delivery.run())
    seen = printed(lines[0])["found"]
    tip = delivery.work({"src/a/new.py": "x = 1\n"})
    git(delivery.repo, "tag", "-f", "v2", tip)
    delivery.shared("accept", *lines)
    proc = delivery.run()
    assert changed_items(proc) == [ref("refs/tags/v2")]
    assert printed(listed(proc)[0])["recorded"] == seen and printed(listed(proc)[0])["found"] == tip


@pytest.mark.skipif(sys.platform == "win32", reason="a symlink needs a privilege on Windows")
def test_a_hook_symlink_pointed_elsewhere_exits_4(tmp_path):
    def linked_hook(repo: Path) -> None:
        hooks = common(repo) / "hooks"
        (hooks / "a.sh").write_text("#!/bin/sh\n", encoding="utf-8")
        (hooks / "post-checkout").symlink_to("a.sh")

    delivery = make_delivery(tmp_path, linked_hook)
    hook = common(delivery.repo) / "hooks" / "post-checkout"
    hook.unlink()
    hook.symlink_to("b.sh")
    assert [item[:2] for item in changed_items(delivery.run())] == [["file", "hooks/post-checkout"]]


def test_exit_4_wins_over_a_refusal(delivery):
    delivery.work({"src/b/stray.py": "s = 1\n"})
    git(delivery.repo, "tag", "v2")
    assert changed_items(delivery.run()) == [ref("refs/tags/v2")]


# --- the record and the worker's repository: exits 2 and 1 ----------------------------------------------------------


def test_without_a_record_the_check_exits_2_and_says_how_a_run_begins(delivery):
    (delivery.repo / ".pe" / "shared-state.json").unlink()
    proc = delivery.run()
    usage_error(proc, "no record at")
    assert "`shared_state.py start` begins a new run; in a run, stop and go to the user" in proc.stderr


def test_a_worker_git_folder_outside_the_worktrees_folder_exits_1_and_runs_nothing_there(tmp_path):
    """Its ``commondir`` names this repository, so only where the git folder itself lies tells it apart."""
    delivery = make_delivery(tmp_path, worktree_config_on)
    tip = delivery.work({"src/a/new.py": "x = 1\n"})
    elsewhere = tmp_path / "elsewhere"
    shutil.copytree(str(common(delivery.repo) / "worktrees" / "worker"), str(elsewhere))
    (elsewhere / "commondir").write_text(common(delivery.repo).as_posix() + "\n", encoding="utf-8")
    command, counter = spy(tmp_path)
    git(tmp_path, "config", "--file", (elsewhere / "config.worktree").as_posix(), "filter.spy.clean", command)
    (delivery.worktree / ".gitattributes").write_text("* filter=spy\n", encoding="utf-8")
    os.utime(str(delivery.worktree / "src/a/a.py"), (1_000_000_000, 1_000_000_000))
    (delivery.worktree / ".git").write_text("gitdir: %s\n" % elsewhere.as_posix(), encoding="utf-8")
    refused(delivery.run(replace={"--tip": tip}), "the worktree's .git leads to")
    assert calls(counter) == 0


def test_a_worker_git_that_leads_to_another_repository_exits_1_and_runs_nothing_there(delivery, tmp_path):
    tip = delivery.work({"src/a/new.py": "x = 1\n"})
    other = init_repo(tmp_path / "other")
    commit(other, {"src/a/a.py": "a = 1\n"}, "other")
    command, counter = spy(tmp_path)
    git(other, "config", "filter.spy.clean", command)
    (other / ".git" / "info" / "attributes").write_text("* filter=spy\n", encoding="utf-8")
    (delivery.worktree / ".git").write_text("gitdir: %s\n" % (other / ".git").as_posix(), encoding="utf-8")
    refused(delivery.run(replace={"--tip": tip}), "the worktree's .git leads to")
    assert calls(counter) == 0


# --- accepted: what the closed list lets change ----------------------------------------------------------------------


def accepted(proc) -> None:
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_the_sync_branches_of_a_resumption_are_the_teams(delivery):
    delivery.work({"src/a/new.py": "x = 1\n"})
    for name in ("w-sync", "w-sync2"):
        git(delivery.worktree, "switch", "-q", "-c", name)
        delivery.work({"src/a/%s.py" % name.replace("-", "_"): "x = 1\n"})
    accepted(delivery.run(replace={"--branch": "w-sync2"}))


def test_a_host_branch_and_a_branch_declared_after_start_are_the_teams(delivery, tmp_path):
    delivery.shared("team", "w2")
    agent = tmp_path / "agent"
    git(delivery.repo, "worktree", "add", "-q", "-b", "worktree-agent-x", str(agent), "integration")
    git(agent, "switch", "-q", "-c", "w2")
    commit(agent, {"src/a/agent.py": "x = 1\n"}, "work")
    delivery.integrate({"src/b/more.py": "m = 1\n"})
    git(agent, "merge", "-q", "--no-edit", "integration")
    tip = git(agent, "rev-parse", "HEAD").strip()
    accepted(delivery.run(replace={"--branch": "w2", "--tip": tip, "--worktree": agent.as_posix()}))


def test_gc_changes_nothing_that_is_compared(delivery):
    delivery.work({"src/a/new.py": "x = 1\n"})
    git(delivery.repo, "gc", "-q")
    accepted(delivery.run())


def reftable_works(tmp_path: Path) -> bool:
    probe = tmp_path / "probe"
    probe.mkdir()
    return subprocess.run(["git", "init", "-q", "--ref-format=reftable"], cwd=str(probe)).returncode == 0


def test_a_reftable_repository_with_a_commit_and_a_fast_forward(tmp_path):
    if not reftable_works(tmp_path):
        pytest.skip("git init --ref-format=reftable fails here (it needs git 2.45)")
    delivery = make_delivery(tmp_path, init=("--ref-format=reftable",))
    tip = delivery.work({"src/a/new.py": "x = 1\n"})
    git(delivery.repo, "merge", "-q", "--ff-only", tip)
    delivery.shared("merged", tip)
    accepted(delivery.run())


def test_the_fsmonitor_daemon_started_after_the_record(delivery):
    started = subprocess.run(["git", "fsmonitor--daemon", "start"], cwd=str(delivery.repo), capture_output=True,
                             text=True)
    if started.returncode != 0:
        pytest.skip("git fsmonitor--daemon start fails here (macOS and Windows only): %s" % started.stderr.strip())
    try:
        delivery.work({"src/a/new.py": "x = 1\n"})
        accepted(delivery.run())
    finally:
        subprocess.run(["git", "fsmonitor--daemon", "stop"], cwd=str(delivery.repo), capture_output=True)


def test_a_prunable_worktree_pruned(tmp_path):
    def prunable(repo: Path) -> None:
        git(repo, "worktree", "add", "-q", "--detach", str(tmp_path / "gone"))
        shutil.rmtree(str(tmp_path / "gone"))

    delivery = make_delivery(tmp_path, prunable)
    git(delivery.repo, "worktree", "prune")
    delivery.work({"src/a/new.py": "x = 1\n"})
    accepted(delivery.run())


def test_a_config_worktree_copied_from_the_coordinator(tmp_path):
    def coordinator_config(repo: Path) -> None:
        worktree_config_on(repo)
        git(repo, "config", "--worktree", "x.y", "z")

    delivery = make_delivery(tmp_path, coordinator_config)
    assert git(delivery.worktree, "config", "--worktree", "x.y").strip() == "z"
    delivery.work({"src/a/new.py": "x = 1\n"})
    accepted(delivery.run())


def test_what_the_host_writes_into_the_configuration_and_the_exclude_file(delivery):
    worktree_config_on(delivery.repo)
    append(common(delivery.repo) / "info" / "exclude", ".claude/worktrees/\n**/.claude/settings.local.json\n")
    git(delivery.worktree, "config", "--worktree", "core.untrackedCache", "true")
    git(delivery.worktree, "config", "--worktree", "core.longpaths", "true")
    delivery.work({"src/a/new.py": "x = 1\n"})
    accepted(delivery.run())


def test_merged_after_a_fast_forward_and_after_a_merge_commit(delivery):
    first = delivery.work({"src/a/new.py": "x = 1\n"})
    git(delivery.repo, "merge", "-q", "--ff-only", first)
    delivery.shared("merged", first)
    accepted(delivery.run())
    delivery.work({"src/a/more.py": "y = 1\n"})
    git(delivery.repo, "merge", "-q", "--no-ff", "-m", "integrate w", delivery.tip())
    delivery.shared("merged", git(delivery.repo, "rev-parse", "HEAD").strip())
    accepted(delivery.run())


def test_an_accepted_change_is_no_longer_listed(delivery):
    git(delivery.repo, "tag", "v2")
    delivery.accept_listed()
    accepted(delivery.run())


def test_a_submodule_of_the_worker_runs_no_program_of_its_own_configuration(tmp_path):
    """Its git folder lies in the worker's admin folder, which nothing compares, so the status never looks inside it."""
    delivery = make_delivery(tmp_path, lambda repo: submodule_in(repo, tmp_path / "sub"))
    git(delivery.worktree, "-c", "protocol.file.allow=always", "submodule", "update", "-q", "--init")
    delivery.work({"src/a/new.py": "x = 1\n"})
    command, counter = spy(tmp_path)  # after the work: the worker's own commit looks into the submodule too
    inner = delivery.worktree / "sub"
    git(inner, "config", "core.fsmonitor", command)
    git(inner, "config", "filter.spy.clean", command)
    (inner / ".gitattributes").write_text("* filter=spy\n", encoding="utf-8")
    os.utime(str(inner / "s.py"), (1_000_000_000, 1_000_000_000))
    accepted(delivery.run())
    assert calls(counter) == 0


def test_an_accepted_fsmonitor_in_the_workers_own_config_still_runs_nothing(tmp_path):
    """Once the user accepts the entry, only ``-c core.fsmonitor=false`` keeps the status from starting it."""
    delivery = make_delivery(tmp_path, worktree_config_on)
    delivery.work({"src/a/new.py": "x = 1\n"})
    command, counter = spy(tmp_path)  # after the work: the worker's own commit would start it too
    git(delivery.worktree, "config", "--worktree", "core.fsmonitor", command)
    delivery.accept_listed()
    accepted(delivery.run())
    assert calls(counter) == 0
