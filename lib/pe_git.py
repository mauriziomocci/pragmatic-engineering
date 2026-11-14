"""The one way the skill scripts and the shared code of ``lib/`` run git. The ``PreToolUse`` hook keeps its own
call: it reads only the repository root and the tracked state of ``.pe``, which ``git replace`` does not change.

``--no-replace-objects`` is always on: ``git replace`` changes what git reads for a sha, and a script that decides on
what a commit contains must read the commit itself. ``errors="surrogateescape"`` keeps the bytes of a path or a message
that is not valid text, so they still compare exactly.
"""
import subprocess


def run_git(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "--no-replace-objects", *args], capture_output=True, text=True,
                          errors="surrogateescape")
