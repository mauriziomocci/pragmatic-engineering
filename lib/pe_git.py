"""The one way the skill scripts and the shared code of ``lib/`` run git. The ``PreToolUse`` hook keeps its own
call: it reads only the repository root and the tracked state of ``.pe``, which ``git replace`` does not change.

``--no-replace-objects`` is always on: ``git replace`` changes what git reads for a sha, and a script that decides on
what a commit contains must read the commit itself. ``errors="surrogateescape"`` keeps the bytes of a path or a message
that is not valid text, so they still compare exactly.
"""
import re
import subprocess
from typing import List, Optional

HEADS = "refs/heads/"
OBJECT_ID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")  # a full object id, SHA-1 or SHA-256


class GitError(Exception):
    """A git command failed; the message names the command and gives git's own reason."""


def run_git(*args: str, input: Optional[str] = None) -> subprocess.CompletedProcess:
    """``input`` is the standard input, for a command that reads its names there, as ``cat-file --batch-check`` does."""
    return subprocess.run(["git", "--no-replace-objects", *args], input=input, capture_output=True, text=True,
                          errors="surrogateescape")


def output_lines(output: str) -> List[str]:
    """The lines of git's output, split on newlines only: ``str.splitlines`` also splits on line breaks of Unicode,
    such as U+2028 and U+0085, which git takes in a branch name or a path."""
    return [line for line in output.split("\n") if line]


def git(*args: str, input: Optional[str] = None) -> str:
    """The standard output of a git command that must succeed."""
    proc = run_git(*args, input=input)
    if proc.returncode != 0:
        raise GitError("`git %s` failed: %s" % (" ".join(args), proc.stderr.strip()))
    return proc.stdout
