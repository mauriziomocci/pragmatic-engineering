#!/usr/bin/env python3
"""Project PreToolUse hook of the plugin repository (step zero).

Registered in the maintainer's .claude/settings.local.json, outside git, and
run from the copy that tools/install_dev_hooks.py keeps under the git
directory. It keeps the agent from skipping or switching off the privacy
pre-push (shared filters in lib/pe_guard/filters.py), blocks MCP tools that
write to a remote (they bypass the pre-push), and runs the privacy check on
the text of pull and merge requests when they are opened, edited or merged and,
for gh and glab commands, when they are commented, reviewed or closed.

Exit 2 blocks the tool, with the reason on stderr; exit 0 lets it run. A tool
this hook does not know passes. An input without a tool name, or a known tool
without its usual fields, is checked as text. Any failure while loading the
checks or checking a known tool blocks, because Claude Code does not block on
a hook that errors in any other way or times out.

The text of a pull request is read only where it is written: in the command,
or in an absolute regular file named by --body-file or -F. The hook models no
shell grammar, so what the shell would fill in at run time blocks, with the
hint to pass an absolute --body-file path: a here-document or a here-string
(any <<), standard input as the body file (-, /dev/stdin, /dev/fd/0), a command
or process substitution, a variable, an ANSI-C or locale string ($'...',
$"..."), a tilde or zsh's =command, also after empty quotes. A body file blocks
too when it is attached to its option (-Fbody.md), named by a relative path
after a cd, or a device, a pipe, a folder or a file under /dev or /proc; when
its name, or just its last component, is written elsewhere in the command,
because the hook reads the file before the command runs and a cp or a redirect
in the same command would leave it with a text the command no longer sends; and
when the command names more than ten different body files, each of which is
searched for in the whole text. A backslash-newline is removed before the
command is checked, as the shell removes it; the privacy scan reads the command
both ways, because inside single quotes the shell keeps the pair.

Open limits, declared and pinned in OPEN_FORMS of tests/test_dev_guard.py:

- a folder change made by a program other than cd or pushd (``env -C sub gh pr
  create --body-file body.md``) leaves a relative body file read from the
  folder the hook starts in;
- an option name that is quoted or escaped (``'-F' -``, ``"--body-file" -``,
  ``--body\\-file -``) is not read as the option, so the standard input given
  to it is not seen;
- gh fills a pull request from places the command does not show (flags of gh
  2.102.0, read in the help of ``gh pr create``, ``edit`` and ``comment``, not
  run against GitHub): ``--fill``, ``--fill-first`` and ``--fill-verbose`` take
  the commit messages, which the pre-push checks when they are pushed;
  ``--template`` takes the starting body from the file it names, ``--attach``
  uploads the files it names and appends them to the body (``gh pr edit`` and
  ``gh pr comment`` have it too), ``--recover`` takes the input of an earlier
  failed run, ``--editor`` the text typed in an editor and ``--web`` the text
  typed in the browser (``gh pr comment`` has both).
"""
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    from pe_guard import filters
    import privacy_check
except Exception as exc:  # fail closed: a broken shared module must block, not let every tool run
    print("dev_guard: cannot load the checks (%s: %s); blocking to stay safe" % (exc.__class__.__name__, exc),
          file=sys.stderr)
    sys.exit(2)

