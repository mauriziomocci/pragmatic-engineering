#!/usr/bin/env python3
"""Project PreToolUse hook of the plugin repository (step zero).

Registered in the maintainer's .claude/settings.local.json, outside git, and
run from the copy that tools/install_dev_hooks.py keeps under the git
directory. It keeps the agent from skipping or switching off the privacy
pre-push (shared filters in lib/pe_guard/filters.py), blocks MCP tools that
write to a remote (they bypass the pre-push), and runs the privacy check on
the text of pull and merge requests when they are opened, edited or merged.

Exit 2 blocks the tool, with the reason on stderr; exit 0 lets it run. A tool
this hook does not know passes. An input without a tool name, or a known tool
without its usual fields, is checked as text. Any failure while loading the
checks or checking a known tool blocks, because Claude Code does not block on
a hook that errors in any other way or times out. The text of a pull request
that the hook cannot read from the command blocks too, with the hint to pass
an absolute --body-file path, because a miss on the pull request path would
let the text through unchecked: a command or process substitution, a
variable, a tilde or zsh's =command; a body file attached to its option, named
by a relative path after a cd, or that is a device, a pipe, a folder or a
file under /dev or /proc.

A body read from standard input (--body-file or -F with -, /dev/stdin or
/dev/fd/0) passes only when the whole command is one of two shapes, an
allowlist and not a parser: gh or glab and its words, ending in one quoted
here-document operator (``gh pr create --title x --body-file - <<'EOF'``), or
``cat <<'EOF' |`` and then gh or glab and its words; after that line, the
body, its terminator line and nothing but blanks and newlines. The words hold
only ASCII letters, digits and - _ . / = : @ , + %, single-quoted text, and
double-quoted text without $, backtick or backslash, none of them across a
newline. Anything else with standard input blocks: a pipe from another
command, a < or a second operator, a separator, a continuation, a second
command.

The body of a quoted here-document is literal text, and it is cut out before
the command is searched for substitutions and variables; so a body may hold
$HOME or backticks, and ``$(cat <<'EOF'`` is readable when nothing follows
the operator on its line and the closing parenthesis comes right after the
terminator. The terminator is the tag alone on its line (after tabs only for
<<-), as bash and zsh end the body. An operator that a backslash escapes is no
operator, and one whose line goes on past the newline (a quoted string left
open, a backslash at the end) stops the cutting, so the lines after it stay in
the text the checks read.

Open limits, declared and pinned in OPEN_FORMS of tests/test_dev_guard.py: an
operator the shell does not read as one (inside a quoted string, after a
comment sign, in the body of an unquoted here-document) followed by a bare
terminator line is taken for a quoted here-document, so a substitution
between them is not seen (``--body "Use <<'EOF' in scripts``, then
``$(cat body.md)``, then ``EOF``, then ``"``); and a folder change made by a
program other than cd or pushd (``env -C sub gh pr create --body-file
body.md``) leaves a relative body file read from the folder the hook starts
in.
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
_STDIN_NAMES = ("-", "/dev/stdin", "/dev/fd/0")  # body file names that mean standard input
# The name given to --body-file or -F as the shell passes it: the whole word, quoted parts and all, up to a blank or an
# operator character (-; is standard input, then a separator), so that "-"x is the file -x and ""- is standard input;
# _QUOTES then takes the quotes off.
_BODY_FILE = re.compile(r"(?:--body-file|(?<!\S)-F)(?:\s+|=)((?:\"[^\"]*\"|'[^']*'|[^\s\"';&|<>()])+)")
_QUOTES = re.compile(r"\"([^\"]*)\"|'([^']*)'")
# Folders of devices and of process data: a body file there is a stream (the hook would read its own input, or wait)
# or a file of another process, never the text the command sends.
_SPECIAL_FOLDERS = ("/dev", "/proc")
# A body file the pattern above does not read: -F attached to its value (-Fbody.md) or bundled with other short
# options (-dF body.md). A short option word with an F in it also catches a value that happens to hold one (-tFix),
# an accepted over-block.
_ATTACHED_BODY_FILE = re.compile(r"(?<!\S)-(?!-)(?!F(?:\s|=|$))\S*?F")
# The only commands in which a body read from standard input is a here-document written in the command and nothing
# else, as one grammar of the whole text: (A) gh or glab (a path in front allowed) and its words, ending in one quoted
# here-document operator; (B) cat with that operator, a pipe, then gh or glab and its words. Then the body, the
# terminator line exactly as bash and zsh end the body (the tag alone, after tabs only for <<-), and nothing but
# blanks and newlines. A word holds, outside quotes, only ASCII letters, digits and _ - . / = : @ , + %; a
# double-quoted string no $, backtick or backslash; a single-quoted one anything but '; neither a newline. So nothing
# on the line expands, redirects or starts another command (what does expand there, zsh's =command, is blocked by
# _EXPANSION first). Every character has one reading, so a failing match costs time linear in the text.
_SHELL_WORD = r"(?:[\w\-.,/=:@+%]|'[^'\n]*'|\"[^\"$`\\\n]*\")+"
_PR_CLIENT_COMMAND = r"(?:[\w.\-/]*/)?(?:gh|glab)(?:[ \t]+%s)*" % _SHELL_WORD
_TERMINATOR = r"(?(dash)\t*)(?P=tag)(?=\n|\Z)"
_STDIN_HERE_DOC_COMMAND = re.compile(
    r"[ \t]*(?:(?P<pipe>cat[ \t]+)|{command}[ \t]*)<<(?P<dash>-)?(?P<quote>['\"])(?P<tag>\w+)(?P=quote)"
    r"(?(pipe)[ \t]*\|[ \t]*{command})[ \t]*\n"
    r"(?:(?!{terminator})[^\n]*\n)*{terminator}(?:\n[ \t\n]*)?".format(
        command=_PR_CLIENT_COMMAND, terminator=_TERMINATOR
    ),
    re.ASCII,
)
# The operator of a quoted here-document: not of a here-string (<<<), and not one a backslash escapes (\<<'EOF' is the
# text < and an input redirection from a file). Groups: the dash of <<-, the quote, the tag.
_QUOTED_OPERATOR = re.compile(r"(?<![<\\])<<(-)?[ \t]*([\"'])(\w+)\2")
# What may follow the operator on its line for the body to start on the next one: quoted strings that close on the
# line, and no backslash left at its end (an odd run of backslashes before the newline continues the line). Every
# character has one reading, so a failing match costs time linear in the line.
_OPERATOR_LINE_END = re.compile(r"(?:[^'\"\\\n]|\\[^\n]|'[^'\n]*'|\"(?:[^\"\\\n]|\\[^\n])*\")*")
# A line that may end a body: tabs and a word, with no blank or carriage return after it.
_TERMINATOR_LINE = re.compile(r"^(\t*)(\w+)$", re.MULTILINE)
_CD = re.compile(r"\b(?:cd|pushd)\b")
# Text the shell produces at run time: a command substitution, a parameter expansion, a process substitution (zsh
# also writes =(...)), zsh's =command (the path of the command) and a tilde at the start of a word or after = or :
# (the home folder). The one substitution that is not text produced at run time is
# $(cat <<'EOF' with nothing else on its line and the closing parenthesis right after the body (the text this is
# tested on has the body of a quoted here-document cut out): its text is then the here-document, which is part of
# the command. An argument or a pipe after the operator, or a command after the terminator line, makes cat or the
# substitution print something else; an unquoted tag keeps its body in the text, where the parenthesis is not next.
_EXPANSION = re.compile(
    r"\$\((?!\s*cat\s+<<-?[ \t]*([\"'])\w+\1[ \t\r]*\n\s*\))|`|\$[{A-Za-z_0-9@*#?$!-]"
    r"|[<>]\(|(?<!\S)=\S|(?<![^\s=:])~"
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


def _without_quoted_here_document_bodies(text: str) -> str:
    """The text without the bodies of its quoted here-documents, which the shell takes literally.

    The operator line stays, and so does everything after the terminator line, which is the tag alone (after tabs
    only for <<-), as bash and zsh end the body. The text is read once: after a terminator the search goes on from
    there, so an operator inside a body is part of that body, as in the shell. An operator whose terminator is
    missing, or whose line goes on past its newline (a quoted string still open, a backslash at the end), stops the
    scan and what follows stays in the text, where the checks see it: the body does not start where the scan would
    cut, and an operator inside a quoted string is no here-document, so taking the rest of the text for a body would
    hide a substitution that really runs.
    """
    kept: List[str] = []
    position = 0
    while True:
        operator = _QUOTED_OPERATOR.search(text, position)
        if operator is None:
            break
        line_end = text.find("\n", operator.end())
        if line_end < 0 or not _OPERATOR_LINE_END.fullmatch(text, operator.end(), line_end):
            break  # no line after it, or the command line goes on: no body starts on the next line
        dash, tag = operator.group(1), operator.group(3)
        terminator = next(
            (
                line for line in _TERMINATOR_LINE.finditer(text, line_end + 1)
                if line.group(2) == tag and (dash or not line.group(1))
            ),
            None,
        )
        if terminator is None:
            break
        kept.append(text[position:line_end])
        position = terminator.end()
    kept.append(text[position:])
    return "".join(kept)


def _body_file_names(command: str) -> List[str]:
    """The names given to --body-file or -F, without their quotes, as the shell passes them; standard input too."""
    return [_QUOTES.sub(r"\1\2", word) for word in _BODY_FILE.findall(command)]


def _body_files(cwd: Path, command: str) -> List[Tuple[str, str]]:
    """(source, text) of the files named by --body-file or -F; a missing file raises and blocks.

    Standard input is skipped: _unreadable_text lets it through only when a here-document written in the command
    feeds it, and that text is checked with the command itself.
    """
    texts = []
    for name in _body_file_names(command):
        if name in _STDIN_NAMES:
            continue
        path = Path(name) if Path(name).is_absolute() else cwd / name
        texts.append(("body file %s" % name, path.read_text(encoding="utf-8")))
    return texts


def _is_special_file(cwd: Path, name: str) -> bool:
    """Whether a body file is a device, a pipe, a folder or a file of another process.

    That is a name under /dev or /proc as written or as resolved (``../``, ``//``, a symbolic link), or one that exists
    as anything but a regular file. Reading it, the hook would get its own standard input, wait for a writer that never
    comes, or fail, instead of reading the text the command sends.
    """
    joined = os.path.join(str(cwd), name)  # an absolute name replaces the folder
    for path in (os.path.normpath(joined), os.path.realpath(joined)):
        if any(path == folder or path.startswith(folder + "/") for folder in _SPECIAL_FOLDERS):
            return True
    return os.path.exists(joined) and not os.path.isfile(joined)


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


def _unreadable_text(cwd: Path, text: str) -> Optional[str]:
    """Why the text of a pull request command cannot be read from the command, or None when it can.

    The body of a quoted here-document is literal and already in the command. Anything else the shell would
    produce at run time (a substitution, a variable, standard input), or read from a file the hook cannot find by
    its name or cannot read as the command would, is text this hook cannot check.
    """
    literal = _without_quoted_here_document_bodies(text)
    if _EXPANSION.search(literal):
        return (
            "the pull request command holds a substitution, a shell variable or another expansion (a tilde, "
            "=command, <(...)), whose value this hook cannot check; " + BODY_HINT
            + "; spell out the title, branch and other values in the command"
        )
    if _ATTACHED_BODY_FILE.search(literal):
        return (
            "the pull request command passes a body file attached to a short option (-Fbody.md, -dF body.md), "
            "which this hook cannot locate; " + BODY_HINT + ", written as a separate word"
        )
    names = _body_file_names(text)
    if any(name in _STDIN_NAMES for name in names) and not _STDIN_HERE_DOC_COMMAND.fullmatch(text):
        return (
            "the pull request body comes from standard input, and the command is not one of the two forms whose "
            "input this hook can read (the pull request command ending in one quoted here-document, <<'EOF', or "
            "cat <<'EOF' piped into it, with plain words and nothing else in the command); " + BODY_HINT
        )
    files = [name for name in names if name not in _STDIN_NAMES]
    if _CD.search(literal) and any(not Path(name).is_absolute() for name in files):
        return (
            "the command changes folder and names a body file with a relative path, which this hook would read from "
            "another folder; " + BODY_HINT
        )
    if any(_is_special_file(cwd, name) for name in files):
        return (
            "the pull request body file is a device, a pipe, a folder or a file under /dev or /proc, which this hook "
            "cannot read as the command would; " + BODY_HINT
        )
    return None


def _check_shell(cwd: Path, text: str) -> Optional[str]:
    reason = filters.check_shell_command(text)
    if reason or not filters.pr_command_kind(text):
        return reason
    return _unreadable_text(cwd, text) or _check_pr_text(cwd, [("the command", text)] + _body_files(cwd, text))


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
