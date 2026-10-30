"""Text filters shared by the project hook of step zero and the PreToolUse guard of A2.

Both checks are deliberately textual and apply to the whole command, with no
prefix exemption: ``echo ok && git push --no-verify`` is caught like
``git push --no-verify``. They defend against the model's haste (retrying a
blocked push with --no-verify, turning hooks off), not against a user who is
determined to bypass them.

What a textual filter cannot see stays open, by design: a call the command
does not write out, because an endpoint, an option value or the whole command
is held in a variable (``gh api "$EP" -f ...``, ``git push -o "$OPT"``,
``$cmd``, ``eval "$cmd"``), hidden by a shell, git or gh alias or function, or
written in a script file the command runs (``bash make-pr.sh``);
a quoted option flag of git (``git push "-o" ...``); bundled short options of
gh api (``-iX PUT``); a quoted command word of a pull request command
(``gh pr "create"``, ``'gh' pr create``, which ``pr_command_kind`` does not
read, while options between its words are); and ``curl`` or any other client
calling the API directly.

For raw API writes the filter keeps every block of its first version, which
blocked a command with an api call, a write marker and a pull or merge request
word, each anywhere in it. Such a command is let through only when every
gh/glab api call written in it is one the parser vouches for and judges, as bash
and zsh read the command, and none of them is a pull or merge request write as
``_read_api_call`` defines it; see ``_api_writes_requests``. glab api is read
with the options of gh api (glab's own could not be checked here, see
``_VALUE_OPTIONS``).

One class is carved out: text that another program turns into a command line
(``sh -c '...'``, ``eval '...'``, ``... | sh``) is read only for the calls
written out in it, so a call built there from pieces is not seen, even next to
a read the first version blocked:
``sh -c 'g$(echo h) api ...'``, ``sh -c 'g`echo h` api ...'``,
``sh -c 'g\\h api ...'``, ``sh -c 'gh ap\\i ...'``,
``printf 'gh api .../merge%s' ' -X PUT' | sh``. The same goes where another
program supplies the command word or the arguments of the call: ``sh -c '$0 api
.../merge -X PUT' gh`` (the shell fills ``$0`` with the word after the quoted
text) and ``echo api .../merge -X PUT | xargs gh`` (xargs appends what echo
prints to the gh it starts). This filter leaves both open; the project hook of
step zero (tools/dev_guard.py) blocks the second, as it blocks any gh or glab
word after xargs.
"""
import re
from pathlib import PurePath
from typing import Dict, List, NamedTuple, Optional, Set, Tuple
from urllib.parse import unquote

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
# The long option branch is written to be linear: an unanchored --pu[a-z-]* would, from every --pu of a long run such
# as --pu--pu--pu..., read on to the end of the run, and a hook that times out lets the tool run. It starts once per
# maximal run of letters and hyphens (the lookbehind), checks with the lookahead that the run holds --pu, takes the
# whole run and asks for the separator after it: the same commands as --pu[a-z-]*[\s=]+ at any place, since a match
# from a --pu inside a run always read on to the end of that run.
_MR_PUSH_OPTION = re.compile(
    r"(?:(?<![\w-])-[a-z0-9]*o\s*"
    r"|(?<![a-z-])(?=[a-z-]*--pu)[a-z-]+[\s=]+"
    r"|pushoption[\s=]+)[\"']?merge_request\.",
    _I,
)
# The whole-text verdict of the first version of this filter: an api call, a write marker and a pull or merge request
# word, each anywhere in the command. _api_writes_requests also counts a call with options between gh and api.
_API_CALL = re.compile(r"\b(?:gh|glab)\s+api\b", _I)
_MR_ENDPOINT = re.compile(r"pulls|merge_requests|pullrequest|mergerequest", _I)
_WRITE_METHOD = re.compile(r"(?:-X\s*|--method[\s=]+)[\"']?(?:post|put|patch|delete)\b", _I)
_WRITE_FIELD = re.compile(r"(?:^|\s)(?:-f|--field|--raw-field|--input)(?=[\s=]|$)", _I)
# The syntax the parser models, an allowlist: outside quotes only word characters, - _ . / = : @ , + %, spaces, tabs
# and the separators && || ; | and newline; single-quoted text with anything; double-quoted text without $, backtick
# or backslash. Nothing in such a command expands, so the words below are exactly the arguments the shell passes; the
# one place where the allowlist alone would be wrong is shared with the hook of step zero, see the next constant.
_MODELLED = re.compile(r"(?:[\w\-.,/=:@+% \t\n;|]|&&|'[^']*'|\"[^\"$`\\]*\")*", re.ASCII)
# zsh expands an = or a tilde that follows empty quotes at the start of a word (''=gh is the path of gh, ''~ the home
# folder) as it does without the quotes. The start of a word is the start of the text, a blank or a separator.
EMPTY_QUOTES_BEFORE_EXPANSION = r"(?<![^\s;&|])(?:''|\"\")+[=~]"
_EMPTY_QUOTES_EXPANSION = re.compile(EMPTY_QUOTES_BEFORE_EXPANSION)
# Statements end at && || ; | & and newline outside quotes, but not at a backslash-newline continuation; words end at
# blanks outside quotes, and lose their quotes. A command outside the model is cut the same way, approximately: there
# its calls can only add blocks to the whole-text verdict.
_STATEMENT = re.compile(r"(?:\\\r?\n|\"[^\"]*\"|'[^']*'|[^|;&\n])+")
_WORD = re.compile(r"(?:[^\s\"'\\]|\\(?!\r?\n)|\"[^\"]*\"|'[^']*')+")
_QUOTES = re.compile(r"\"([^\"]*)\"|'([^']*)'")
_CLIENT = re.compile(r"(?:.*\W)?(gh|glab)", _I | re.DOTALL)  # also /usr/local/bin/gh, zsh's =gh, GH on macOS
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
# graphql, /graphql, a URL, a host prefix. Only the path before the first ? or # may precede the word: in a query string
# or a fragment graphql is data, and a REST endpoint with ?x=/graphql is still that endpoint.
_GRAPHQL = re.compile(r"(?:[^?#]*/)?graphql/?(?:[?#].*)?", _I | re.DOTALL)
_MUTATION = re.compile(r"\bmutation\b", _I)
_LINE_CONTINUATION = re.compile(r"\\\r?\n")
# What each verb of the pull or merge request commands does to the request, see pr_command_kind. A comment, a review,
# a closing comment and a reopening comment are updates: their text is as public as a body. A revert opens a request.
_PR_KIND = {
    "create": "create", "new": "create", "edit": "update", "update": "update", "merge": "merge",
    "comment": "update", "review": "update", "close": "update", "note": "update",
    "revert": "create", "reopen": "update",
}
_PR_VERB = re.compile(r"(%s)\b" % "|".join(_PR_KIND), _I)
# The subcommand word and the verbs of the pull or merge request commands of each client.
_PR_SUBCOMMANDS = {
    "gh": ("pr", frozenset({"create", "new", "edit", "merge", "comment", "review", "close", "revert", "reopen"})),
    "glab": ("mr", frozenset({"create", "new", "update", "merge", "note"})),
}
_MCP_TOOL = re.compile(r"mcp__.+__([A-Za-z0-9_-]+)")
_SETTINGS_NAME = re.compile(r"settings.*\.json", _I)


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

    Any call that writes blocks. A command in which the parser vouches for every call and judges every one of them
    passes. Otherwise the whole-text verdict of the first version of this filter stands: an api call, a write marker
    and a pull or merge request word, each anywhere in the command, where a call written with options between gh and
    api counts as an api call too.
    """
    calls = [(vouched,) + _read_api_call(arguments) for arguments, vouched in _api_calls(text)]
    if any(writes for _, _, writes in calls):
        return True
    # gh and api in different statements are no call to the parser, but the whole text reads like one: calls is empty
    if calls and all(vouched and judged for vouched, judged, _ in calls):
        return False
    return bool(
        (calls or _API_CALL.search(text))
        and (_WRITE_METHOD.search(text) or _WRITE_FIELD.search(text))
        and _MR_ENDPOINT.search(text)
    )


def _api_calls(text: str) -> List[Tuple[List[str], bool]]:
    """The arguments of every gh/glab api call in a command, as the shell passes them, and whether the parser vouches
    for the call.

    A call is the word gh or glab, any options with their values, then the word api: gh hands the options written
    before its subcommand to it, so they are arguments of the call, which run on to the next call or the end of the
    statement (quoted text never cuts a call in two). The parser vouches for a call written plainly: in a text in the
    modelled syntax (_MODELLED), with gh as the command word of its statement after any assignments, because a call
    that another program launches (``xargs gh api ...``) may get arguments the text does not show, and with api right
    after gh, because options before it decide which word gh takes for its subcommand. A quoted argument with a blank
    in it may be a command line for another shell (``sh -c '...'``), so it is read as a command too, and vouched for
    only if the text around it is in the modelled syntax as well.
    """
    modelled = _MODELLED.fullmatch(text) is not None and _EMPTY_QUOTES_EXPANSION.search(text) is None
    calls: List[Tuple[List[str], bool]] = []
    for statement in _STATEMENT.findall(text):
        words = [remove_quotes(word) for word in _WORD.findall(statement)]
        command = next((i for i, word in enumerate(words) if not _ASSIGNMENT.match(word)), len(words))
        found = _client_api_spans(words)
        for (client, api), following in zip(found, [client for client, _ in found[1:]] + [len(words)]):
            plain = modelled and client == command and api == client + 1
            calls.append((words[client + 1:api] + words[api + 1:following], plain))
        for word in words:
            if _BLANK.search(word):
                calls += [(arguments, modelled and vouched) for arguments, vouched in _api_calls(word)]
    return calls


def _client_api_spans(words: List[str]) -> List[Tuple[int, int]]:
    """The index of the client word and of the api word of every gh/glab api call among the words of one statement."""
    spans: List[Tuple[int, int]] = []
    position = 0
    while position < len(words):
        end = position + 1
        if _CLIENT.fullmatch(words[position]):
            end = _after_client_options(words, position)
            if end < len(words) and words[end] == "api":
                spans.append((position, end))
        position = end
    return spans


def _after_client_options(words: List[str], client: int) -> int:
    """The index of the first word after the options that follow the client word, each with its value if one follows."""
    end = client + 1
    while end < len(words) and words[end].startswith("-"):
        end += 1
        if end < len(words) and words[end] != "api" and not words[end].startswith("-"):
            end += 1
    return end


class _ApiArguments(NamedTuple):
    """The arguments of one gh/glab api call."""

    endpoint: Optional[str]
    method: Optional[str]
    fields: bool
    from_file: bool
    judged: bool


def _parse_api_arguments(arguments: List[str]) -> _ApiArguments:
    """Read the arguments as gh's flag parser does: ``-X PUT``, ``-XPUT``, ``-X=PUT`` with one ``=`` stripped,
    ``--method=PUT``, and so for every option that takes a value; ``-X GET`` inside a field value is therefore a
    value, not the method.

    ``judged`` is False when the call has an option gh api does not have or a second positional argument, or uses
    PowerShell's arrays or splatting, because then which argument is what stays open.
    """
    endpoint = method = None
    judged = not any(argument.startswith("@") or ",-" in argument for argument in arguments)
    fields = from_file = False
    remaining = iter(arguments)
    for argument in remaining:
        if argument in _VALUE_OPTIONS:
            option, value = argument, next(remaining, "")
        elif argument.startswith("--"):
            option, _, value = argument.partition("=")
        else:
            option, value = argument[:2], argument[3:] if argument[2:3] == "=" else argument[2:]
        if option in ("-X", "--method"):
            method = value.lower()
        elif option in _FIELD_OPTIONS:
            fields = True
            from_file = from_file or option == "--input" or value.startswith("query=@")
        elif option in _VALUE_OPTIONS or argument in _SWITCHES:
            continue
        elif argument.startswith("-") or endpoint is not None:
            judged = False
        else:
            endpoint = argument
    return _ApiArguments(endpoint, method, fields, from_file, judged)


def _read_api_call(arguments: List[str]) -> Tuple[bool, bool]:
    """Whether the parser can judge one gh/glab api call, and whether the call writes to pull or merge requests, or may.

    The call can be judged when it has one endpoint and only options gh api has: an option it does not have (a
    glab-only flag, bundled short options like ``-iX``) or a second positional argument leaves open which argument is
    what, and so do PowerShell's arrays and splatting, which turn ``a,-X`` and ``@a`` into several arguments.

    The call writes when it sends a method other than GET, or fields without an explicit GET, and its text names pulls
    or merge requests, percent-encoding decoded as the server decodes it; or when its endpoint is GraphQL (``graphql``,
    ``/graphql``, a URL or a host ending in graphql) and it sends a mutation naming a pull or merge request, or a query
    read from a file (``may``: a file cannot be inspected).
    """
    parsed = _parse_api_arguments(arguments)
    call = unquote(" ".join(arguments))
    if _GRAPHQL.fullmatch(unquote(parsed.endpoint or "")):
        # GraphQL always travels as a POST, so only the query tells a read from a write.
        writes = parsed.from_file or bool(_MUTATION.search(call) and _MR_ENDPOINT.search(call))
    else:
        # With an explicit GET, fields are query parameters, not a request body.
        method = parsed.method
        writes = (method in _WRITE_METHODS or (parsed.fields and method != "get")) and bool(_MR_ENDPOINT.search(call))
    return parsed.judged and parsed.endpoint is not None, writes


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


def remove_quotes(word: str) -> str:
    """The word with the quotes of its single and double quoted parts taken off, and nothing else done to it.

    A backslash stays, and so does the dollar sign of ``$'...'``; the text inside the quotes is kept as it is.
    """
    return _QUOTES.sub(r"\1\2", word)


# What the shell removes from a command before it hands the words on: a backslash outside quotes (it keeps the next
# character, and a backslash-newline goes whole), the quotes of a single-quoted part (its text is literal), and the
# quotes of a double-quoted part, where a backslash goes only before a quote, a backslash, a dollar sign, a backtick
# or a newline. Each character has one reading, so a part that never closes costs one scan of the rest of the text.
_QUOTING = re.compile(r"\\(\r?\n|.)|'([^']*)'|\"((?:[^\"\\]|\\.)*)\"", re.DOTALL)
_DOUBLE_QUOTE_ESCAPE = re.compile(r"\\(\r?\n|[\"\\$`])")


def _without_newline(escaped: str) -> str:
    return "" if escaped.endswith("\n") else escaped


def _quoting_removed(match: "re.Match[str]") -> str:
    escaped, single, double = match.groups()
    if escaped is not None:
        return _without_newline(escaped)
    if single is not None:
        return single
    return _DOUBLE_QUOTE_ESCAPE.sub(lambda inner: _without_newline(inner.group(1)), double)


def remove_shell_quoting(text: str) -> str:
    """The text with the quoting taken off as the shell takes it off, so that ``Zorb""lax``, ``'Zorb''lax'``,
    ``Zorb\\lax`` and ``'Dell'\\''Acqua'`` read as the words gh gets.

    Unlike ``remove_quotes`` it also drops the backslashes the shell drops. It models nothing else (no expansion, no
    word splitting, no ``$'...'``), so it is for adding a reading of a text to be searched, never for deciding that a
    command is clean.
    """
    return _QUOTING.sub(_quoting_removed, text)


def without_line_continuations(text: str) -> str:
    """The text with every backslash-newline removed, as the shell removes it before it reads the words.

    It joins what it cuts in two (``$`` and ``(cat x)``, ``Zorb`` and ``lax``). Inside single quotes the shell keeps the
    pair, so a text read this way may differ from what a single-quoted argument holds: callers that must see both
    read the text twice.
    """
    return _LINE_CONTINUATION.sub("", text)


# (client, still before the subcommand word?, did an option come last, so that the next word may be its value?)
_Reading = Tuple[str, bool, bool]


def pr_command_kind(command: str) -> Optional[str]:
    """'create', 'update' or 'merge' for gh pr / glab mr commands in a shell text, for the first one found.

    A comment, a review, a closing or reopening comment (``gh pr comment``, ``review``, ``close``, ``reopen``, ``glab
    mr note``) counts as an 'update': its text is as public as a body. ``gh pr revert`` opens a pull request: 'create'.

    The words of the text are read once, with every reading that is still possible kept alive, so the time is linear
    in the text (a pattern tried again from every gh of ``gh -a gh -a ...`` would not be). A command is a client word
    (gh or glab, also with a path in front), the subcommand word (pr for gh, mr for glab) and a verb, with options
    between them: ``gh -R o/r pr create``, ``gh pr -R o/r create`` and ``gh --repo=o/r pr create`` are found. An
    option is a word that starts with a hyphen and the word after it may be its value or the next word of the command;
    both readings are followed, so the check errs towards finding the command. The verb must come right after the
    subcommand and its options: ``gh pr view 5 -R o/r edit`` is not a pull request edit. A backslash-newline is
    removed, as the shell removes it: between words the blanks around it still part them, and inside a word it joins
    the two halves, so a verb cut in two by it is read whole. Quoted command words stay unseen, see the module
    docstring.
    """
    readings: Set[_Reading] = set()
    for word in without_line_continuations(command or "").split():
        client = _CLIENT.fullmatch(word)
        following = {(client.group(1).lower(), True, False)} if client else set()
        for reading in readings:
            kind, after_word = _read_word(reading, word)
            if kind:
                return kind
            following.update(after_word)
        readings = following
    return None


def _read_word(reading: _Reading, word: str) -> Tuple[Optional[str], List[_Reading]]:
    """The kind of the command when ``word`` is the verb that completes ``reading``, else the readings it leaves."""
    name, before_subcommand, after_option = reading
    subcommand, verbs = _PR_SUBCOMMANDS[name]
    option = word.startswith("-")
    if before_subcommand:
        after_word = [(name, False, False)] if word.lower() == subcommand else []
        return None, after_word + ([(name, True, option)] if option or after_option else [])
    verb = _PR_VERB.match(word)
    if verb and verb.group(1).lower() in verbs:
        return _PR_KIND[verb.group(1).lower()], []
    return None, [(name, False, option)] if option or after_option else []
