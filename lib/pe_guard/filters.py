"""Text filters shared by the project hook of step zero and the PreToolUse guard of A2.

Both checks are deliberately textual and apply to the whole command, with no
prefix exemption: ``echo ok && git push --no-verify`` is caught like
``git push --no-verify``. They defend against the model's haste (retrying a
blocked push with --no-verify, turning hooks off), not against a user who is
determined to bypass them.

What a textual filter cannot see stays open, by design: the endpoint of a raw
API call held in a shell variable (``gh api "$EP" -f ...``), a quoted option
flag of git (``git push "-o" ...``), an option value held in a variable
(``-o "$OPT"``), a shell, git or gh alias or function that hides the command,
``eval`` or a command held in a variable (``$cmd``), a command line that
another program builds from text (``sh -c 'g$(echo h) api ...'``,
``printf '... %s PUT' -X | sh``), bundled short options of gh api
(``-iX PUT``), and ``curl`` or any other client calling the API directly.

For raw API writes the filter never lets through what its first version
blocked, except reads it can vouch for: the whole-text verdict of that version
(an api call, a write marker and a pull or merge request word, each anywhere in
the command) stands unless the command is written only in the syntax the parser
models and every api call found in it reads, see ``_api_writes_requests``.
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
# the word push: -o alone or bundled with other short options and digits (-uo, -4o), a long option or an
# abbreviation of it git accepts (--pu...), or the push.pushOption config key. A short option must start a word,
# so --typo or release-o are not -o. A file named tests/test_merge_request.py is not caught. The guard is the
# word git anywhere in the command, not the arguments of a git command (so an alias like "git p" is caught): it
# keeps "curl -o merge_request.json" and "sort -o merge_request.txt" out, and "git status && curl -o
# merge_request.json URL" is blocked, an accepted over-block.
_MR_PUSH_OPTION = re.compile(
    r"(?:(?<![\w-])-[a-z0-9]*o\s*|--pu[a-z-]*[\s=]+|pushoption[\s=]+)[\"']?merge_request\.", _I
)
# The whole-text verdict of the first version of this filter: an api call, a write marker and a pull or merge request
# word, each anywhere in the command.
_API_CALL = re.compile(r"\b(?:gh|glab)\s+api\b", _I)
_MR_ENDPOINT = re.compile(r"pulls|merge_requests|pullrequest|mergerequest", _I)
_WRITE_METHOD = re.compile(r"(?:-X\s*|--method[\s=]+)[\"']?(?:post|put|patch|delete)\b", _I)
_WRITE_FIELD = re.compile(r"(?:^|\s)(?:-f|--field|--raw-field|--input)(?=[\s=]|$)", _I)
# The syntax the parser models, an allowlist: outside quotes only word characters, - _ . / = : @ , + %, spaces, tabs
# and the separators && || ; | and newline; single-quoted text with anything; double-quoted text without $, backtick
# or backslash. Nothing in such a command expands, so the words below are exactly the arguments the shell passes.
_MODELLED = re.compile(r"(?:[\w\-.,/=:@+% \t\n;|]|&&|'[^']*'|\"[^\"$`\\]*\")*", re.ASCII)
# Statements end at && || ; | & and newline outside quotes, but not at a backslash-newline continuation; words end at
# blanks outside quotes, and lose their quotes. A command outside the model is cut the same way, approximately: there
# its calls can only add blocks to the whole-text verdict.
_STATEMENT = re.compile(r"(?:\\\r?\n|\"[^\"]*\"|'[^']*'|[^|;&\n])+")
_WORD = re.compile(r"(?:[^\s\"'\\]|\\(?!\r?\n)|\"[^\"]*\"|'[^']*')+")
_QUOTES = re.compile(r"\"([^\"]*)\"|'([^']*)'")
_CLIENT = re.compile(r"(?:.*\W)?(?:gh|glab)", _I | re.DOTALL)  # also /usr/local/bin/gh, zsh's =gh, GH on macOS
_ASSIGNMENT = re.compile(r"[A-Za-z_]\w*=")
_BLANK = re.compile(r"\s")
# gh api options (gh 2.100.0, gh api --help): those that take a value, those whose value is a field (the request
# body unless the method is GET), and the switches. glab api could not be checked here, so a glab-only option is an
# option the parser does not know: the whole-text verdict stands for its command (a read that names a merge request
# is blocked, a false positive), and the write check takes the next argument for the endpoint (a GraphQL query read
# from a file behind a glab-only option that takes a value is not seen, open as in the first version of this filter).
_VALUE_OPTIONS = frozenset({
    "-F", "-H", "-X", "-f", "-p", "-q", "-t",
    "--cache", "--field", "--header", "--hostname", "--input", "--jq", "--method", "--preview", "--raw-field",
    "--template",
})
_FIELD_OPTIONS = frozenset({"-F", "-f", "--field", "--input", "--raw-field"})
_SWITCHES = frozenset({"-i", "--allow-escape-sequences", "--include", "--paginate", "--silent", "--slurp", "--verbose"})
_WRITE_METHODS = frozenset({"post", "put", "patch", "delete"})
_MUTATION = re.compile(r"\bmutation\b", _I)
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
    """True when a gh/glab api call in a command writes to pull or merge requests, or may.

    Any call that writes blocks. Otherwise the whole-text verdict of the first version of this filter stands, and is
    lifted only when the parser can vouch for every call: the command, and each quoted argument a call was found in,
    is written in the modelled syntax (_MODELLED), and every call is launched by the shell itself and has an endpoint
    and only options gh api has. So this filter never lets through what the first version blocked, except reads it
    has seen in full.
    """
    texts: List[str] = []
    calls = [(launched,) + _read_api_call(arguments) for arguments, launched in _api_calls(text, texts)]
    if any(writes for _, _, writes in calls):
        return True
    # No call found although the whole text has one (gh and api in different statements): nothing was read.
    seen_in_full = all(launched and endpoint is not None for launched, endpoint, _ in calls)
    lifted = bool(calls) and seen_in_full and all(map(_MODELLED.fullmatch, texts))
    return _whole_text_writes(text) and not lifted


def _whole_text_writes(text: str) -> bool:
    """The first verdict of this filter: an api call, a write marker and a pull request word, anywhere."""
    return bool(
        _API_CALL.search(text)
        and (_WRITE_METHOD.search(text) or _WRITE_FIELD.search(text))
        and _MR_ENDPOINT.search(text)
    )


def _api_calls(text: str, texts: List[str]) -> List[Tuple[List[str], bool]]:
    """The arguments of every gh/glab api call in a command, as the shell passes them, and whether the shell itself
    launches the call.

    A call is the word gh or glab followed by the word api; its arguments run to the next call or the end of the
    statement, so quoted text never cuts a call in two. The shell launches it when gh is the command word of its
    statement, after any assignments; launched by another program (``xargs gh api ...``) it may get arguments the
    text does not show. A quoted argument with a blank in it may be a command line for another shell
    (``sh -c '...'``), so it is read as a command too. Each text a call was found in, the command included, is
    appended to ``texts``.
    """
    calls: List[Tuple[List[str], bool]] = []
    for statement in _STATEMENT.findall(text):
        words = [_QUOTES.sub(r"\1\2", word) for word in _WORD.findall(statement)]
        command = next((i for i, word in enumerate(words) if not _ASSIGNMENT.match(word)), len(words))
        starts = [i for i in range(len(words) - 1) if words[i + 1] == "api" and _CLIENT.fullmatch(words[i])]
        calls += [(words[start + 2:end], start == command) for start, end in zip(starts, starts[1:] + [len(words)])]
        for word in words:
            if _BLANK.search(word):
                calls += _api_calls(word, texts)
    if calls:
        texts.append(text)
    return calls


def _read_api_call(arguments: List[str]) -> Tuple[Optional[str], bool]:
    """The endpoint of one gh/glab api call, and whether the call writes to pull or merge requests, or may.

    The arguments are read as gh's flag parser reads them (``-X PUT``, ``-XPUT``, ``-X=PUT``, ``--method=PUT``, and so
    for every option that takes a value), so ``-X GET`` inside a field value is a value, not the method. An option gh
    api does not have (a glab-only flag, bundled short options like ``-iX``) leaves the endpoint unknown (None):
    which argument is its value cannot be told. ``may`` is a GraphQL query read from a file, which cannot be inspected.
    """
    endpoint = method = None
    known, fields, from_file = True, False, False
    remaining = iter(arguments)
    for argument in remaining:
        if argument in _VALUE_OPTIONS:
            option, value = argument, next(remaining, "")
        elif argument.startswith("--"):
            option, _, value = argument.partition("=")
        else:
            option, value = argument[:2], argument[2:].lstrip("=")
        if option in ("-X", "--method"):
            method = value.lower()
        elif option in _FIELD_OPTIONS:
            fields = True
            from_file = from_file or option == "--input" or value.startswith("query=@")
        elif option in _VALUE_OPTIONS or argument in _SWITCHES:
            continue
        elif argument.startswith("-"):
            known = False
        elif endpoint is None:
            endpoint = argument
    call = " ".join(arguments)
    if (endpoint or "").lower() == "graphql":
        # GraphQL always travels as a POST, so only the query tells a read from a write.
        writes = from_file or bool(_MUTATION.search(call) and _MR_ENDPOINT.search(call))
    else:
        # With an explicit GET, fields are query parameters, not a request body.
        writes = (method in _WRITE_METHODS or (fields and method != "get")) and bool(_MR_ENDPOINT.search(call))
    return (endpoint if known else None), writes


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
