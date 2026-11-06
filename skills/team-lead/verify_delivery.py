#!/usr/bin/env python3
"""Check a worker's delivery against git, from the coordinator's checkout, before and after its review.

Usage: python3 <this skill's folder>/verify_delivery.py --integration <rev> --branch <branch> --tip <sha>
--worktree <folder> --brief <file> [--reviewed <sha>] [--red <command>]

``--integration`` and ``--reviewed`` are a branch, a tag, a full ref name or a sha; a bare name that is both a branch
and a tag is a usage error, because git would read the tag and the worker can create one. ``--branch`` is always read
as ``refs/heads/<branch>``.

``--tip`` is the tip the worker declared in its report, ``--worktree`` is the worker's worktree and ``--brief`` the
brief the worker was given: its ``OWNED: <glob>`` lines (one or more) name the files the worker may change, matched
with ``fnmatchcase`` on the repository paths, where ``*`` also crosses ``/``.

Exit 1, a refusal, with every reason on standard error: the branch does not point to the declared tip; the worktree
is not clean (``git status --porcelain --untracked-files=all`` prints something); a file of
``git diff --no-renames --name-only <integration> <tip>`` is outside every ``OWNED:`` line (without ``--no-renames``
a rename names only its destination, and a file moved in from another worker's area would pass).

With ``--red``, the command is the project's test command for the worker's tests, split with ``shlex.split`` and run
without a shell, from the root of two temporary worktrees. The test files are the files of the diff
(``--diff-filter=d``, so none that the delivery deleted) that match a ``TESTS: <glob>`` line of the brief. The command
must exit 0 at the delivery tip and non-zero at the integration tip once only those test files of the tip are copied
to it: that is the red the worker saw. The command runs with the resources the brief names (a database, a port);
this script chooses none.

Exit 3, a review is needed, only when nothing is refused: a merge of ``git rev-list --merges <reviewed>..<tip>``
whose ``git show --remerge-diff`` is not empty, that is, a merge whose conflict resolution nobody has read.
``--reviewed`` is the tip the reviewer last read and defaults to ``--integration``.

Exit 2, a usage error: a missing or unknown argument, a brief with no ``OWNED:`` line, a revision that is not a
commit or that begins with ``-``, a folder or a file that is not there. Exit 0: accepted.

What it does not do: read the numbers of the worker's suite, or check that the integration tip is an ancestor of
the delivery; the reviewer and ``git merge --ff-only`` do that. Every ``git show`` and ``git diff`` here carries the
fixed options the reviewer's own reads carry, so a driver or a conversion filter in the user's configuration cannot
hide a change.
"""
import argparse
import fnmatch
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from pe_worktree import WorktreeError, temporary_worktree  # noqa: E402  (the plugin's shared code, found from this file)

READ_FLAGS = ("--no-color", "--no-ext-diff", "--no-textconv", "--no-relative", "--ignore-submodules=none")
NOT_A_REVISION = "not a commit of this repository, or it begins with a dash"


class UsageError(Exception):
    """The call is wrong, or git could not answer: nothing was checked."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # argparse would exit 2 itself, without the script's prefix
        raise UsageError(message)


@dataclass(frozen=True)
class Request:
    integration: str
    branch: str
    tip: str
    worktree: str
    owned: Tuple[str, ...]
    tests: Tuple[str, ...]
    reviewed: str
    red: Optional[str]


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, errors="surrogateescape")


def git(*args: str) -> str:
    proc = _run(*args)
    if proc.returncode != 0:
        raise UsageError("`git %s` failed: %s" % (" ".join(args), proc.stderr.strip()))
    return proc.stdout


def resolve(revision: str) -> Optional[str]:
    """The commit ``revision`` names, or ``None``; a name that begins with a dash is never passed to git."""
    if revision.startswith("-"):
        return None
    proc = _run("rev-parse", "--verify", "--quiet", revision + "^{commit}")
    return proc.stdout.strip() if proc.returncode == 0 else None


def require_unambiguous(option: str, name: str) -> None:
    """Git reads a bare name as a tag before a branch, and the worker can create a tag: a name that is both is refused
    instead of guessed. A full ref name (``refs/heads/<name>``) or a sha is never ambiguous."""
    refs = ["refs/heads/" + name, "refs/tags/" + name]
    if all(resolve(ref) for ref in refs):
        raise UsageError("%s %r is both a branch and a tag (%s and %s): write the full ref name"
                         % (option, name, refs[0], refs[1]))


def commit_of(option: str, revision: str) -> str:
    require_unambiguous(option, revision)
    found = resolve(revision)
    if found is None:
        raise UsageError("%s %r is %s" % (option, revision, NOT_A_REVISION))
    return found


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


def parse(argv: Sequence[str]) -> Request:
    parser = _Parser(prog="verify_delivery", add_help=False)
    for option in ("integration", "branch", "tip", "worktree", "brief"):
        parser.add_argument("--" + option, required=True)
    parser.add_argument("--reviewed")
    parser.add_argument("--red")
    args = parser.parse_args(argv)
    if args.branch.startswith("-"):
        raise UsageError("--branch %r begins with a dash" % args.branch)
    if not Path(args.worktree).is_dir():
        raise UsageError("--worktree %r is not a folder" % args.worktree)
    integration = commit_of("--integration", args.integration)
    reviewed = commit_of("--reviewed", args.reviewed) if args.reviewed else integration
    owned, tests = read_brief(args.brief)
    if args.red is not None and not tests:
        raise UsageError("--red needs a `TESTS:` line in the brief")
    return Request(integration, args.branch, commit_of("--tip", args.tip), args.worktree, owned, tests, reviewed,
                   args.red)


def changed_files(integration: str, tip: str, *options: str) -> List[str]:
    """``-z`` keeps a path with a space or a non-ASCII letter as it is, instead of git's quoted form."""
    out = git("diff", *READ_FLAGS, "--no-renames", "--name-only", "-z", *options, integration, tip)
    return [path for path in out.split("\0") if path]


