#!/usr/bin/env python3
"""PreToolUse hook of the pragmatic-engineering plugin: the closed interface of blunt-reviewer, enforced.

1. It denies an Agent call to pragmatic-engineering:blunt-reviewer whose
   prompt is not exactly one line of the agent's closed grammar
   (agents/blunt-reviewer.md, "The prompt you accept"), so whoever launches
   the reviewer cannot steer it through the prompt; the reason quotes the
   grammar, so the main session can relaunch with the right line.
2. Inside that agent (agent_type), it denies every Bash command that is not
   one of the git read forms of "How you read", written exactly as there,
   and every Write outside <toplevel>/.pe/, both paths compared after
   os.path.realpath so that a committed .pe symlink cannot lead out. The
   forms only read, with one exception: --remerge-diff redoes each merge, so
   a merge driver defined in a git configuration (merge.<name>.driver) runs
   during that read.

Both checks match closed shapes only: anything a pattern does not describe is
denied, so a gap in a pattern can only make the reviewer stricter. Every other
call, of the main session or of any other agent, gets no decision and goes
through the normal permission flow.

Exit 2 denies, with the reason on stderr, as tools/dev_guard.py does; exit 0
with no output is no decision. A malformed input is no decision. A failure
after the input is read denies when the call concerns the reviewer and is no
decision otherwise, so a bug here can never block another tool. The hook is
registered with "onFailure": "continue": a hook that cannot start or times out
lets the call through, and the reviewer's limits are then declared only, as
they were before this hook.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Dict, Optional

REVIEWER = "pragmatic-engineering:blunt-reviewer"
GRAMMAR = "<base>..<tip> [round=1|2] [full=<path>,...]"
# A sha, HEAD, HEAD~n or a branch name: it starts with a letter or digit, so git never reads it as an option,
# and a dot is always followed by a name character, so ".." and "..." cannot hide inside it.
_REVISION = r"[A-Za-z0-9](?:\.?[A-Za-z0-9/_-])*(?:~[0-9]+)?"
# A repository-relative path: segments joined by "/", none empty, "." or "..", so it cannot be absolute or climb out.
_SEGMENT = r"(?!\.\.?(?![A-Za-z0-9._+-]))[A-Za-z0-9._+-]+"
_PATH = r"%s(?:/%s)*" % (_SEGMENT, _SEGMENT)
_RANGE = r"%s\.\.%s" % (_REVISION, _REVISION)
_PROMPT = re.compile(r"%s(?: round=[12])?(?: full=%s(?:,%s)*)?" % (_RANGE, _PATH, _PATH))
# The read-only git commands of agents/blunt-reviewer.md, one per call: no pipe, redirect or other shell syntax fits.
_PATCH_FLAGS = "--no-color --no-ext-diff --no-textconv --no-relative --ignore-submodules=none"
_READ_FORMS = re.compile("(?:%s)" % "|".join((
    r"git rev-parse --show-toplevel",
    r'git rev-parse --verify "%s\^\{commit\}"' % _REVISION,
    r"git merge-base --is-ancestor %s %s" % (_REVISION, _REVISION),
    r"git log --no-color --oneline(?: --merges)? %s" % _RANGE,
    r"git show %s(?: --stat --patch)? %s(?: -- %s)?" % (_PATCH_FLAGS, _REVISION, _PATH),
    r"git show %s --remerge-diff %s(?: -- %s)?" % (_PATCH_FLAGS, _REVISION, _PATH),
    r"git diff %s %s(?: -- %s)?" % (_PATCH_FLAGS, _RANGE, _PATH),
    r"git show %s %s:%s" % (_PATCH_FLAGS, _REVISION, _PATH),
)))
_PROMPT_REASON = (
    "blunt-reviewer accepts exactly one line in its closed grammar, `%s`, and nothing else: revisions are shas, HEAD, "
    "HEAD~n or branch names (letters, digits, / . _ -), and full= takes repository-relative paths separated by "
    "commas, without spaces; relaunch it with only that line" % GRAMMAR
)
_COMMAND_REASON = (
    "blunt-reviewer runs only the read-only git commands of its definition (agents/blunt-reviewer.md, \"How you "
    "read\"), written exactly as there, one per call, with no pipe, redirect or other shell syntax"
)
_WRITE_REASON = "blunt-reviewer writes only under .pe/ at the repository root (git rev-parse --show-toplevel)"
GIT_TIMEOUT = 5.0  # seconds; the hook's own timeout in hooks/hooks.json is longer


def _launches_reviewer(payload: Any) -> bool:
    if not isinstance(payload, dict) or payload.get("tool_name") != "Agent":
        return False
    tool_input = payload.get("tool_input")
    return isinstance(tool_input, dict) and tool_input.get("subagent_type") == REVIEWER


def _prompt_problem(prompt: Any) -> Optional[str]:
    if isinstance(prompt, str) and _PROMPT.fullmatch(prompt):
        return None
    return _PROMPT_REASON


def _runs_in_reviewer(payload: Any) -> bool:
    return isinstance(payload, dict) and payload.get("agent_type") == REVIEWER


def _command_problem(tool_input: Dict[str, Any], cwd: Any) -> Optional[str]:
    command = tool_input.get("command")
    if isinstance(command, str) and _READ_FORMS.fullmatch(command):
        return None
    return _COMMAND_REASON


def _toplevel(cwd: str) -> Optional[str]:
    try:
        proc = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):  # no git, or git hangs
        return None
    return proc.stdout.strip() if proc.returncode == 0 and proc.stdout.strip() else None


def _write_problem(tool_input: Dict[str, Any], cwd: Any) -> Optional[str]:
    path = tool_input.get("file_path")
    top = _toplevel(cwd) if isinstance(cwd, str) and cwd else None
    if not (isinstance(path, str) and path and top):
        return _WRITE_REASON
    allowed = Path(os.path.realpath(top)) / ".pe"
    target = Path(os.path.realpath(os.path.join(cwd, path)))
    return None if allowed in target.parents else _WRITE_REASON


# The reviewer's tools that the hook is registered for; its others (Read, Grep, Glob) only read.
_REVIEWER_TOOL_CHECKS: Dict[str, Callable[[Dict[str, Any], Any], Optional[str]]] = {
    "Bash": _command_problem,
    "Write": _write_problem,
}


def decide(payload: Any) -> Optional[str]:
    """Return why the tool call must be denied, or None for no decision."""
    if _launches_reviewer(payload):
        return _prompt_problem(payload["tool_input"].get("prompt"))
    check = _REVIEWER_TOOL_CHECKS.get(payload.get("tool_name")) if _runs_in_reviewer(payload) else None
    if check is None:
        return None
    tool_input = payload.get("tool_input")
    return check(tool_input if isinstance(tool_input, dict) else {}, payload.get("cwd"))


def main() -> int:
    try:
        # Bytes, so json decodes the UTF-8 that Claude Code sends; text would use the locale's code page (cp1252 on
        # Windows), which turns some valid input into a decode error.
        payload = json.loads(sys.stdin.buffer.read())
    except (OSError, ValueError, RecursionError):  # not JSON, not UTF-8, or nested too deeply to parse
        return 0
    try:
        reason = decide(payload)
    except Exception as exc:  # taste-exempt: a crash must deny the reviewer's call and leave every other one alone
        concerns_reviewer = _launches_reviewer(payload) or _runs_in_reviewer(payload)
        reason = "check failed (%s: %s)" % (exc.__class__.__name__, exc) if concerns_reviewer else None
    if reason:
        print("pragmatic-engineering: " + reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
