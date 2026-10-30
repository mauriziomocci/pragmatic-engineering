#!/usr/bin/env python3
"""Re-create, inside the office hours, the commits made outside them and never pushed.

Usage: python3 <this skill's folder>/recreate_night_commits.py <base>, run from any directory of the repository to
fix. ``<base>`` is the last commit already pushed, or the branch point when the branch was never pushed.

The script refuses to start, and changes nothing, in this order: not inside a repository's work tree; no office hours
set (``pe.officeHours``); a base that is not a commit, or nothing above it; the current hour outside the window; a
commit of ``<base>..HEAD`` already on a remote-tracking branch, because published history is never rewritten (the
branches are read as they are after the last fetch); a backup tag that already exists. Then it tags the tip, runs
``git rebase --force-rebase --ignore-date --rebase-merges <base>`` in a temporary worktree of its own and runs four
checks on the result, stopping at the first that fails (``rebase.updateRefs`` is pinned off, so no other local branch
moves). Only when all four pass does the branch move to the result, with ``git update-ref`` guarded by the tip read
before the run. The user's working tree and index are never read or written: the new tree is the tag's, so they stay
consistent, and uncommitted changes and untracked files, ignored or not, are safe. On any failure after the tag the
branch has not moved, and the message says how to delete the tag.

Every day uses the hours of ``pe.officeHours``, weekends and ``pe.holidays`` included, so a commit re-created on a
weekend morning carries a date inside the weekday hours, which the date check accepts.
"""
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Iterator, List, Sequence, Tuple

WINDOW = re.compile(r"(\d\d)-(\d\d)")


class Refusal(Exception):
    """A check failed: ``check`` names it, ``way_back`` lists what the user can run to undo what was done."""

    def __init__(self, check: str, detail: str, way_back: Sequence[str] = ()) -> None:
        super().__init__("%s: %s" % (check, detail))
        self.check = check
        self.detail = detail
        self.way_back = tuple(way_back)


class OfficeHoursError(Refusal):
    """The value of ``pe.officeHours`` is not two different hours ``HH-HH``."""


@dataclass(frozen=True)
class Window:
    """Office hours: ``start`` is inside, ``end`` is outside; a start after the end wraps past midnight."""

    start: int
    end: int

    def contains(self, hour: int) -> bool:
        if self.start < self.end:
            return self.start <= hour < self.end
        return hour >= self.start or hour < self.end


def parse_window(value: str) -> Window:
    found = WINDOW.fullmatch(value)
    if found is None:
        raise OfficeHoursError("office hours", "%r is not two hours written HH-HH" % value)
    start, end = int(found.group(1)), int(found.group(2))
    if not (0 <= start <= 23 and 0 <= end <= 23) or start == end:
        raise OfficeHoursError("office hours", "%r needs two different hours between 00 and 23" % value)
    return Window(start, end)


def _run(*args: str) -> subprocess.CompletedProcess:
    """``surrogateescape`` keeps the bytes of a commit message that is not valid text, so it still compares exactly."""
    return subprocess.run(["git", *args], capture_output=True, text=True, errors="surrogateescape")


def git(*args: str) -> str:
    proc = _run(*args)
    if proc.returncode != 0:
        raise Refusal("git", "`git %s` failed: %s" % (" ".join(args), proc.stderr.strip()))
    return proc.stdout


def git_succeeds(*args: str) -> bool:
    return _run(*args).returncode == 0


def office_window() -> Window:
    proc = _run("config", "--get", "pe.officeHours")
    value = proc.stdout.strip()
    if proc.returncode != 0 or value in ("", "none"):
        raise Refusal("office hours", "no office hours set: the window comes from `git config pe.officeHours`")
    return parse_window(value)


def commits_to_re_create(base: str) -> List[str]:
    if base.startswith("-") or not git_succeeds("rev-parse", "--verify", "--quiet", base + "^{commit}"):
        raise Refusal("base", "%r is not a commit" % base)
    shas = git("rev-list", base + "..HEAD").split()
    if not shas:
        raise Refusal("range", "%s..HEAD is empty: there is nothing to re-create" % base)
    return shas


def require_hour_in_window(window: Window, now: datetime) -> None:
    if not window.contains(now.hour):
        raise Refusal("window", "it is %02d:%02d, outside the office hours" % (now.hour, now.minute))


def require_unpublished(base: str, shas: List[str]) -> None:
    """The range minus what no remote-tracking branch reaches: what is left is published and stays as it is."""
    unpublished = set(git("rev-list", "HEAD", "--not", base, "--remotes").split())
    published = [sha for sha in shas if sha not in unpublished]
    if published:
        raise Refusal(
            "published commits",
            "%d commit(s) of %s..HEAD are already on a remote-tracking branch, the first is %s"
            % (len(published), base, published[0]),
        )


def backup_tag(now: datetime) -> str:
    return "night-backup-" + now.strftime("%Y%m%d-%H%M%S")


def create_backup_tag(now: datetime, tip: str) -> str:
    tag = backup_tag(now)
    if git_succeeds("rev-parse", "--quiet", "--verify", "refs/tags/" + tag):
        raise Refusal("backup tag", "%s already exists" % tag)
    git("tag", tag, tip)
    return tag


