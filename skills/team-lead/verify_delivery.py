#!/usr/bin/env python3
"""Check a worker's delivery against git, from the coordinator's checkout, before and after its review.

Usage: python3 <this skill's folder>/verify_delivery.py --integration <branch> --branch <branch> --tip <sha>
--worktree <folder> --brief <file> [--reviewed <sha>] [--red <command>]

Every revision (``--integration``, ``--branch``, ``--tip``, ``--reviewed``) is a full object id of 40 or 64 hex digits
that is a commit, or else a branch name, which is read only as the exact ref ``refs/heads/<name>`` (the prefix is
optional) with ``git show-ref --verify``, which also refuses a name that is no valid ref. A tag, ``refs/<name>``, ``HEAD`` or ``w~1`` is never read in its place:
git's own lookup tries a tag and ``refs/<name>`` before a branch, and the worker can create them. Every git call runs
with ``--no-replace-objects``, so ``git replace`` cannot change what a commit contains.

``--tip`` is the tip the worker declared in its report, ``--worktree`` is the worker's worktree and ``--brief`` the
brief the worker was given: its ``OWNED: <glob>`` lines (one or more) name the files the worker may change, matched
with ``fnmatchcase`` on the repository paths, where ``*`` also crosses ``/``.

Exit 1, a refusal, with every reason on standard error: the branch does not point to the declared tip; the worktree
is not clean (``git status --porcelain --untracked-files=all`` prints something); a file the delivery changed is
outside every ``OWNED:`` line. The files are those of ``git diff --no-renames --name-only <merge base> <tip>``, where
the merge base is that of the integration and the tip, so a delivery the integration has overtaken is judged on its
own changes (without ``--no-renames`` a rename names only its destination, and a file moved in from another worker's
area would pass).

With ``--red``, the command is the project's test command for the worker's tests, split with ``shlex.split`` and run
without a shell, from the root of two temporary worktrees; a path in it is written with ``/`` because a backslash is
an escape. The test files are the files of that diff (``--diff-filter=d``, so none that the delivery deleted) that
match a ``TESTS: <glob>`` line of the brief. The command must exit 0 at the delivery tip and non-zero at the
integration tip once only those test files of the tip are copied to it: that is the red the worker saw. A refusal
carries the last 20 lines of the command's output. This is the one place where the script writes: it adds the two
temporary worktrees and removes them, and runs ``git worktree prune``, which drops the records of every worktree of
the repository whose folder is gone. The command runs the delivery's own code and inherits the environment of the
session that runs the script; the script enforces none of the resources of the brief, so the coordinator sets them in
the command (``env NAME=value <command>``) or in the environment.

Exit 3, a review is needed, only when nothing is refused. The commits above ``--reviewed`` and not in the integration
(``git rev-list <reviewed>..<tip> --not <integration>``, because the integration's own history was read when it was
merged) are the ones to read. Without ``--reviewed`` (it then equals ``--integration``) only a merge whose
``git show --remerge-diff`` is not empty counts, that is, a merge whose conflict resolution nobody has read. With
``--reviewed`` every commit counts, listed by sha, except a merge with an empty remerge diff.

Exit 2, a usage error: a missing or unknown argument, a brief with no ``OWNED:`` line, a value that is neither a
commit id nor a branch of the repository, a ``--red`` command that is empty, has an unbalanced quote or cannot start,
a folder or a file that is not there, a git command that fails. Exit 0: accepted.

What it does not do: read the numbers of the worker's suite, or check that the integration tip is an ancestor of
the delivery; the reviewer and ``git merge --ff-only`` do that. Every ``git show`` and ``git diff`` here carries the
fixed options the reviewer's own reads carry, so a driver or a conversion filter in the user's configuration cannot
hide a change.
"""
import argparse
import fnmatch
import re
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from pe_git import run_git  # noqa: E402
from pe_worktree import WorktreeError, temporary_worktree  # noqa: E402  (the plugin's shared code, found from this file)

READ_FLAGS = ("--no-color", "--no-ext-diff", "--no-textconv", "--no-relative", "--ignore-submodules=none")
OBJECT_ID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
HEADS = "refs/heads/"
OUTPUT_LINES = 20


