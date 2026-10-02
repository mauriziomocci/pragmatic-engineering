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
that the hook cannot read from the command (a substitution, a variable,
standard input without a here-document of the same command line, a body file
it cannot locate) blocks too, with the hint to pass an absolute --body-file
path: a miss on the pull request path would let the text through unchecked.
"""
import json
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
_BODY_FILE = re.compile(r"(?:--body-file|(?<!\S)-F)(?:\s+|=)(\"[^\"]*\"|'[^']*'|\S+)")
# A body file the pattern above does not read: -F attached to its value (-Fbody.md) or bundled with other short
# options (-dF body.md). A short option word with an F in it also catches a value that happens to hold one (-tFix),
# an accepted over-block.
_ATTACHED_BODY_FILE = re.compile(r"(?<!\S)-(?!-)(?!F(?:\s|=|$))\S*?F")
_STDIN_BODY = re.compile(
    r"(?:--body-file|(?<!\S)-F)(?:\s+|=)[\"']?(?:%s)[\"']?(?!\S)" % "|".join(re.escape(n) for n in _STDIN_NAMES)
)
_HERE_DOC = re.compile(r"<<-?\s*[\"']?\w+")
# The operator of a quoted here-document, not of a here-string (<<<). Group 1 is the operator line: it is command
# text and stays checked; only the body below it is literal.
_QUOTED_OPERATOR = re.compile(r"(?<!<)(<<-?[ \t]*([\"'])(\w+)\2[^\n]*)\n")
_TERMINATOR_LINE = re.compile(r"^\t*(\w+)[ \t]*$", re.MULTILINE)
# Where a command line ends: the separators of a list, and a newline unless a backslash continues the line.
_LIST_SEPARATOR = re.compile(r"&&|\|\||;|\n|(?<![<>])&(?!>)")
_CONTINUATION = re.compile(r"\\\r?\n")
_CD = re.compile(r"\b(?:cd|pushd)\b")
# A command substitution or a parameter expansion. The one substitution that is not text produced at run time is
# $(cat <<'EOF' with nothing else on its line: its text is the here-document below it, which is part of the command.
# With an argument or a pipe after the operator, cat or the pipeline reads something else.
_EXPANSION = re.compile(r"\$\((?!\s*cat\s+<<-?[ \t]*[\"']?\w+[\"']?[ \t\r]*\n)|`|\$[{A-Za-z_0-9@*#?$!-]")


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

    The operator line stays, and so does everything after the terminator line. The text is read once: after a
    terminator the search goes on from there, so an operator inside a body is part of that body, as in the shell. An
    operator whose terminator is missing stops the scan and what follows stays in the text, where the checks see it:
    the shell would read it as the body, but an operator inside a quoted string is no here-document, and taking the
    rest of the text for a body would hide a substitution that really runs.
    """
    kept: List[str] = []
    position = 0
    while True:
        operator = _QUOTED_OPERATOR.search(text, position)
        if operator is None:
            break
        terminator = next(
            (line for line in _TERMINATOR_LINE.finditer(text, operator.end()) if line.group(1) == operator.group(3)),
            None,
        )
        if terminator is None:
            break
        kept.append(text[position:operator.end(1)])
        position = terminator.end()
    kept.append(text[position:])
    return "".join(kept)


def _body_file_names(command: str) -> List[str]:
    """The names given to --body-file or -F, except standard input, which a here-document in the command feeds."""
    names = [raw.strip("\"'") for raw in _BODY_FILE.findall(command)]
    return [name for name in names if name not in _STDIN_NAMES]


def _body_files(cwd: Path, command: str) -> List[Tuple[str, str]]:
    """(source, text) of the files named by --body-file or -F; a missing file raises and blocks."""
    texts = []
    for name in _body_file_names(command):
        path = Path(name) if Path(name).is_absolute() else cwd / name
        texts.append(("body file %s" % name, path.read_text(encoding="utf-8")))
    return texts


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


def _unreadable_text(text: str) -> Optional[str]:
    """Why the text of a pull request command cannot be read from the command, or None when it can.

    The body of a quoted here-document is literal and already in the command. Anything else the shell would
    produce at run time (a substitution, a variable, standard input), or read from a file the hook cannot find by
    its name, is text this hook cannot check.
    """
    literal = _without_quoted_here_document_bodies(text)
    if _EXPANSION.search(literal):
        return (
            "the pull request command holds a command substitution or a shell variable, whose value this hook "
            "cannot check; " + BODY_HINT + "; spell out the title, branch and other values in the command"
        )
    if _ATTACHED_BODY_FILE.search(literal):
        return (
            "the pull request command passes a body file attached to a short option (-Fbody.md, -dF body.md), "
            "which this hook cannot locate; " + BODY_HINT + ", written as a separate word"
        )
    # A here-document feeds the standard input of the command line it is written on: a pipeline or a single command.
    # One written next to another command (git commit -F - <<'EOF') feeds that command, not the pull request.
    for line in _LIST_SEPARATOR.split(_CONTINUATION.sub(" ", literal)):
        if _STDIN_BODY.search(line) and not _HERE_DOC.search(line):
            return (
                "the pull request body comes from standard input and no here-document of the same command line "
                "feeds it, which this hook cannot read; " + BODY_HINT
            )
    if _CD.search(literal) and any(not Path(name).is_absolute() for name in _body_file_names(text)):
        return (
            "the command changes folder and names a body file with a relative path, which this hook would read from "
            "another folder; " + BODY_HINT
        )
    return None


def _check_shell(cwd: Path, text: str) -> Optional[str]:
    reason = filters.check_shell_command(text)
    if reason or not filters.pr_command_kind(text):
        return reason
    return _unreadable_text(text) or _check_pr_text(cwd, [("the command", text)] + _body_files(cwd, text))


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