def branch_is_unchanged(tag: str) -> Tuple[str]:
    """The way back of every failure after the tag: there is nothing to undo."""
    return ("the branch is unchanged; delete the tag with `git tag -d %s` if you do not want it" % tag,)


@contextmanager
def temporary_worktree(tag: str) -> Iterator[str]:
    """A detached worktree of ``tag`` in a folder of the script's own, removed on success and on every failure."""
    try:
        folder = tempfile.mkdtemp(prefix="recreate-night-commits-")
    except OSError as error:
        raise Refusal("worktree", "the temporary folder cannot be made: %s" % error) from error
    try:
        git("worktree", "add", "--detach", folder, tag)
        yield folder
    finally:
        _run("worktree", "remove", "--force", folder)
        _run("worktree", "prune")
        shutil.rmtree(folder, ignore_errors=True)  # what is left when `worktree add` failed before it took over


def rebase(base: str, folder: str) -> str:
    """Replay the range inside ``folder`` and return the new tip. ``rebase.updateRefs`` is pinned off because it would
    move every other local branch that points into the range, before the checks."""
    proc = _run("-c", "rebase.updateRefs=false", "-C", folder, "rebase", "--force-rebase", "--ignore-date",
                "--rebase-merges", base)
    if proc.returncode != 0:
        raise Refusal("rebase", "`git rebase` failed: %s" % proc.stderr.strip())
    return git("-C", folder, "rev-parse", "HEAD").strip()


@dataclass(frozen=True)
class Recreation:
    """What the four checks compare: the range above ``base`` on ``tag`` and on ``new``, in ``window``."""

    base: str
    tag: str
    new: str
    window: Window


def _count(base: str, ref: str) -> str:
    return git("rev-list", "--count", "%s..%s" % (base, ref))


def _messages(base: str, ref: str) -> List[str]:
    """Sorted, because commits of parallel branches get one timestamp after the rebase and git may list them in
    another order; a message lost or changed still shows."""
    return sorted(git("log", "-z", "--format=%B", "%s..%s" % (base, ref)).split("\0"))


def tree_is_the_tags(recreation: Recreation) -> bool:
    return git_succeeds("diff", "--quiet", recreation.tag, recreation.new)


def commit_count_is_the_tags(recreation: Recreation) -> bool:
    return _count(recreation.base, recreation.tag) == _count(recreation.base, recreation.new)


def messages_are_the_tags(recreation: Recreation) -> bool:
    return _messages(recreation.base, recreation.tag) == _messages(recreation.base, recreation.new)


def dates_are_in_the_window(recreation: Recreation) -> bool:
    rev_range = "%s..%s" % (recreation.base, recreation.new)
    hours = git("log", "--format=%ad %cd", "--date=format-local:%H", rev_range).split()
    return all(recreation.window.contains(int(hour)) for hour in hours)


CHECKS: Tuple[Tuple[str, Callable[[Recreation], bool]], ...] = (
    ("tree", tree_is_the_tags),
    ("commit count", commit_count_is_the_tags),
    ("messages", messages_are_the_tags),
    ("dates", dates_are_in_the_window),
)


def verify(recreation: Recreation) -> None:
    """A git error inside a check ends in the same refusal as a failed check; the branch has not moved yet."""
    for name, passes in CHECKS:
        try:
            passed = passes(recreation)
        except Refusal as refusal:
            raise Refusal(name, "the check could not run: %s" % refusal.detail) from refusal
        if not passed:
            raise Refusal(name, "the check failed after the rebase")


def move_branch(tip: str, recreation: Recreation) -> None:
    """``tip`` is the value read before the run, so a branch that moved meanwhile is refused, never overwritten."""
    proc = _run("update-ref", "-m", "recreate_night_commits", "HEAD", recreation.new, tip)
    if proc.returncode != 0:
        detail = "the branch moved while the script ran: %s" % proc.stderr.strip()
        raise Refusal("branch", detail)


def require_work_tree() -> None:
    """``--show-toplevel`` fails outside a repository and inside a bare one, where there is no branch to move."""
    git("rev-parse", "--show-toplevel")


def recreate(base: str, now: datetime) -> str:
    """Run every step in order and return the backup tag; the first failure raises ``Refusal``."""
    require_work_tree()
    window = office_window()
    shas = commits_to_re_create(base)
    require_hour_in_window(window, now)
    require_unpublished(base, shas)
    tip = git("rev-parse", "HEAD").strip()
    tag = create_backup_tag(now, tip)
    try:
        with temporary_worktree(tag) as folder:
            recreation = Recreation(base, tag, rebase(base, folder), window)
            verify(recreation)
        move_branch(tip, recreation)
    except Refusal as refusal:  # the one home of the way back: whatever fails after the tag leaves the branch alone
        raise Refusal(refusal.check, refusal.detail, branch_is_unchanged(tag)) from refusal
    return tag


def main(argv: Sequence[str]) -> int:
    if len(argv) != 1:
        print("usage: python3 <this skill's folder>/recreate_night_commits.py <base>", file=sys.stderr)
        return 2
    try:
        tag = recreate(argv[0], datetime.now())
    except Refusal as refusal:
        print("recreate_night_commits: %s" % refusal, file=sys.stderr)
        for step in refusal.way_back:
            print("way back: %s" % step, file=sys.stderr)
        return 1
    print("%s: four checks passed" % tag)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
