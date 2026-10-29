"""The re-creation script of safe-operations: refusals, the rebase and the four checks, in temporary repositories.

The script rewrites history, so nothing here touches this repository: every test builds its own, with the test's
isolated git configuration. No test fakes a date, so the one thing these runs cannot show is that git gives an old
commit the time of the moment; the date check exists for that, and it is exercised on the dates the commits have.
"""
import importlib.util
from datetime import datetime
from pathlib import Path
from typing import Tuple

import pytest

from support import REPO_ROOT, commit, git, init_repo, run_script

SCRIPT = REPO_ROOT / "skills" / "safe-operations" / "recreate_night_commits.py"


@pytest.fixture
def night():
    """The script as a module, loaded per test so that a missing file turns each test red on its own."""
    spec = importlib.util.spec_from_file_location("recreate_night_commits", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def window_around_now() -> str:
    """A window that holds the current hour with an hour of margin on each side, so a run at a boundary holds."""
    hour = datetime.now().hour
    return "%02d-%02d" % ((hour - 1) % 24, (hour + 2) % 24)


def window_without_now() -> str:
    hour = datetime.now().hour
    return "%02d-%02d" % ((hour + 2) % 24, (hour + 4) % 24)


def night_repo(tmp_path: Path, window: str = "") -> Tuple[Path, str]:
    """A repository with one base commit and its office hours, which default to a window around now."""
    repo = init_repo(tmp_path / "repo")
    base = commit(repo, {"a.txt": "base\n"}, "base")
    git(repo, "config", "pe.officeHours", window or window_around_now())
    return repo, base


def head(repo: Path) -> str:
    return git(repo, "rev-parse", "HEAD").strip()


def tags(repo: Path) -> str:
    return git(repo, "tag", "--list").strip()


def refuse(repo: Path, base: str, check: str):
    """Run the script and assert that it refused at ``check`` and changed nothing: same tip, no tag."""
    before = head(repo)
    proc = run_script(SCRIPT, [base], repo)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert check in proc.stderr, proc.stderr
    assert head(repo) == before and tags(repo) == ""
    return proc


def with_remote(tmp_path: Path, repo: Path) -> Path:
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    git(repo, "remote", "add", "origin", str(remote))
    return remote


# --- the window ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("hour,inside", [(5, False), (6, True), (20, True), (21, False)])
def test_the_window_06_21_runs_from_06_up_to_2059(night, hour, inside):
    assert night.parse_window("06-21").contains(hour) is inside


@pytest.mark.parametrize("hour,inside", [(21, False), (22, True), (23, True), (0, True), (5, True), (6, False)])
def test_a_window_whose_start_is_after_its_end_wraps_past_midnight(night, hour, inside):
    assert night.parse_window("22-06").contains(hour) is inside


@pytest.mark.parametrize("value", ["", "6-21", "06-21-", "ab-cd", "25-03", "06-24", "06-06", "06:21", "none"])
def test_a_malformed_window_raises_the_typed_error(night, value):
    with pytest.raises(night.OfficeHoursError):
        night.parse_window(value)


def test_the_backup_tag_is_named_to_the_second_as_the_skill_says(night):
    skill = (SCRIPT.parent / "SKILL.md").read_text(encoding="utf-8")
    assert night.backup_tag(datetime(2026, 1, 2, 3, 4, 5)) == "night-backup-20260102-030405"
    assert "`night-backup-<YYYYMMDD-HHMMSS>`" in skill and "recreate_night_commits.py" in skill


# --- refusals, before anything changes ---------------------------------------------------------------------------


def test_it_refuses_when_no_office_hours_are_set(tmp_path):
    repo = init_repo(tmp_path / "repo")
    base = commit(repo, {"a.txt": "base\n"}, "base")
    commit(repo, {"a.txt": "night\n"}, "night")
    refuse(repo, base, "office hours")


def test_it_refuses_when_office_hours_are_none(tmp_path):
    repo, base = night_repo(tmp_path, window="none")
    commit(repo, {"a.txt": "night\n"}, "night")
    refuse(repo, base, "office hours")


def test_it_refuses_a_malformed_window_with_a_non_zero_exit(tmp_path):
    repo, base = night_repo(tmp_path, window="six-21")
    commit(repo, {"a.txt": "night\n"}, "night")
    refuse(repo, base, "office hours")


def test_it_refuses_a_base_that_is_not_a_commit(tmp_path):
    repo, _ = night_repo(tmp_path)
    commit(repo, {"a.txt": "night\n"}, "night")
    refuse(repo, "no-such-ref", "base")


def test_it_refuses_a_base_that_looks_like_an_option(tmp_path):
    repo, _ = night_repo(tmp_path)
    commit(repo, {"a.txt": "night\n"}, "night")
    refuse(repo, "--help", "base")


def test_it_refuses_an_empty_range(tmp_path):
    repo, _ = night_repo(tmp_path)
    refuse(repo, "HEAD", "range")


def test_it_refuses_a_dirty_working_tree(tmp_path):
    repo, base = night_repo(tmp_path)
    commit(repo, {"a.txt": "night\n"}, "night")
    (repo / "scratch.txt").write_text("not committed\n", encoding="utf-8")
    refuse(repo, base, "clean tree")


def test_it_refuses_when_the_current_hour_is_outside_the_window(tmp_path):
    repo, base = night_repo(tmp_path, window=window_without_now())
    commit(repo, {"a.txt": "night\n"}, "night")
    refuse(repo, base, "window")


def test_it_refuses_a_commit_already_on_a_remote_tracking_branch(tmp_path):
    repo, base = night_repo(tmp_path)
    with_remote(tmp_path, repo)
    commit(repo, {"a.txt": "published\n"}, "published")
    git(repo, "push", "-q", "origin", "main")
    commit(repo, {"a.txt": "night\n"}, "night")
    refuse(repo, base, "published commits")


def test_it_refuses_a_backup_tag_that_already_exists(night, tmp_path, monkeypatch):
    repo, base = night_repo(tmp_path)
    commit(repo, {"a.txt": "night\n"}, "night")
    now = datetime.now()
    git(repo, "tag", night.backup_tag(now))
    monkeypatch.chdir(repo)
    before = head(repo)
    with pytest.raises(night.Refusal) as refusal:
        night.recreate(base, now)
    assert refusal.value.check == "backup tag" and head(repo) == before


def test_it_refuses_published_history_pulled_in_by_a_local_merge(tmp_path):
    """A branch pushed at F0 that merges the already published target at night: the target's commits are not ours."""
    repo, _ = night_repo(tmp_path)
    remote = with_remote(tmp_path, repo)
    git(repo, "checkout", "-q", "-b", "feature")
    first = commit(repo, {"f.txt": "f0\n"}, "f0")
    git(repo, "push", "-q", "origin", "feature")
    git(repo, "checkout", "-q", "main")
    commit(repo, {"x.txt": "x1\n"}, "x1")
    target_tip = commit(repo, {"x.txt": "x2\n"}, "x2")
    git(repo, "push", "-q", "origin", "main")
    git(repo, "checkout", "-q", "feature")
    git(repo, "merge", "-q", "--no-edit", "main")
    commit(repo, {"f.txt": "night\n"}, "night")
    refuse(repo, first, "published commits")
    assert git(repo, "rev-parse", "origin/main").strip() == target_tip
    assert git(remote, "rev-parse", "main").strip() == target_tip
    assert git(repo, "merge-base", "--is-ancestor", target_tip, "HEAD") == ""


def test_it_needs_exactly_one_argument(tmp_path):
    repo, _ = night_repo(tmp_path)
    proc = run_script(SCRIPT, [], repo)
    assert proc.returncode == 2 and "usage" in proc.stderr.lower()


# --- the re-creation ----------------------------------------------------------------------------------------------


def log_of(repo: Path, rev_range: str) -> str:
    return git(repo, "log", "--format=%B", rev_range)


def test_it_re_creates_two_commits_and_the_four_checks_pass(tmp_path):
    repo, base = night_repo(tmp_path)
    commit(repo, {"a.txt": "one\n"}, "first night commit")
    commit(repo, {"b.txt": "two\n"}, "second night commit")
    old_tip = head(repo)
    proc = run_script(SCRIPT, [base], repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    tag = tags(repo)
    assert tag.startswith("night-backup-") and "four checks passed" in proc.stdout and tag in proc.stdout
    assert git(repo, "rev-parse", tag).strip() == old_tip
    assert git(repo, "diff", "--stat", tag, "HEAD") == ""
    assert git(repo, "rev-list", "--count", base + "..HEAD") == git(repo, "rev-list", "--count", base + ".." + tag)
    assert log_of(repo, base + "..HEAD") == log_of(repo, base + ".." + tag)


def test_a_merge_in_the_range_stays_a_merge(tmp_path):
    repo, base = night_repo(tmp_path)
    git(repo, "checkout", "-q", "-b", "side")
    commit(repo, {"s.txt": "side\n"}, "side commit")
    git(repo, "checkout", "-q", "main")
    commit(repo, {"m.txt": "main\n"}, "main commit")
    git(repo, "merge", "-q", "--no-ff", "-m", "merge side", "side")
    merges = git(repo, "rev-list", "--merges", "--count", base + "..HEAD")
    proc = run_script(SCRIPT, [base], repo)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert git(repo, "rev-list", "--merges", "--count", base + "..HEAD") == merges == "1\n"


def test_a_failed_rebase_prints_the_way_back_and_exits_non_zero(tmp_path):
    """A base on a sibling line that changes the same file makes the replay conflict; the script runs no way back."""
    repo, _ = night_repo(tmp_path)
    git(repo, "checkout", "-q", "-b", "sibling")
    other = commit(repo, {"a.txt": "other\n"}, "sibling change")
    git(repo, "checkout", "-q", "main")
    commit(repo, {"a.txt": "night\n"}, "night")
    proc = run_script(SCRIPT, [other], repo)
    assert proc.returncode == 1
    assert "rebase" in proc.stderr and "git rebase --abort" in proc.stderr and tags(repo) in proc.stderr


# --- the four checks, one by one ---------------------------------------------------------------------------------


def two_lines(repo: Path) -> Tuple[str, str]:
    """A base and a tip two commits above it, on main."""
    base = head(repo)
    commit(repo, {"a.txt": "one\n"}, "one")
    commit(repo, {"a.txt": "two\n"}, "two")
    return base, head(repo)


def test_the_tree_check_fails_when_the_tag_has_another_tree(night, tmp_path, monkeypatch):
    repo, _ = night_repo(tmp_path)
    base, tip = two_lines(repo)
    monkeypatch.chdir(repo)
    window = night.parse_window("00-23")
    assert night.tree_is_the_tags(night.Recreation(base, tip, window)) is True
    assert night.tree_is_the_tags(night.Recreation(base, base, window)) is False


def test_the_count_check_fails_when_the_tag_has_another_number_of_commits(night, tmp_path, monkeypatch):
    repo, _ = night_repo(tmp_path)
    base, tip = two_lines(repo)
    monkeypatch.chdir(repo)
    window = night.parse_window("00-23")
    assert night.commit_count_is_the_tags(night.Recreation(base, tip, window)) is True
    assert night.commit_count_is_the_tags(night.Recreation(base, "HEAD~1", window)) is False


def test_the_messages_check_fails_when_one_message_differs_and_ignores_the_order(night, tmp_path, monkeypatch):
    repo, _ = night_repo(tmp_path)
    base, tip = two_lines(repo)
    git(repo, "checkout", "-q", "-b", "alt", base)
    commit(repo, {"a.txt": "one\n"}, "one")
    commit(repo, {"a.txt": "two\n"}, "other words")
    git(repo, "checkout", "-q", "main")
    monkeypatch.chdir(repo)
    window = night.parse_window("00-23")
    assert night.messages_are_the_tags(night.Recreation(base, tip, window)) is True
    assert night.messages_are_the_tags(night.Recreation(base, "alt", window)) is False


def test_the_dates_check_looks_at_both_dates_of_every_commit(night, tmp_path, monkeypatch):
    repo, _ = night_repo(tmp_path)
    base, tip = two_lines(repo)
    monkeypatch.chdir(repo)
    inside = night.parse_window(window_around_now())
    outside = night.parse_window(window_without_now())
    assert night.dates_are_in_the_window(night.Recreation(base, tip, inside)) is True
    assert night.dates_are_in_the_window(night.Recreation(base, tip, outside)) is False


def test_a_failed_check_names_itself_and_prints_the_way_back_without_running_it(night, tmp_path, monkeypatch, capsys):
    repo, base = night_repo(tmp_path)
    commit(repo, {"a.txt": "night\n"}, "night")
    monkeypatch.chdir(repo)
    monkeypatch.setattr(night, "CHECKS", (("a check that fails", lambda recreation: False),))
    assert night.main([base]) == 1
    error = capsys.readouterr().err
    assert "a check that fails" in error and "git reset --keep %s" % tags(repo) in error
