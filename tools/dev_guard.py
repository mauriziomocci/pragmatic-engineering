#!/usr/bin/env python3
"""Project PreToolUse hook of the plugin repository (step zero).

Registered in the maintainer's .claude/settings.local.json, outside git, with
the command ``python3 "<copy>/tools/dev_guard.py" || exit 2`` and
``"onFailure": "block"``, and run from the copy that
tools/install_dev_hooks.py keeps under the git directory. It keeps the agent
from skipping or switching off the privacy pre-push (shared filters in
lib/pe_guard/filters.py), blocks MCP tools that write to a remote (they bypass
the pre-push), and runs the privacy check on the text of pull and merge
requests when they are opened, edited or merged and, for gh and glab commands,
when they are reverted, reopened, commented, reviewed or closed.

Exit 2 blocks the tool, with the reason on stderr; exit 0 lets it run. A tool
this hook does not know passes. An input without a tool name, or a known tool
without its usual fields, is checked as text. A failure while importing the
shared checks or while checking a known tool exits 2 from inside the hook. A
failure before the hook runs, such as no python3 (exit 127) or a syntax error
in this file (exit 1), exits with another status, which Claude Code does not
treat as a block; the ``|| exit 2`` of the registration turns it into one on
any Claude Code version. ``"onFailure": "block"`` makes Claude Code count every
other failure of the hook as exit 2 too: a timeout, a hook that cannot start
and output that fails validation block the tool. Claude Code reads the field
from 2.1.295; on an earlier version a timed-out hook does not block and the
call goes on through the normal permission flow.

The text of a pull request is read only where it is written: in the command,
or in a regular file named by --body-file or -F (by a relative name only when
the command changes no folder). The hook models no shell grammar, so what the
shell would fill in at run time blocks, with the hint to write the body to a
file and pass its absolute path: a here-document or a here-string (any <<),
standard input as the body file (-, /dev/stdin, /dev/fd/0), any dollar sign
followed by a character (a substitution, a variable, arithmetic, $'...',
$"...", zsh's $=name), a backtick, a process substitution, a tilde or zsh's
=command, also after empty quotes. So does the word xargs when a gh or glab
word follows it, in any command and with or without a pull request verb in the
text: xargs builds the command line of the gh it starts at run time (that
reason carries no advice about a body file, since the gh may be a read). A body
file blocks too when it is attached to its option (-Fbody.md); when it is named
by a relative path after a cd, pushd or chdir; when it is missing, a device, a
pipe, a folder or a file under /dev or /proc; and when its name, or just its
last component, is a word of the rest of the command (read both with a quoted
part kept in its word and split at blanks, quotes taken off, in any letter case;
the pieces of a word split at = and : count too), because the hook reads the
file before the command runs and a cp or a redirect in the same command would
leave it with a text the command no longer sends. A backslash-newline is
removed before the command is checked, as the shell removes it. The privacy
scan reads the command three ways, and every term found in any of them blocks:
as written (inside single quotes the shell keeps the backslash-newline), with
the backslash-newlines removed, and with the quoting removed as the shell
removes it, so that Zorb""lax, 'Zorb''lax', Zorb\\lax and 'Dell'\\''Acqua' read
as the words gh gets.

Open limits, declared and pinned in OPEN_FORMS of tests/test_dev_guard.py:

- a folder change made by a program other than cd, pushd or chdir (``env -C sub
  gh pr create --body-file body.md``) leaves a relative body file read from the
  folder the hook starts in;
- an option name that is quoted or escaped (``'-F' -``, ``"--body-file" -``,
  ``--body\\-file -``) is not read as the option, so the standard input given
  to it is not seen;
- another program that runs the gh command and supplies its text, other than
  xargs (``find -exec``, ``parallel``), and a gh call written in a script file
  (``bash make-pr.sh``), which is unseen like a call held in a variable, an
  alias or a function (see lib/pe_guard/filters.py);
- a step of the same command that writes the body file without spelling its
  name as the option does (``sh gen.sh && gh pr create --body-file body.md``),
  or a value glued to a short option (``curl -sob.md``);
- brace expansion (``Zorbl{b,a}x``) and globs that build a term from literal
  parts or from a file name and reach gh as the term;
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

# Seconds for each git call: the hook has 15, and a timeout blocks the tool only through "onFailure": "block"
# (Claude Code 2.1.295 or later); before that a timed-out hook lets the tool run.
GIT_TIMEOUT = 5.0
BODY_HINT = (
    "write the body to a file in a separate step (with the Write tool), then pass --body-file <path> with an absolute "
    "path outside your home folder, such as /tmp/pr-body.md (a home path in the command is blocked too)"
)
# Why the text of a pull request command cannot be read; _check_shell closes each one with BODY_HINT.
_HERE_DOCUMENT_REASON = (
    "the pull request command holds a here-document or a here-string (<<): this hook reads only text written in the "
    "command or in a body file, and the shell fills the input in at run time"
)
_EXPANSION_REASON = (
    "the pull request command holds a substitution, a shell variable or another expansion (a tilde, =command, "
    "<(...), $'...'), whose value this hook cannot check; spell out the title, branch and other values in the command"
)
_ATTACHED_REASON = (
    "the pull request command passes a body file attached to a short option (-Fbody.md, -dF body.md), which this "
    "hook cannot locate"
)
_STDIN_REASON = (
    "the pull request body comes from standard input (-, /dev/stdin, /dev/fd/0), which this hook cannot read"
)
_CD_REASON = (
    "the command changes folder and names a body file with a relative path, which this hook would read from "
    "another folder"
)
_STALE_FILE_REASON = (
    "the command writes or names the body file elsewhere, and this hook reads the file before the command runs"
)
_SPECIAL_FILE_REASON = (
    "the pull request body file is missing, a device, a pipe, a folder or a file under /dev or /proc, which this hook "
    "cannot read as the command would"
)
# Why a gh or glab command that xargs starts is blocked. It is no pull request reason: xargs may start a read, and
# there is no body to move into a file, so this one has no BODY_HINT.
_XARGS_REASON = (
    "xargs builds the gh or glab command line when it runs, so this hook cannot read it; run gh without xargs, "
    "with the values written in the command"
)
_STDIN_NAMES = ("-", "/dev/stdin", "/dev/fd/0")  # body file names that mean standard input
# A word of the command as the shell reads it: quoted parts kept whole, whatever they hold, up to a blank or an
# operator character (-; is standard input, then a separator), so that "-"x is the file -x and ""- is standard input.
# filters.remove_quotes then takes the quotes off.
_SHELL_WORD = r"(?:\"[^\"]*\"|'[^']*'|[^\s\"';&|<>()])+"
_WORDS = re.compile(_SHELL_WORD)
# The option and the name given to --body-file or -F, the name being one such word.
_BODY_FILE = re.compile(r"(?P<option>--body-file|(?<!\S)-F)(?:\s+|=)(?P<name>%s)" % _SHELL_WORD)
# Folders of devices and of process data: a body file there is a stream (the hook would read its own input, or wait)
# or a file of another process, never the text the command sends.
_SPECIAL_FOLDERS = ("/dev", "/proc")
# A body file the pattern above does not read: -F attached to its value (-Fbody.md) or bundled with other short
# options (-dF body.md). A short option word with an F in it also catches a value that happens to hold one (-tFix),
# an accepted over-block.
_ATTACHED_BODY_FILE = re.compile(r"(?<!\S)-(?!-)(?!F(?:\s|=|$))\S*?F")
_CD = re.compile(r"\b(?:cd|pushd|chdir)\b")  # chdir is zsh's
_XARGS = re.compile(r"\bg?xargs\b")  # gxargs is GNU xargs from Homebrew
# A gh or glab word wherever it stands, also in the quoted command line of a shell (sh -c 'gh pr create ...') and
# behind a path (/usr/bin/gh), but not inside ghost, gh-x, gh.exe or my-gh.
_CLIENT_WORD = re.compile(r"(?<![\w.-])(?:gh|glab)(?![\w.-])", re.IGNORECASE)
# Text the shell produces at run time or reads otherwise than as written: a dollar sign followed by anything but a
# blank (a substitution, a parameter, arithmetic, an ANSI-C or locale string, zsh's $=name and its other flags), a
# backtick, a process substitution (zsh also writes =(...)), zsh's =command (the path of the command), a tilde at the
# start of a word or after = or : (the home folder), and an = or a tilde after empty quotes at a word start.
_EXPANSION = re.compile(
    r"\$\S|`|[<>]\(|(?<!\S)=\S|(?<![^\s=:])~|" + filters.EMPTY_QUOTES_BEFORE_EXPANSION
)
# The words of a text split without reading its quotes: at a blank, a separator, a redirection, a parenthesis, =, :.
_BLANK_SPLIT = re.compile(r"[\s;&|<>()=:]+")
# Where the pieces of a word start: after the = of an assignment or an option value, or the : of a path list.
_VALUE_BREAK = re.compile(r"[=:]+")


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
    """(source, text) of the files named by --body-file or -F; one that cannot be decoded or opened raises and blocks.

    Standard input and a name with no file behind it are refused before this runs.
    """
    return [("body file %s" % name, (cwd / name).read_text(encoding="utf-8")) for name in names]


def _under_special_folder(path: str) -> bool:
    return any(path == folder or path.startswith(folder + "/") for folder in _SPECIAL_FOLDERS)


def _is_special_file(cwd: Path, name: str) -> bool:
    """Whether a body file is missing, a device, a pipe, a folder or a file of another process.

    That is a name under /dev or /proc as written or as resolved (``../``, ``//``, a symbolic link), a name with no file
    behind it (a typo, or a name the shell rewrites: ``\\-``, ``pr.m?``, ``p{x,r}.md``), or one that exists as anything
    but a regular file. Reading it, the hook would get its own standard input, wait for a writer that never comes, or
    fail, instead of reading the text the command sends. A name that is not there is not resolved, which keeps a very
    long one cheap.
    """
    joined = os.path.join(str(cwd), name)  # an absolute name replaces the folder
    if _under_special_folder(os.path.normpath(joined)) or not os.path.lexists(joined):
        return True
    return _under_special_folder(os.path.realpath(joined)) or not os.path.isfile(joined)


def _names_body_file_elsewhere(command: str, names: List[str]) -> bool:
    """Whether the command writes or names a body file anywhere but as the value of --body-file or -F.

    The words of the rest of the command go into one set, built once, each with its quotes taken off and in lower
    case (the disk of a Mac ignores the case). They are read two ways and the set holds both: with the grammar of the
    option's value (a quoted part stays in its word, whatever it holds: ``"pr body.md"``), and split at blanks and
    operator characters (an escaped quote, which the first reading does not see, shifts its pairing and can fold a
    write of the file into one long word). Pieces of each word split at = and :, and the last component of each
    piece, join them. A name is found when it, or its last component, is in the set: ``cp x /tmp/b.md``, ``>b.md``,
    ``tee "B".md`` and ``cp x "pr body.md"`` name the files b.md and pr body.md. ``--body-file`` does not name
    ``body``; ``gh pr`` names ``pr``, an accepted over-block. A union can only find more.
    """
    elsewhere = _BODY_FILE.sub(r"\g<option>", command)
    read = set(_WORDS.findall(elsewhere)) | set(_BLANK_SPLIT.split(elsewhere))
    words = {filters.remove_quotes(word).lower() for word in read}
    pieces = words | {piece for word in words for piece in _VALUE_BREAK.split(word) if piece}
    spelt = pieces | {os.path.basename(piece) for piece in pieces}
    return any((os.path.basename(name) or name).lower() in spelt for name in names)


def _xargs_starts_client(command: str) -> bool:
    """Whether a gh or glab word follows the word xargs: xargs builds the command line of that gh at run time.

    Only the first xargs is searched from: a gh after a later one is after this one too, so the time stays linear.
    """
    xargs = _XARGS.search(command)
    return xargs is not None and _CLIENT_WORD.search(command, xargs.end()) is not None


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
    or another program would fill in at run time, standard input, or a file the hook cannot find by its name or read
    as the command would, is text it cannot check. ``command`` has its backslash-newlines removed; ``names`` are the
    distinct body file names in it. The reason has no hint: the caller adds it.
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
    if _names_body_file_elsewhere(command, names):
        return _STALE_FILE_REASON
    if any(_is_special_file(cwd, name) for name in names):
        return _SPECIAL_FILE_REASON
    return None


def _check_shell(cwd: Path, text: str) -> Optional[str]:
    reason = filters.check_shell_command(text)
    if reason:
        return reason
    command = filters.without_line_continuations(text)
    if _xargs_starts_client(command):
        return _XARGS_REASON
    if not filters.pr_command_kind(command):
        return None
    names = list(dict.fromkeys(_body_file_names(command)))
    reason = _unreadable_text(cwd, command, names)
    if reason:
        return "%s; %s" % (reason, BODY_HINT)
    # What gh receives is one of three readings of the text: inside single quotes the shell keeps a backslash-newline,
    # elsewhere it removes it, and it removes the quoting too (Zorb""lax and 'Dell'\''Acqua' become words). A term
    # in any of them is a finding; none of them decides that the command is clean.
    readings = dict.fromkeys((text, command, filters.remove_shell_quoting(text)))
    return _check_pr_text(cwd, [("the command", reading) for reading in readings] + _body_files(cwd, names))


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