class UsageError(Exception):
    """The call is wrong, or git could not answer: nothing was checked."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # argparse would exit 2 itself, without the script's prefix
        raise UsageError(message)


@dataclass(frozen=True)
class Request:
    integration: str
    branch: str
    branch_tip: str
    tip: str
    worktree: str
    owned: Tuple[str, ...]
    tests: Tuple[str, ...]
    reviewed: str
    after_review: bool
    red: Optional[Tuple[str, ...]]


def git(*args: str) -> str:
    proc = run_git(*args)
    if proc.returncode != 0:
        raise UsageError("`git %s` failed: %s" % (" ".join(args), proc.stderr.strip()))
    return proc.stdout


def branch_head(option: str, value: str) -> str:
    """The commit that the branch ``value`` points to. A value is only ever read as ``refs/heads/<name>`` (the prefix is
    optional) and looked up as that exact ref with ``git show-ref --verify``, which refuses a name that is no valid ref
    (``w~1``, ``..``, ``@{1}``): git's own lookup of a bare name tries a tag, or ``refs/<name>``, before a branch, and
    a worker can create both."""
    ref = HEADS + (value[len(HEADS):] if value.startswith(HEADS) else value)
    found = run_git("show-ref", "--verify", "--hash", ref)
    if found.returncode != 0:
        raise UsageError("%s %r is not a branch of this repository" % (option, value))
    return found.stdout.strip()


def commit_of(option: str, value: str) -> str:
    """A full object id (40 or 64 hex digits) that is a commit, or else a branch name; nothing else reaches git."""
    if not OBJECT_ID.fullmatch(value):
        return branch_head(option, value)
    found = run_git("rev-parse", "--verify", "--quiet", value + "^{commit}")
    if found.returncode != 0:
        raise UsageError("%s %r is not a commit of this repository" % (option, value))
    return found.stdout.strip()


def brief_globs(lines: Sequence[str], key: str) -> Tuple[str, ...]:
    globs = (line[len(key):].strip() for line in lines if line.startswith(key))
    return tuple(glob for glob in globs if glob)


def read_brief(brief: str) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """The ``OWNED:`` and the ``TESTS:`` globs of the brief."""
    try:
        lines = Path(brief).read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise UsageError("the brief cannot be read: %s" % error) from error
    owned = brief_globs(lines, "OWNED:")
    if not owned:
        raise UsageError("the brief has no `OWNED:` line")
    return owned, brief_globs(lines, "TESTS:")


def split_command(command: str) -> Tuple[str, ...]:
    """The test command as the argument list that runs, without a shell: quotes group words, a backslash escapes."""
    try:
        words = tuple(shlex.split(command))
    except ValueError as error:
        raise UsageError("--red %r cannot be read as a command: %s" % (command, error)) from error
    if not words:
        raise UsageError("--red is empty")
    return words


def parse(argv: Sequence[str]) -> Request:
    parser = _Parser(prog="verify_delivery", add_help=False)
    for option in ("integration", "branch", "tip", "worktree", "brief"):
        parser.add_argument("--" + option, required=True)
    parser.add_argument("--reviewed")
    parser.add_argument("--red")
    args = parser.parse_args(argv)
    if not Path(args.worktree).is_dir():
        raise UsageError("--worktree %r is not a folder" % args.worktree)
    integration = commit_of("--integration", args.integration)
    reviewed = commit_of("--reviewed", args.reviewed) if args.reviewed else integration
    owned, tests = read_brief(args.brief)
    if args.red is not None and not tests:
        raise UsageError("--red needs a `TESTS:` line in the brief")
    return Request(integration, args.branch, branch_head("--branch", args.branch), commit_of("--tip", args.tip),
                   args.worktree, owned, tests, reviewed,
                   args.reviewed is not None, None if args.red is None else split_command(args.red))


def own_changes(request: Request, *options: str) -> List[str]:
    """The files the delivery changed since it left the integration: the diff from their merge base to the tip, so a
    delivery that the integration has overtaken is not blamed for another worker's files. ``-z`` keeps a path with a
    space or a non-ASCII letter as it is, instead of git's quoted form."""
    base = git("merge-base", request.integration, request.tip).strip()
    out = git("diff", *READ_FLAGS, "--no-renames", "--name-only", "-z", *options, base, request.tip)
    return [path for path in out.split("\0") if path]