GIT_TIMEOUT = 5.0  # seconds for each git call: the hook has 15, and a hook that times out does not block
BODY_HINT = (
    "write the body to a file and pass --body-file <path> with an absolute path outside your home folder, such as "
    "/tmp/pr-body.md (a home path in the command is blocked too)"
)
_HERE_DOCUMENT_REASON = (
    "the pull request command holds a here-document or a here-string (<<): this hook reads only text written in the "
    "command or in a body file, and the shell fills the input in at run time; " + BODY_HINT
)
_EXPANSION_REASON = (
    "the pull request command holds a substitution, a shell variable or another expansion (a tilde, =command, "
    "<(...), $'...'), whose value this hook cannot check; " + BODY_HINT
    + "; spell out the title, branch and other values in the command"
)
_ATTACHED_REASON = (
    "the pull request command passes a body file attached to a short option (-Fbody.md, -dF body.md), which this "
    "hook cannot locate; " + BODY_HINT + ", written as a separate word"
)
_STDIN_REASON = (
    "the pull request body comes from standard input (-, /dev/stdin, /dev/fd/0), which this hook cannot read; "
    + BODY_HINT
)
_CD_REASON = (
    "the command changes folder and names a body file with a relative path, which this hook would read from "
    "another folder; " + BODY_HINT
)
_SPECIAL_FILE_REASON = (
    "the pull request body file is a device, a pipe, a folder or a file under /dev or /proc, which this hook "
    "cannot read as the command would; " + BODY_HINT
)
_STALE_FILE_REASON = (
    "the command writes or names the body file elsewhere, and this hook reads the file before the command runs; "
    "write it in a separate step; " + BODY_HINT
)
# Each body file name is searched for in the whole command, so the cost grows with names times text: 40000 different
# names in a 490 KB command took 4.7 s. A pull request command reads one body file, so a count this high is no
# hurried form.
_MAX_BODY_FILES = 10
_MANY_FILES_REASON = (
    "the command names more than %d different body files, and this hook checks each one against the rest of the "
    "command; run one pull request command at a time; " % _MAX_BODY_FILES + BODY_HINT
)
_STDIN_NAMES = ("-", "/dev/stdin", "/dev/fd/0")  # body file names that mean standard input
# The option and the name given to --body-file or -F as the shell passes it: the whole word, quoted parts and all, up
# to a blank or an operator character (-; is standard input, then a separator), so that "-"x is the file -x and ""- is
# standard input; filters.remove_quotes then takes the quotes off.
_BODY_FILE = re.compile(
    r"(?P<option>--body-file|(?<!\S)-F)(?:\s+|=)(?P<name>(?:\"[^\"]*\"|'[^']*'|[^\s\"';&|<>()])+)"
)
# Folders of devices and of process data: a body file there is a stream (the hook would read its own input, or wait)
# or a file of another process, never the text the command sends.
_SPECIAL_FOLDERS = ("/dev", "/proc")
# A body file the pattern above does not read: -F attached to its value (-Fbody.md) or bundled with other short
# options (-dF body.md). A short option word with an F in it also catches a value that happens to hold one (-tFix),
# an accepted over-block.
_ATTACHED_BODY_FILE = re.compile(r"(?<!\S)-(?!-)(?!F(?:\s|=|$))\S*?F")
_CD = re.compile(r"\b(?:cd|pushd)\b")
# Text the shell produces at run time or reads otherwise than as written: a command, arithmetic or parameter
# substitution ($(, ${, $name, $1, $?), a backtick, an ANSI-C or locale string ($' and $"), a process substitution
# (zsh also writes =(...)), zsh's =command (the path of the command) and a tilde at the start of a word or after = or :
# (the home folder). zsh ignores empty quotes in front of an = or a tilde, so those count after them too.
_EXPANSION = re.compile(
    r"\$[({'\"A-Za-z_0-9@*#?$!-]|`|[<>]\(|(?<!\S)=\S|(?<![^\s=:])~|(?<!\S)(?:''|\"\")+[=~]"
)


