"""Text filters shared by the project hook of step zero and the PreToolUse guard of A2.

Both checks are deliberately textual and apply to the whole command, with no
prefix exemption: ``echo ok && git push --no-verify`` is caught like
``git push --no-verify``. They defend against the model's haste (retrying a
blocked push with --no-verify, turning hooks off), not against a user who is
determined to bypass them.
"""
import re
from pathlib import PurePath
from typing import Dict, List, Optional, Tuple

SHELL_TOOLS: Tuple[str, ...] = ("Bash", "PowerShell", "Monitor", "mcp__terminal__run_in_terminal")
FILE_TOOLS: Tuple[str, ...] = ("Write", "Edit", "NotebookEdit")
REMOTE_WRITE_MCP_SUFFIXES: Tuple[str, ...] = ("push_files", "create_or_update_file", "delete_file")
MR_ACTION_MCP_SUFFIXES: Dict[str, str] = {
    "create_merge_request": "create",
    "create_pull_request": "create",
    "update_merge_request": "update",
    "update_pull_request": "update",
    "merge_merge_request": "merge",
    "merge_pull_request": "merge",
}
GUARD_DATA_DIR = "pragmatic-engineering"  # also holds the step zero copy, see tools/install_dev_hooks.py
_DATA_DIR_REASON = (
    "the guard's data folder under the git directory, step zero copy included, "
    "is written only by the guard and by tools/install_dev_hooks.py"
)

_I = re.IGNORECASE
_NO_VERIFY = re.compile(r"--no-ve", _I)
_PUSH = re.compile(r"\bpush\b", _I)
_HOOKS_PATH = re.compile(r"hookspath", _I)
_DISABLE_ALL_HOOKS = re.compile(r"disableallhooks", _I)
_GIT_CONFIG_ENV = re.compile(r"git_config_", _I)
_HOOKS_DIR = re.compile(
    r"\.git[/\\]+hooks|--git-path\s+hooks|--git-(?:common-)?dir\)[\"']?[/\\]+hooks|\bhooks[/\\]+pre-push", _I
)
_PRE_PUSH = re.compile(r"pre-push", _I)
_DATA_DIR = re.compile(r"(?:\.git|--git-(?:common-)?dir\)[\"']?)[/\\]+pragmatic-engineering", _I)
_GUARD_CLI = re.compile(r"\bpe[-_]guard\b", _I)
_GUARD_REMOVAL = re.compile(r"\b(?:uninstall|repair)\b", _I)
_GIT = re.compile(r"\bgit\b", _I)
# Any merge_request.* push option (create, merge_when_pipeline_succeeds, auto_merge, description, ...) opens,
# updates or auto-merges a merge request from a plain push. The prefix is anchored to the option syntax, not to
# the word push: -o alone or bundled (-uo), a long option or an abbreviation of it git accepts (--pu...), or the
# push.pushOption config key. A short option must start a word, so --typo or release-o are not -o. A file named
# tests/test_merge_request.py is not caught; the word git (not push, so an alias like "git p" is caught) keeps
# "curl -o merge_request.json" and "sort -o merge_request.txt" out.
_MR_PUSH_OPTION = re.compile(
    r"(?:(?<![\w-])-[a-z]*o\s*|--pu[a-z-]*[\s=]+|pushoption[\s=]+)[\"']?merge_request\.", _I
)
# A command is cut into statements at the shell separators (&& || ; | & and newline), reading from its start so
# that quotes pair up: a separator inside quotes, or after a backslash-newline continuation, does not end a
# statement. Each gh/glab api call is judged on its own text (up to the end of its statement or the next api
# call), so a read in one call never excuses a write in the next.
_STATEMENT = re.compile(r"(?:\\\r?\n|\"[^\"]*\"|'[^']*'|[^|;&\n])+")
_API_CALL = re.compile(r"\b(?:gh|glab)\s+api\b", _I)
_CONTINUATION = re.compile(r"\\\r?\n")
_ARGUMENT = re.compile(r"(?:[^\s\"']|\"[^\"]*\"|'[^']*')+")
# gh api flags that take the next argument as their value (gh 2.100.0, gh api --help); a value is never the
# endpoint. glab api could not be checked here, so a glab-only value flag counts as the endpoint: that fails
# closed, it can only block a read.
_VALUE_FLAGS = frozenset({
    "-f", "-F", "-X", "-H", "-p", "-q", "-t",
    "--cache", "--field", "--header", "--hostname", "--input", "--jq", "--method", "--preview",
    "--raw-field", "--template",
})
_MUTATION = re.compile(r"\bmutation\b", _I)
_QUERY_FROM_FILE = re.compile(r"(?:-f|--field|--raw-field)[\s=]+[\"']?query=@|--input\b", _I)
_MR_ENDPOINT = re.compile(r"pulls|merge_requests|pullrequest|mergerequest", _I)
_WRITE_METHOD = re.compile(r"(?:-X\s*|--method[\s=]+)[\"']?(?:post|put|patch|delete)\b", _I)
_READ_METHOD = re.compile(r"(?:-X\s*|--method[\s=]+)[\"']?get\b", _I)
_WRITE_FIELD = re.compile(r"(?:^|\s)(?:-f|--field|--raw-field|--input)(?=[\s=]|$)", _I)
_PR_COMMAND = re.compile(
    r"\bgh\s+pr\s+(create|new|edit|merge)\b|\bglab\s+mr\s+(create|new|update|merge)\b", _I
)
_MCP_TOOL = re.compile(r"mcp__.+__([A-Za-z0-9_-]+)")
_SETTINGS_NAME = re.compile(r"settings.*\.json", _I)
_PR_KIND = {"create": "create", "new": "create", "edit": "update", "update": "update", "merge": "merge"}