def matches(path: str, globs: Sequence[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, glob) for glob in globs)


def branch_problems(request: Request) -> List[str]:
    if request.branch_tip == request.tip:
        return []
    return ["branch %s points to %s, not to the declared tip %s" % (request.branch, request.branch_tip, request.tip)]


def worktree_problems(request: Request) -> List[str]:
    dirty = git("-C", request.worktree, "status", "--porcelain", "--untracked-files=all")
    return ["the worktree is not clean:\n%s" % dirty.rstrip()] if dirty.strip() else []


def area_problems(request: Request) -> List[str]:
    outside = [path for path in own_changes(request) if not matches(path, request.owned)]
    return ["%d file(s) outside the OWNED lines of the brief: %s" % (len(outside), ", ".join(outside))] if outside else []


def run_test_command(request: Request, revision: str, test_files: Sequence[str]) -> subprocess.CompletedProcess:
    """The test command in a temporary worktree of ``revision``, after the delivery's own ``test_files`` are copied
    into it; its output is kept, standard error merged into standard output."""
    try:
        with temporary_worktree(revision, "verify-delivery-") as folder:
            if test_files:
                git("-C", folder, "checkout", request.tip, "--", *test_files)
            return subprocess.run(request.red, cwd=folder, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, errors="replace")
    except WorktreeError as error:
        raise UsageError(str(error)) from error
    except OSError as error:  # a program that is not there
        raise UsageError("the test command cannot start: %s" % error) from error


def with_output_tail(reason: str, proc: subprocess.CompletedProcess) -> str:
    """The reason goes to the worker, and a reason without the test that failed names nothing to fix."""
    tail = "\n".join(proc.stdout.splitlines()[-OUTPUT_LINES:])
    return "%s; the last %d lines of its output:\n%s" % (reason, OUTPUT_LINES, tail) if tail else reason


def red_problems(request: Request) -> List[str]:
    if request.red is None:
        return []
    test_files = [path for path in own_changes(request, "--diff-filter=d") if matches(path, request.tests)]
    if not test_files:
        return ["no changed test file matches a `TESTS:` line of the brief"]
    problems = []
    on_base = run_test_command(request, request.integration, test_files)
    if on_base.returncode == 0:
        problems.append(with_output_tail("the test command passes on the integration tip with the delivery's test "
                                         "files: they were never red", on_base))
    at_tip = run_test_command(request, request.tip, ())
    if at_tip.returncode != 0:
        problems.append(with_output_tail("the test command fails at the delivery tip", at_tip))
    return problems


def refusals(request: Request) -> List[str]:
    return branch_problems(request) + worktree_problems(request) + area_problems(request) + red_problems(request)


def unread_commits(request: Request) -> List[str]:
    """What the reviewer has not read: above the reviewed tip and not in the integration (the integration's own history
    was read when it was merged), every commit after a review, and before one only a merge whose resolution kept or
    dropped something, that is, whose remerge diff is not empty."""
    above = ("%s..%s" % (request.reviewed, request.tip), "--not", request.integration)
    merges = set(git("rev-list", "--merges", *above).split())

    def unread(sha: str) -> bool:
        if sha not in merges:
            return request.after_review
        return bool(git("show", "--format=", *READ_FLAGS, "--remerge-diff", sha).strip())

    return [sha for sha in git("rev-list", *above).split() if unread(sha)]


def main(argv: Sequence[str]) -> int:
    try:
        request = parse(argv)
        problems = refusals(request)
        if problems:
            for problem in problems:
                print("verify_delivery: refused: %s" % problem, file=sys.stderr)
            return 1
        unread = unread_commits(request)
    except UsageError as error:
        print("verify_delivery: %s" % error, file=sys.stderr)
        return 2
    if unread:
        print("verify_delivery: review needed: not read by the reviewer: %s" % ", ".join(unread), file=sys.stderr)
        return 3
    print("verify_delivery: accepted %s" % request.tip)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