def matches(path: str, globs: Sequence[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, glob) for glob in globs)


def branch_problems(request: Request) -> List[str]:
    found = resolve("refs/heads/" + request.branch)
    if found == request.tip:
        return []
    return ["branch %s points to %s, not to the declared tip %s" % (request.branch, found or "nothing", request.tip)]


def worktree_problems(request: Request) -> List[str]:
    dirty = git("-C", request.worktree, "status", "--porcelain", "--untracked-files=all")
    return ["the worktree is not clean:\n%s" % dirty.rstrip()] if dirty.strip() else []


def area_problems(request: Request) -> List[str]:
    outside = [path for path in changed_files(request.integration, request.tip) if not matches(path, request.owned)]
    return ["%d file(s) outside the OWNED lines of the brief: %s" % (len(outside), ", ".join(outside))] if outside else []


def exit_code_in(request: Request, revision: str, test_files: Sequence[str]) -> int:
    """The exit code of the test command in a temporary worktree of ``revision``, after the delivery's own
    ``test_files`` are copied into it."""
    try:
        argv = shlex.split(request.red or "")
        with temporary_worktree(revision, "verify-delivery-") as folder:
            if test_files:
                git("-C", folder, "checkout", request.tip, "--", *test_files)
            return subprocess.run(argv, cwd=folder, capture_output=True).returncode
    except WorktreeError as error:
        raise UsageError(str(error)) from error
    except OSError as error:  # an empty command, a program that is not there
        raise UsageError("the test command cannot start: %s" % error) from error


def red_problems(request: Request) -> List[str]:
    if request.red is None:
        return []
    test_files = [path for path in changed_files(request.integration, request.tip, "--diff-filter=d")
                  if matches(path, request.tests)]
    if not test_files:
        return ["no changed test file matches a `TESTS:` line of the brief"]
    problems = []
    if exit_code_in(request, request.integration, test_files) == 0:
        problems.append("the test command passes on the integration tip with the delivery's test files: they were never red")
    if exit_code_in(request, request.tip, ()) != 0:
        problems.append("the test command fails at the delivery tip")
    return problems


def refusals(request: Request) -> List[str]:
    return branch_problems(request) + worktree_problems(request) + area_problems(request) + red_problems(request)


def unread_resolutions(request: Request) -> List[str]:
    """The merges above the reviewed tip whose resolution kept or dropped something: the remerge diff is not empty."""
    merges = git("rev-list", "--merges", "%s..%s" % (request.reviewed, request.tip)).split()
    return [merge for merge in merges if git("show", "--format=", *READ_FLAGS, "--remerge-diff", merge).strip()]


def main(argv: Sequence[str]) -> int:
    try:
        request = parse(argv)
        problems = refusals(request)
        if problems:
            for problem in problems:
                print("verify_delivery: refused: %s" % problem, file=sys.stderr)
            return 1
        unread = unread_resolutions(request)
    except UsageError as error:
        print("verify_delivery: %s" % error, file=sys.stderr)
        return 2
    if unread:
        print("verify_delivery: review needed: the resolution of merge %s is not in the reviewed range"
              % ", ".join(unread), file=sys.stderr)
        return 3
    print("verify_delivery: accepted %s" % request.tip)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