def check_shell_command(command: str) -> Optional[str]:
    """Return why a shell command must be blocked, or None when it may run."""
    text = command or ""
    if _NO_VERIFY.search(text) and _PUSH.search(text):
        return "a push that skips git hooks (--no-verify or a prefix of it) is not allowed"
    if _HOOKS_PATH.search(text):
        return "changing core.hooksPath switches git hooks off; only the user may do it, from their own terminal"
    if _DISABLE_ALL_HOOKS.search(text):
        return "disableAllHooks switches every Claude Code hook off; only the user may set it"
    if _GIT_CONFIG_ENV.search(text):
        return "GIT_CONFIG_* variables rewrite git configuration for one command, hooks path included"
    if _HOOKS_DIR.search(text) and _PRE_PUSH.search(text):
        return "the pre-push hook is not read, changed, moved or removed by the agent"
    if _DATA_DIR.search(text):
        return _DATA_DIR_REASON
    if _GUARD_CLI.search(text) and _GUARD_REMOVAL.search(text):
        return "pe-guard uninstall and repair are the user's commands, from their own terminal"
    if _GIT.search(text) and _MR_PUSH_OPTION.search(text):
        return (
            "merge_request.* push options open, update or auto-merge a merge request "
            "without going through the checked merge request tools"
        )
    if _api_writes_requests(text):
        return (
            "writing to pull or merge requests through the raw API, or sending a GraphQL query read from a file, "
            "bypasses the checked tools"
        )
    return None


def _api_writes_requests(text: str) -> bool:
    """True when any gh/glab api call in a command writes to pull or merge requests, or may."""
    # split() cuts a statement at each api call, so every call is analysed once, on its own text
    return any(
        _api_call_writes_requests(call)
        for statement in _STATEMENT.findall(text)
        for call in _API_CALL.split(statement)[1:]
    )


def _api_endpoint(call: str) -> Optional[str]:
    """First argument of a gh/glab api call that is neither a flag nor a flag's value, quotes removed."""
    arguments = iter(_ARGUMENT.findall(call))
    for argument in arguments:
        if not argument.startswith("-"):
            return argument.strip("\"'")
        if argument in _VALUE_FLAGS:
            next(arguments, None)
    return None


def _api_call_writes_requests(call: str) -> bool:
    """True when one gh/glab api call (the text after ``api``) writes to pull or merge requests, or may.

    ``may`` is a GraphQL query read from a file: it cannot be inspected, so it counts as a write.
    """
    call = _CONTINUATION.sub(" ", call)
    if (_api_endpoint(call) or "").lower() == "graphql":
        # GraphQL always travels as a POST, so only the query tells a read from a write.
        return bool(_QUERY_FROM_FILE.search(call) or (_MUTATION.search(call) and _MR_ENDPOINT.search(call)))
    # With an explicit GET, -f and -F fields are query parameters, not a request body.
    writes = _WRITE_METHOD.search(call) or (_WRITE_FIELD.search(call) and not _READ_METHOD.search(call))
    return bool(writes and _MR_ENDPOINT.search(call))


def _is_git_dir(part: str) -> bool:
    return part == ".git" or part.endswith(".git")


def check_file_write(path: str, content_after: Optional[str]) -> Optional[str]:
    """Return why a file write must be blocked, or None when it may happen.

    ``content_after`` is the whole file as it would be after the write; the
    caller computes it (for Edit, by applying the replacement to the current
    file). It matters only for Claude Code settings files.
    """
    parts: List[str] = [p.lower() for p in PurePath(path).parts]
    if not parts:
        return None
    name = parts[-1]
    # Indices before the file name only: parts[i + 1] always exists, and a git directory is never the
    # "hooks" folder itself, so a non-empty list already means "somewhere under a git directory".
    git_dirs = [i for i, part in enumerate(parts[:-1]) if _is_git_dir(part)]
    if git_dirs and name == "pre-push" and parts[-2] == "hooks":
        return "the pre-push hook is not written by the agent"
    if any(parts[i + 1] == GUARD_DATA_DIR for i in git_dirs):
        return _DATA_DIR_REASON
    after = None if content_after is None else content_after.lower()
    is_settings = name == "managed-settings.json" or (
        len(parts) >= 2 and parts[-2] == ".claude" and _SETTINGS_NAME.fullmatch(name) is not None
    )
    if is_settings and (after is None or "disableallhooks" in after):
        return "a Claude Code settings file with disableAllHooks switches every hook off; only the user may write it"
    return None


def _mcp_suffix(tool_name: str) -> Optional[str]:
    """Tool name after the server part, with hyphens read as underscores (some servers spell them so)."""
    match = _MCP_TOOL.fullmatch(tool_name or "")
    return match.group(1).replace("-", "_") if match else None


def is_remote_write_mcp_tool(tool_name: str) -> bool:
    """MCP tools that write commits straight to a remote, bypassing the pre-push hook."""
    return _mcp_suffix(tool_name) in REMOTE_WRITE_MCP_SUFFIXES


def mr_action_kind(tool_name: str) -> Optional[str]:
    """'create', 'update' or 'merge' for MCP merge request tools, else None."""
    suffix = _mcp_suffix(tool_name)
    return MR_ACTION_MCP_SUFFIXES.get(suffix) if suffix else None


def pr_command_kind(command: str) -> Optional[str]:
    """'create', 'update' or 'merge' for gh pr / glab mr commands in a shell text."""
    match = _PR_COMMAND.search(command or "")
    if not match:
        return None
    verb = (match.group(1) or match.group(2)).lower()
    return _PR_KIND[verb]
