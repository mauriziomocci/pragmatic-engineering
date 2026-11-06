"""The delivery check of team-lead against git: every case builds its own repository and its own worker worktree.

The script runs from the coordinator's checkout (``repo``, on the branch ``integration``) and reads the worker's
branch ``w``, checked out in ``worktree``. Every path inside a command line is written with ``as_posix()``: the
suite also runs on Windows, where a backslash is an escape for the command splitter.
"""
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

import pytest

from support import REPO_ROOT, commit, git, init_repo, run_script

SCRIPT = REPO_ROOT / "skills" / "team-lead" / "verify_delivery.py"
BRIEF = "# Brief\n\nOWNED: src/a/*\nOWNED: tests/test_a*.py\nTESTS: tests/test_a*.py\n"
# A test is a script that exits with a non-zero code when its assertion falls, run from the root of a worktree.
FEATURE_TEST = "import sys\n\nsys.path.insert(0, 'src/a')\nimport feature\n\nassert feature.VALUE == 1\n"


@dataclass
class Delivery:
    """The coordinator's checkout, the worker's worktree on ``w``, and the brief."""

    repo: Path
    worktree: Path
    brief: Path

    def tip(self) -> str:
        return git(self.worktree, "rev-parse", "HEAD").strip()

    def work(self, files: Dict[str, str], message: str = "work") -> str:
        return commit(self.worktree, files, message)

    def integrate(self, files: Dict[str, str], message: str = "integration moves") -> str:
        return commit(self.repo, files, message)

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
        git(self.repo, "branch", "other", "integration")
        git(self.repo, "checkout", "-q", "other")
        commit(self.repo, {"src/b/b.py": "b = 'other'\n"}, "other worker")
        git(self.repo, "checkout", "-q", "integration")
        commit(self.repo, {"src/b/b.py": "b = 'integration'\n"}, "integration moves")
        subprocess.run(["git", "merge", "--no-edit", "other"], cwd=str(self.repo), capture_output=True)
        git(self.repo, "checkout", "--ours", "--", "src/b/b.py")
        git(self.repo, "add", "src/b/b.py")
        git(self.repo, "commit", "-q", "--no-edit")
        return git(self.repo, "rev-parse", "HEAD").strip()

    def red_command(self) -> str:
        return shlex.join([Path(sys.executable).as_posix(), "tests/test_a.py"])

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
        return run_script(SCRIPT, [*flat, *extra], self.repo)


@pytest.fixture
def delivery(tmp_path):
    repo = init_repo(tmp_path / "repo")
    git(repo, "checkout", "-q", "-b", "integration")
    commit(repo, {"src/a/a.py": "a = 1\n", "src/b/b.py": "b = 1\n"}, "base")
    worktree = tmp_path / "worker"
    git(repo, "worktree", "add", "-q", "-b", "w", str(worktree), "integration")
    brief = tmp_path / "brief.md"
    brief.write_text(BRIEF, encoding="utf-8")
    return Delivery(repo, worktree, brief)


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
    refused(delivery.run(replace={"--tip": declared}), "not to the declared tip")


@pytest.mark.parametrize("kind", ["tag", "ref-under-refs"])
def test_a_tag_or_a_ref_named_like_the_integration_is_ignored(delivery, kind):
    """A tag ``integration``, or ``refs/integration``, at the delivery tip would empty the diff if git read it."""
    delivery.work({"src/b/stray.py": "s = 1\n"})
    if kind == "tag":
        git(delivery.repo, "tag", "integration", delivery.tip())
    else:
        git(delivery.repo, "update-ref", "refs/integration", delivery.tip())
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
