"""A detached worktree of a revision, in a folder of its own, shared by the scripts that need one.

It lives in ``lib/`` because two skills use it and a skill never imports from another skill's folder.
"""
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from typing import Iterator


class WorktreeError(Exception):
    """The temporary worktree could not be made; the message says why."""


def _git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, errors="replace")


@contextmanager
def temporary_worktree(revision: str, prefix: str) -> Iterator[str]:
    """A detached worktree of ``revision`` in the repository of the current folder, in a new folder whose name starts
    with ``prefix``; it is removed on success and on every failure."""
    try:
        folder = tempfile.mkdtemp(prefix=prefix)
    except OSError as error:
        raise WorktreeError("the temporary folder cannot be made: %s" % error) from error
    try:
        added = _git("worktree", "add", "--detach", folder, revision)
        if added.returncode != 0:
            raise WorktreeError("`git worktree add` failed: %s" % added.stderr.strip())
        yield folder
    finally:
        _git("worktree", "remove", "--force", folder)
        _git("worktree", "prune")
        shutil.rmtree(folder, ignore_errors=True)  # what is left when `worktree add` failed before it took over
