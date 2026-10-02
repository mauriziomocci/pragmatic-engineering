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
a hook that errors in any other way or times out.
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
BODY_HINT = "write the body to a file and pass --body-file <path>"
_STDIN_NAMES = ("-", "/dev/stdin", "/dev/fd/0")  # body file names that mean standard input
_BODY_FILE = re.compile(r"(?:--body-file|(?<!\S)-F)(?:\s+|=)(\"[^\"]*\"|'[^']*'|\S+)")
_STDIN_BODY = re.compile(
    r"(?:--body-file|(?<!\S)-F)(?:\s+|=)[\"']?(?:%s)[\"']?(?!\S)" % "|".join(re.escape(n) for n in _STDIN_NAMES)
)
_HERE_DOC = re.compile(r"<<-?\s*[\"']?\w+")
# Group 1 is the operator line: it is command text and stays checked; only the body below it is literal.
_QUOTED_HERE_DOC = re.compile(r"(<<-?\s*([\"'])(\w+)\2[^\n]*)\n.*?^\t*\3[ \t]*$", re.DOTALL | re.MULTILINE)
# A command substitution (except the $(cat <<'EOF' form, whose body is literal) or a parameter expansion.
_EXPANSION = re.compile(r"\$\((?!\s*cat\s+<<)|`|\$[{A-Za-z_0-9@*#?$!-]")


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


def _body_files(cwd: Path, command: str) -> List[Tuple[str, str]]:
    """(source, text) of the files named by --body-file or -F; a missing file raises and blocks."""
    texts = []
    for raw in _BODY_FILE.findall(command):
        name = raw.strip("\"'")
        if name in _STDIN_NAMES:
            continue  # standard input fed by a here-document inside the command, checked with the command itself
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


def _check_shell(cwd: Path, text: str) -> Optional[str]:
    reason = filters.check_shell_command(text)
    if reason or not filters.pr_command_kind(text):
        return reason
    # The body of a quoted here-document is literal and already in the command; anything else the shell
    # would produce at run time (a substitution, a variable, standard input) is text this hook cannot read.
    if _EXPANSION.search(_QUOTED_HERE_DOC.sub(r"\1", text)):
        return (
            "the pull request command holds a command substitution or a shell variable, whose value this hook "
            "cannot check; " + BODY_HINT + ", and spell out the title, branch and other values"
        )
    if _STDIN_BODY.search(text) and not _HERE_DOC.search(text):
        return "the pull request body comes from standard input, which this hook cannot read; " + BODY_HINT
    return _check_pr_text(cwd, [("the command", text)] + _body_files(cwd, text))


def decide(payload: Any) -> Optional[str]:
    """Return why the tool call must be blocked, or None to let it run."""
    if not isinstance(payload, dict):
        return "unreadable hook input"
    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
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