def _strings(value: Any) -> List[str]:
    """Every string inside a JSON value, depth first."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for item in value.values() for s in _strings(item)]
    if isinstance(value, list):
        return [s for item in value for s in _strings(item)]
    return []


def shell_text(payload: Dict[str, Any]) -> str:
    """The command of a shell tool, or every string of the hook input when that field is missing."""
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if isinstance(command, str):
        return command
    return "\n".join(_strings(payload))


def content_after_edit(path: Path, old: str, new: str, replace_all: bool) -> Optional[str]:
    """The file as an Edit would leave it.

    When ``old`` is not in the file the Edit tool fails and writes nothing;
    the current text plus ``new`` is returned so the check errs on the safe
    side. None means the file exists but cannot be read.
    """
    try:
        current = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return new
    except (OSError, UnicodeDecodeError):
        return None
    if old and old in current:
        return current.replace(old, new) if replace_all else current.replace(old, new, 1)
    return current + new


def _content_after(tool_name: str, tool_input: Dict[str, Any], path: Path) -> Optional[str]:
    if tool_name == "Write":
        content = tool_input.get("content")
        return content if isinstance(content, str) else None
    if tool_name == "Edit":
        old, new = tool_input.get("old_string"), tool_input.get("new_string")
        if not isinstance(old, str) or not isinstance(new, str):
            return None
        return content_after_edit(path, old, new, bool(tool_input.get("replace_all")))
    source = tool_input.get("new_source")
    return source if isinstance(source, str) else None


def _body_file_names(command: str) -> List[str]:
    """The names given to --body-file or -F, without their quotes, as the shell passes them; standard input too."""
    return [filters.remove_quotes(match["name"]) for match in _BODY_FILE.finditer(command)]


def _body_files(cwd: Path, names: List[str]) -> List[Tuple[str, str]]:
    """(source, text) of the files named by --body-file or -F; a missing file raises and blocks.

    Standard input is refused before this runs, so every name is a file.
    """
    return [("body file %s" % name, (cwd / name).read_text(encoding="utf-8")) for name in names]


def _under_special_folder(path: str) -> bool:
    return any(path == folder or path.startswith(folder + "/") for folder in _SPECIAL_FOLDERS)


def _is_special_file(cwd: Path, name: str) -> bool:
    """Whether a body file is a device, a pipe, a folder or a file of another process.

    That is a name under /dev or /proc as written or as resolved (``../``, ``//``, a symbolic link), or one that exists
    as anything but a regular file. Reading it, the hook would get its own standard input, wait for a writer that never
    comes, or fail, instead of reading the text the command sends. A name that is not there is not resolved: reading
    it raises, which blocks.
    """
    joined = os.path.join(str(cwd), name)  # an absolute name replaces the folder
    if _under_special_folder(os.path.normpath(joined)):
        return True
    if not os.path.lexists(joined):
        return False
    return _under_special_folder(os.path.realpath(joined)) or not os.path.isfile(joined)


def _names_body_file_elsewhere(command: str, names: List[str]) -> bool:
    """Whether the command writes or names a body file anywhere but as the value of --body-file or -F.

    A name counts when it, or its last component, is found in the rest of the text however it is spelt around it
    (``>/tmp/b.md``, ``cd /tmp && cp x b.md``). A short name is found in many words: an accepted over-block.
    """
    elsewhere = _BODY_FILE.sub(r"\g<option>", command)
    return any((os.path.basename(name) or name) in elsewhere for name in names)


def _check_pr_text(cwd: Path, sources: List[Tuple[str, str]]) -> Optional[str]:
    repo = privacy_check.repository_root(cwd, timeout=GIT_TIMEOUT)
    terms = privacy_check.load_terms(privacy_check.terms_file_from_git(repo, timeout=GIT_TIMEOUT))
    found: List[str] = []
    for source, text in sources:
        for finding in privacy_check.scan_text(text, terms, source):
            what = 'term "%s"' % finding.label if finding.kind == "term" else "pattern %s" % finding.label
            item = "%s in %s" % (what, source)
            if item not in found:
                found.append(item)
    if not found:
        return None
    return (
        "private or personal data in the pull request (%s): the whole command is checked, not only the "
        "title and the body, so a path under a home folder counts too; remove it or use a relative path"
        % "; ".join(found)
    )


def _unreadable_text(cwd: Path, command: str, names: List[str]) -> Optional[str]:
    """Why the text of a pull request command cannot be read from the command, or None when it can.

    The hook reads what is written in the command and in the files named by --body-file or -F. Whatever the shell
    would fill in at run time, standard input, or a file the hook cannot find by its name or read as the command
    would, is text it cannot check. ``command`` has its backslash-newlines removed; ``names`` are the distinct body
    file names in it.
    """
    if "<<" in command:
        return _HERE_DOCUMENT_REASON
    if _EXPANSION.search(command):
        return _EXPANSION_REASON
    if _ATTACHED_BODY_FILE.search(command):
        return _ATTACHED_REASON
    if any(name in _STDIN_NAMES for name in names):
        return _STDIN_REASON
    if _CD.search(command) and any(not Path(name).is_absolute() for name in names):
        return _CD_REASON
    if len(names) > _MAX_BODY_FILES:
        return _MANY_FILES_REASON
    if any(_is_special_file(cwd, name) for name in names):
        return _SPECIAL_FILE_REASON
    if _names_body_file_elsewhere(command, names):
        return _STALE_FILE_REASON
    return None


def _check_shell(cwd: Path, text: str) -> Optional[str]:
    reason = filters.check_shell_command(text)
    if reason or not filters.pr_command_kind(text):
        return reason
    command = filters.without_line_continuations(text)
    names = list(dict.fromkeys(_body_file_names(command)))
    reason = _unreadable_text(cwd, command, names)
    if reason:
        return reason
    # Inside single quotes the shell keeps a backslash-newline, so what it sends may be either reading of the text.
    sources = [("the command", reading) for reading in dict.fromkeys((text, command))]
    return _check_pr_text(cwd, sources + _body_files(cwd, names))


def decide(payload: Any) -> Optional[str]:
    """Return why the tool call must be blocked, or None to let it run."""
    if not isinstance(payload, dict):
        return "unreadable hook input"
    tool_name = payload.get("tool_name")
    raw_input = payload.get("tool_input")
    tool_input = raw_input if isinstance(raw_input, dict) else {}
    cwd_value = payload.get("cwd")
    cwd = Path(cwd_value) if isinstance(cwd_value, str) and cwd_value else Path.cwd()
    if not isinstance(tool_name, str) or tool_name in filters.SHELL_TOOLS:
        # Without a tool name the input has a shape this hook does not know: check its text as a command.
        return _check_shell(cwd, shell_text(payload))
    if tool_name in filters.FILE_TOOLS:
        path_value = tool_input.get("file_path") or tool_input.get("notebook_path")
        if not isinstance(path_value, str) or not path_value:
            return filters.check_shell_command("\n".join(_strings(payload)))
        return filters.check_file_write(path_value, _content_after(tool_name, tool_input, Path(path_value)))
    if filters.is_remote_write_mcp_tool(tool_name):
        return "MCP tools that write to a remote skip the privacy pre-push; commit locally and push with git"
    if filters.mr_action_kind(tool_name):
        if not isinstance(raw_input, dict):
            # The rest of the payload (cwd, transcript path) says nothing about the pull request, so it is not scanned.
            return (
                "the tool input of a pull or merge request tool is missing or has an unknown input shape, "
                "so its text cannot be checked"
            )
        return _check_pr_text(cwd, [("the tool input", text) for text in _strings(tool_input)])
    return None


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except (OSError, ValueError, RecursionError):  # not JSON, not readable as text, or nested too deeply to parse
        print("dev_guard: unreadable hook input; blocking to stay safe", file=sys.stderr)
        return 2
    try:
        reason = decide(payload)
    except Exception as exc:  # fail closed: a crashed hook would let the tool run
        print("dev_guard: check failed (%s: %s); blocking to stay safe" % (exc.__class__.__name__, exc), file=sys.stderr)
        return 2
    if reason:
        print("dev_guard: " + reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
