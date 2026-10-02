"""Tests for lib/pe_guard/filters.py: shell text filter, file write filter, tool lists."""
import itertools
import random
import re
import time

import pytest

from pe_guard import filters

# (command, a word of the reason it must be blocked for)
BLOCKED_COMMANDS = [
    ("git push --no-verify", "--no-verify"),
    ("git push --no-veri origin main", "--no-verify"),
    ("echo ok && git push --no-verify", "--no-verify"),
    ("git push --no-verbose", "--no-verify"),  # the --no-ve prefix rule also stops this; accepted
    ("git -c core.hookspath=/dev/null push", "core.hooksPath"),
    ("git -c CORE.HOOKSPATH=x push", "core.hooksPath"),
    ("cd sub; git config core.hooksPath .nohooks", "core.hooksPath"),
    ('echo \'{"disableAllHooks": true}\' > .claude/settings.local.json', "disableAllHooks"),
    ("GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath git push", "core.hooksPath"),
    ("Git_Config_Parameters=x git status", "GIT_CONFIG_"),
    ("rm .git/hooks/pre-push", "pre-push hook"),
    ("chmod -x .git/hooks/pre-push", "pre-push hook"),
    ("cd .git/hooks && chmod -x pre-push", "pre-push hook"),
    ('chmod -x "$(git rev-parse --git-path hooks)/pre-push"', "pre-push hook"),
    ('chmod -x "$(git rev-parse --git-common-dir)/hooks/pre-push"', "pre-push hook"),
    ('rm "$(git rev-parse --git-dir)/hooks/pre-push"', "pre-push hook"),
    ("cd .git && rm hooks/pre-push", "pre-push hook"),
    ("ls .git/pragmatic-engineering", "data folder"),
    ('cat "$(git rev-parse --git-common-dir)/pragmatic-engineering/events.jsonl"', "data folder"),
    ("rm -rf .git/pragmatic-engineering/step-zero", "data folder"),
    ('cp x.py "$(git rev-parse --git-common-dir)/pragmatic-engineering/step-zero/tools/privacy_check.py"', "data folder"),
    ("pe-guard uninstall", "uninstall and repair"),
    ("python3 -m pe_guard.cli repair", "uninstall and repair"),
    ("git push -o merge_request.create origin feature", "push options"),
    ("git push --push-option=merge_request.merge_when_pipeline_succeeds origin x", "push options"),
    # every merge_request.* push option, not only create and merge_when_pipeline_succeeds
    ("git push -o merge_request.auto_merge origin feature", "push options"),
    ("git push -o merge_request.description=ready origin feature", "push options"),
    ("git push --push-option=merge_request.auto_merge origin x", "push options"),
    ("git push --push-option merge_request.title=x origin x", "push options"),
    ('git push -o "merge_request.create" origin x', "push options"),
    ("git push -omerge_request.create origin x", "push options"),
    ("git -c push.pushOption=merge_request.create push", "push options"),
    ("git config --add push.pushOption merge_request.draft", "push options"),
    # spellings git accepts: abbreviated long option, bundled short options, an alias with no push word
    ("git push --pu=merge_request.create origin x", "push options"),
    ("git push --push-opt=merge_request.create origin x", "push options"),
    ("git push -uo merge_request.create origin x", "push options"),
    ("git push -uomerge_request.create origin x", "push options"),
    ("git p -o merge_request.create origin x", "push options"),
    # alternatives of the hooks directory and data folder patterns that no other case reaches alone
    ('cd "$(git rev-parse --git-dir)/hooks" && chmod -x pre-push', "pre-push hook"),
    ('cd "$(git rev-parse --git-common-dir)"/hooks && rm pre-push', "pre-push hook"),
    ('cat "$(git rev-parse --git-dir)/pragmatic-engineering/events.jsonl"', "data folder"),
    ('cat "$(git rev-parse --git-dir)"/pragmatic-engineering/events.jsonl', "data folder"),
    ("gh api -X POST repos/o/r/pulls -f title=x", "pull or merge requests"),
    ("gh api repos/o/r/pulls/1/merge --method PUT", "pull or merge requests"),
    ("gh api repos/o/r/pulls -F title=x", "pull or merge requests"),
    ("gh api repos/o/r/pulls/2 --input body.json", "pull or merge requests"),
    ("glab api projects/1/merge_requests -X POST", "pull or merge requests"),
    ("gh api graphql -f query='mutation { mergePullRequest(input: {}) { clientMutationId } }'", "pull or merge requests"),
    ("glab api graphql -f query='mutation { mergeRequestSetDraft(input: {}) { clientMutationId } }'", "pull or merge requests"),
    # a GraphQL query read from a file cannot be inspected: it is treated as a possible mutation
    ("gh api graphql -F query=@m.graphql", "pull or merge requests"),
    ("glab api graphql --raw-field query=@m.graphql", "pull or merge requests"),
    ("gh api graphql --input query.json", "pull or merge requests"),
    # --field and --raw-field, spelled out
    ("gh api repos/o/r/pulls --field title=x", "pull or merge requests"),
    ("glab api projects/1/merge_requests --raw-field title=x", "pull or merge requests"),
    # a REST call whose title merely says graphql is still a REST write
    ("gh api -X POST repos/o/r/pulls -f title='Move to graphql'", "pull or merge requests"),
    # a read exemption belongs to its own api call: it never covers a write next to it in the same command
    ("gh api graphql -f query='query { viewer { login } }' && gh api -X PUT repos/o/r/pulls/1/merge", "pull or merge requests"),
    ("gh api -X GET repos/o/r/pulls && gh api repos/o/r/pulls -f title=x -f head=a -f base=main", "pull or merge requests"),
    ("curl -X GET https://x && gh api repos/o/r/pulls -f title=x", "pull or merge requests"),
    ("git commit -m 'switch to gh api graphql' && gh api -X POST repos/o/r/pulls -f title=x", "pull or merge requests"),
    ("gh api -X GET repos/o/r/pulls || gh api repos/o/r/pulls -f title=x", "pull or merge requests"),
    ("gh api -X GET repos/o/r/pulls; gh api repos/o/r/pulls -f title=x", "pull or merge requests"),
    ("gh api -X GET repos/o/r/pulls & gh api repos/o/r/pulls -f title=x", "pull or merge requests"),
    ("gh api -X GET repos/o/r/pulls\ngh api repos/o/r/pulls -f title=x", "pull or merge requests"),
    (
        "gh api -X GET repos/o/r/pulls/1 --jq .title | xargs -I{} gh api repos/o/r/pulls -f title={} -f head=a -f base=main",
        "pull or merge requests",
    ),
    # the graphql endpoint is the first argument that is neither a flag nor a flag's value
    ("gh api -f graphql=1 -X PUT repos/o/r/pulls/1/merge", "pull or merge requests"),
    ("gh api -f title='graphql tips' -X PUT repos/o/r/pulls/1/merge", "pull or merge requests"),
    ('gh api -f title="graphql tips" -X PUT repos/o/r/pulls/1/merge', "pull or merge requests"),
    ("gh api --paginate graphql -F query=@m.graphql", "pull or merge requests"),
    ("gh api --hostname h graphql -F query=@m.graphql", "pull or merge requests"),
    ("gh api 'graphql' -F query=@m.graphql", "pull or merge requests"),
    ('gh api "graphql" -F query=@m.graphql', "pull or merge requests"),
    ("gh api GraphQL -F query=@m.graphql", "pull or merge requests"),
    # a call nested in a command substitution is a call of its own, even next to a read in the same statement
    ('gh api -X GET repos/o/r/pulls --jq "$(gh api repos/o/r/pulls -f title=x)"', "pull or merge requests"),
    # a separator inside quotes does not end the call, and neither does a backslash-newline continuation
    ('gh api -f title="a; b" -X PUT repos/o/r/pulls/1/merge', "pull or merge requests"),
    ("gh api -f title='a | b' -X PUT repos/o/r/pulls/1/merge", "pull or merge requests"),
    ("gh api graphql -f query='mutation {\n  mergePullRequest(input: {}) { clientMutationId }\n}'", "pull or merge requests"),
    ("gh api -X PUT \\\n  repos/o/r/pulls/1/merge", "pull or merge requests"),
    ("gh api \\\n  graphql -F query=@m.graphql", "pull or merge requests"),
    # every spelling of a query read from a file
    ("gh api graphql --field query=@m.graphql", "pull or merge requests"),
    ("gh api graphql -F 'query=@m.graphql'", "pull or merge requests"),
    ("gh api graphql --field=query=@m.graphql", "pull or merge requests"),
    # a bundled short option group may carry digits
    ("git push -4o merge_request.create origin x", "push options"),
    # when a command is not read unambiguously the whole-text verdict stands, whatever one call alone looks like:
    # an ampersand that belongs to a redirection is not a separator
    ("gh api repos/o/r/pulls 2>&1 -f title=x -f head=a -f base=main", "pull or merge requests"),
    ("gh api repos/o/r/pulls/1/merge &>/dev/null -X PUT", "pull or merge requests"),
    ("gh api repos/o/r/pulls >&2 -f title=x", "pull or merge requests"),
    ("gh api repos/o/r/pulls/1/merge <&0 -X PUT", "pull or merge requests"),
    # separators inside a command substitution do not split the call
    ("gh api repos/o/r/pulls/$(echo 1; echo)/merge -X PUT", "pull or merge requests"),
    ("gh api repos/o/r/pulls/$(echo 1 | cat)/merge -X PUT", "pull or merge requests"),
    ("gh api repos/o/r/pulls/$(true && echo 1)/merge -X PUT", "pull or merge requests"),
    ("gh api repos/o/r/pulls/$(echo 1\necho 2)/merge -X PUT", "pull or merge requests"),
    ("gh api repos/o/r/pulls/`echo 1; echo`/merge -X PUT", "pull or merge requests"),
    # an unbalanced quote (an apostrophe in a comment, an escaped quote) would pair with a later quote and join
    # statements, which widens the read exemption of the call before it
    ("# don't merge yet\ngh api repos/o/r/pulls -f title=x -f head=a -f base=main\ncurl -X GET 'https://example.org'", "pull or merge requests"),
    ('# say "hi\ngh api repos/o/r/pulls -f title=x -f head=a -f base=main\ncurl -X GET "https://example.org"', "pull or merge requests"),
    ("echo \\'; gh api repos/o/r/pulls -f title=x -f head=a -f base=main; curl -X GET 'https://example.org'", "pull or merge requests"),
    ('echo \\"; gh api repos/o/r/pulls -f title=x -f head=a -f base=main; curl -X GET "https://example.org"', "pull or merge requests"),
    ('echo "; gh api repos/o/r/pulls -f title=x -f head=a -f base=main; curl -X GET "https://example.org"', "pull or merge requests"),
    ("echo don't; gh api repos/o/r/pulls -f title=x -f head=a -f base=main; curl -X GET 'https://example.org'", "pull or merge requests"),
    # two stray apostrophes pair with each other, so the quotes balance by luck and still swallow the call between
    # them: comments and heredoc bodies are inert text to the shell
    ("# don't merge yet\ngh api repos/o/r/pulls -f title=x -f head=a -f base=main\ncurl -X GET 'a'\n# can't merge either", "pull or merge requests"),
    ("cat <<EOF\ndon't\nEOF\ngh api repos/o/r/pulls -f title=x -f head=a -f base=main\ncurl -X GET 'a'\ncat <<EOF\ncan't\nEOF", "pull or merge requests"),
    # a redirection that overrides noclobber ends in a pipe character
    ("gh api repos/o/r/pulls >| out.json -f title=x", "pull or merge requests"),
    # a backslash-escaped space keeps the words together: graphql here is part of a field value
    ("gh api -f title=a\\ graphql -X PUT repos/o/r/pulls/1/merge", "pull or merge requests"),
    # an endpoint built by the shell (or missing) cannot be judged by the call's own text: when the command names a
    # pull request elsewhere, the whole-text verdict stands
    ('EP=repos/o/r/pulls; gh api -X POST "$EP" -f title=x', "pull or merge requests"),
    ('EP=pulls gh api -X POST "$EP" -f title=x', "pull or merge requests"),
    ("EP=pulls gh api -X POST `echo x` -f title=x", "pull or merge requests"),
    ("echo pulls; glab api --method POST", "pull or merge requests"),
    # a gh and an api in different statements are not a call, but the whole text reads like one
    ("gh\napi repos/o/r/pulls -f title=x", "pull or merge requests"),
    # a read marker inside quotes belongs to a value, not to the call
    ("gh api repos/o/r/pulls -f title='support -X GET' -f head=a -f base=main", "pull or merge requests"),
    ('gh api repos/o/r/pulls -f title="uses --method GET" -f head=a -f base=main', "pull or merge requests"),
    ("gh api repos/o/r/pulls -f head=a -f base=main -H 'X-Note: -X GET'", "pull or merge requests"),
    # GETX is not the method GET
    ("gh api -X GETX repos/o/r/pulls -f title=x", "pull or merge requests"),
]

# flags of gh api that take the next argument as their value (gh 2.100.0, gh api --help); the value of
# --input is covered by its own passing case, because --input also marks a query read from a file
VALUE_FLAGS = [
    "-f", "-F", "-X", "-H", "-p", "-q", "-t",
    "--cache", "--field", "--header", "--hostname", "--jq", "--method", "--preview", "--raw-field", "--template",
]

PASSING_COMMANDS = [
    "git push",
    "git push origin feature",
    "git commit --no-verify -m wip",
    "git status && git log --oneline",
    "ls .git/hooks",
    "git log -- pragmatic-engineering/notes.md",
    "pe-guard status",
    "gh api repos/o/r/pulls",
    "gh api repos/o/r/issues -f title=x",
    "gh api repos/o/r/contents/README.md",
    # reads: a GraphQL query without mutation, and an explicit GET whose fields become query parameters
    "gh api graphql -f query='query { repository(owner:\"o\",name:\"r\") { pullRequest(number: 5) { title } } }'",
    "glab api graphql -f query='query { project(fullPath: \"o/r\") { mergeRequest(iid: \"4\") { title } } }'",
    "gh api -X GET repos/o/r/pulls -f state=closed -f per_page=100",
    "gh api graphql -f query='mutation { addStar(input: {starrableId: \"x\"}) { clientMutationId } }'",  # no PR
    "gh api --method GET repos/o/r/pulls -f state=open",
    "glab api --method=get projects/1/merge_requests -F state=opened",
    "gh api -XGET repos/o/r/pulls -f state=open",
    'gh api --method "GET" repos/o/r/pulls -f state=open',
    "gh api --input graphql repos/o/r/issues",  # a file named graphql, not the endpoint
    # syntax the parser models stays a read: continuations, an apostrophe inside double quotes, a substitution
    # without separators, an explicit GET with a value flag
    "gh api -X GET repos/o/r/pulls \\\n  -f state=open",
    "echo \"it's fine\" && gh api -X GET repos/o/r/pulls -f state=open",
    "gh api -X GET repos/o/r/pulls/$(git rev-parse HEAD) -f state=open",
    # a call whose own literal endpoint names no pull request is not a pull request write, whatever else is said
    "echo pulls; gh api -X PUT repos/o/r/issues/1 -f state=closed",
    "gh api -X GET repos/o/r/pulls -f title='#5' -f state=open",  # a hash inside quotes is not a comment
    "gh api -X GET repos/o/r/pulls/5#comment-1 -f state=open",  # a hash inside a word is not a comment
    "gh api -X GET repos/o/r/pulls -f n=$# -f state=open",  # $# is the argument count, not a comment
    # ambiguous syntax alone blocks nothing: the whole-text verdict needs an api call, a write marker and a pull
    # or merge request word, and the call here names none
    "gh api repos/o/r/issues 2>&1 -f title=x",
    "git add -f docs/pulls.md 2>&1",
    "gh api -X GET repos/o/r/pulls -f state=open --jq '.[0].title' | head -1",
    # only gh api and glab api calls are looked at, whatever else a command says about pulls
    "git add -f docs/pulls.md",
    # a flag of the next command is not a field of the api call before it
    "gh api repos/o/r/pulls; git add -f x",
    "gh api repos/o/r/pulls | grep -f patterns",
    "gh api repos/o/r/pulls\ngit add -f x",
    "gh api repos/o/r/pulls && git add -f x",
    # a quoted mention of gh api must not pair its quote with a quote of the next command
    "git commit -m 'switch to gh api graphql' && gh api graphql -f query='query { repository { pullRequest(number: 1) { id } } }'",
    "echo \"run gh api now\" && gh api -X GET repos/o/r/pulls -f state=open",
    # a GraphQL query that merely contains a word starting or ending like mutation is a read
    "gh api graphql -f query='query { search(query: \"mutations is:pr\", type: ISSUE, first: 5) { nodes { ... on PullRequest { title } } } }'",
    "gh api graphql -f query='query { repository(owner:\"o\",name:\"r\") { pullRequests(labels: [\"no_mutation\"], first: 5) { nodes { title } } } }'",
    # a file that merely has merge_request in its name is not a push option
    "python3 -m pytest tests/test_merge_request.py -q",
    "git push && python3 -m pytest tests/test_merge_request.py -q",
    "git add merge_request.py && git push",
    "curl -o merge_request.json https://example.org/api",
    "curl -o merge_request.json https://github.com/o/r",  # github is not the word git
    "sort -o merge_request.txt in.txt",
    "git log --abbrev-commit --typo merge_request.py",  # a long option that merely ends in o
    "git checkout release-o merge_request.py",  # a hyphen inside a word is not a short option
    "gh pr create --title x --body y",
    "python3 -m pytest tests/test_filters.py -q",
    "python3 tools/install_dev_hooks.py",
    "",
]


@pytest.mark.parametrize("command,word", BLOCKED_COMMANDS)
def test_suspicious_shell_commands_are_blocked(command, word):
    reason = filters.check_shell_command(command)
    assert reason and word in reason, reason


@pytest.mark.parametrize("command", PASSING_COMMANDS)
def test_ordinary_shell_commands_pass(command):
    assert filters.check_shell_command(command) is None


# what the module docstring declares open, and the limit of a glab-only value flag declared next to _VALUE_FLAGS
OPEN_FORMS = [
    'gh api "$EP" -f title=x',  # endpoint in a shell variable
    'git push "-o" merge_request.create',  # quoted option flag
    'git push -o "$OPT"',  # option value in a variable
    "gp -o merge_request.create",  # alias or function that hides the word git
    'eval "$cmd"',
    "$cmd",
    "curl -X POST https://api.example.org/repos/o/r/pulls -d x",  # another client calling the API directly
    "glab api --unknown-value-flag v graphql -F query=@m.graphql",  # the unknown flag's value hides the endpoint
]


@pytest.mark.parametrize("command", OPEN_FORMS)
def test_forms_a_textual_filter_cannot_see_stay_open_as_the_module_declares(command):
    assert filters.check_shell_command(command) is None


def test_thousands_of_api_calls_in_one_command_are_checked_in_linear_time():
    """Each api call is analysed once, on its own text: re-reading the tail for every call would take seconds."""
    command = "gh api -f a=b repos/o/r/issues " * 2000
    started = time.perf_counter()
    assert filters.check_shell_command(command) is None
    assert time.perf_counter() - started < 1.0


# The whole-text verdict of the first version of the filter (commit e0eac43): a command with a gh or glab api call,
# a write marker anywhere in it and a pull or merge request word anywhere in it is a write. The per-call analysis may
# lift that block only for a command it reads unambiguously and finds made of reads.
_WHOLE_API = re.compile(r"\b(?:gh|glab)\s+api\b", re.IGNORECASE)
_WHOLE_MR = re.compile(r"pulls|merge_requests|pullrequest|mergerequest", re.IGNORECASE)
_WHOLE_METHOD = re.compile(r"(?:-X\s*|--method[\s=]+)[\"']?(?:post|put|patch|delete)\b", re.IGNORECASE)
_WHOLE_FIELD = re.compile(r"(?:^|\s)(?:-f|--field|--raw-field|--input)(?=[\s=]|$)", re.IGNORECASE)

# calls the parser reads unambiguously and that read ({r} is where a redirection may go)
CLEAN_READS = [
    "gh api -X GET repos/o/r/pulls{r} -f state=closed -f per_page=100",
    "gh api --method GET repos/o/r/pulls{r} -f state=open",
    "gh api graphql{r} -f query='query { repository(owner:\"o\",name:\"r\") { pullRequest(number: 5) { title } } }'",
    "glab api graphql{r} -f query='query { project(fullPath: \"o/r\") { mergeRequest(iid: \"4\") { title } } }'",
    "gh api repos/o/r/pulls{r}",
    "git status{r}",
    "git commit -m 'switch to gh api graphql'{r}",
    "curl -X GET https://x{r}",
]
# calls that write, or may
WRITES = [
    "gh api -X PUT repos/o/r/pulls/1/merge{r}",
    "gh api repos/o/r/pulls{r} -f title=x -f head=a -f base=main",
    "gh api -X POST repos/o/r/pulls{r} -f title=x",
    "glab api projects/1/merge_requests{r} -X POST",
    "gh api graphql{r} -f query='mutation { mergePullRequest(input: {}) { clientMutationId } }'",
    "gh api graphql{r} -F query=@m.graphql",
    "gh api -f graphql=1{r} -X PUT repos/o/r/pulls/1/merge",
    "gh api repos/o/r/pulls{r} -f title='support -X GET' -f head=a -f base=main",
    'gh api -X POST "$EP"{r} -f title=x',  # the endpoint is built by the shell: it may be a pull request
    "glab api --method POST{r}",  # no endpoint at all
]
# fragments the parser cannot read unambiguously: an apostrophe in a comment, a lone double quote, escaped quotes,
# an escaped space, a separator inside a command substitution or backticks
APOSTROPHE_COMMENTS = ["# don't merge yet", "# can't merge either"]
FRAGMENTS = APOSTROPHE_COMMENTS + [
    '# say "hi', "echo \\'", 'echo \\"', "echo a\\ b", "echo $(echo 1; echo)", "echo `echo 1; echo`",
]
REDIRECTIONS = [" 2>&1", " &>/dev/null", " >&2", " <&0", " >| out.json"]
SEPARATORS = [" && ", " || ", "; ", " | ", "\n", " & "]


def whole_text_blocks(command):
    return bool(
        _WHOLE_API.search(command)
        and (_WHOLE_METHOD.search(command) or _WHOLE_FIELD.search(command))
        and _WHOLE_MR.search(command)
    )


def generated_commands():
    """(command, made only of clean reads) for chained commands that mix reads, writes and ambiguous syntax."""
    plain = [(part.replace("{r}", ""), True) for part in CLEAN_READS]
    plain += [(part.replace("{r}", ""), False) for part in WRITES]
    plain += [(part, False) for part in FRAGMENTS]
    redirected = [(part.replace("{r}", r), False) for part in CLEAN_READS + WRITES for r in REDIRECTIONS]
    for (first, first_clean), (second, second_clean) in itertools.product(plain, plain):
        for sep in SEPARATORS:
            yield first + sep + second, first_clean and second_clean
    for (call, _), (read, read_clean) in itertools.product(redirected, plain[: len(CLEAN_READS)]):
        for sep in SEPARATORS:
            yield call + sep + read, False
            yield read + sep + call, False
    # two apostrophes in comments pair up around a write and a read: the quotes balance by luck
    for first, second in itertools.product(APOSTROPHE_COMMENTS, repeat=2):
        for write, read in itertools.product(WRITES, CLEAN_READS):
            yield "\n".join([first, write.replace("{r}", ""), read.replace("{r}", ""), second]), False
    chooser = random.Random(20260930)
    for _ in range(3000):
        parts = [chooser.choice(plain + redirected) for _ in range(3)]
        seps = [chooser.choice(SEPARATORS) for _ in range(2)]
        yield parts[0][0] + seps[0] + parts[1][0] + seps[1] + parts[2][0], all(clean for _, clean in parts)


def test_a_command_the_whole_text_rule_blocked_stays_blocked_unless_it_is_made_of_clean_reads():
    """Monotonic: the per-call analysis lifts a block only for unambiguous commands in which every call reads."""
    lifted = kept = 0
    for command, clean_reads in generated_commands():
        verdict = filters.check_shell_command(command)
        if clean_reads:
            assert verdict is None, command
            lifted += whole_text_blocks(command)
        elif whole_text_blocks(command):
            assert verdict, command
            kept += 1
    assert lifted > 100 and kept > 3000, (lifted, kept)  # the generator really exercised both sides


@pytest.mark.parametrize("flag", VALUE_FLAGS)
def test_the_value_of_a_flag_is_never_taken_for_the_graphql_endpoint(flag):
    """``gh api -f graphql -X PUT ...`` is a REST write: here graphql is a flag value, not the endpoint."""
    reason = filters.check_shell_command("gh api %s graphql -X PUT repos/o/r/pulls/1/merge" % flag)
    assert reason and "pull or merge requests" in reason, reason


# (path, content after the write, a word of the reason it must be blocked for)
BLOCKED_WRITES = [
    ("/srv/repo/.git/hooks/pre-push", "#!/bin/sh\nexit 0\n", "pre-push hook"),
    ("/srv/repo/.GIT/HOOKS/PRE-PUSH", "", "pre-push hook"),
    ("/srv/bare.git/hooks/pre-push", "", "pre-push hook"),
    ("/srv/repo/.git/pragmatic-engineering/events.jsonl", "{}\n", "data folder"),
    ("/srv/repo/.git/pragmatic-engineering/step-zero/tools/privacy_check.py", "x = 1\n", "data folder"),
    ("/srv/repo/.git/pragmatic-engineering/step-zero/lib/pe_guard/filters.py", "", "data folder"),
    ("/srv/repo/.claude/settings.json", '{"disableAllHooks": true}', "disableAllHooks"),
    ("/srv/repo/.claude/settings.local.json", '{"DISABLEALLHOOKS": false}', "disableAllHooks"),
    ("~/.claude/settings.json", '{"disableAllHooks": true}', "disableAllHooks"),
    ("/srv/policy/managed-settings.json", '{"disableAllHooks": true}', "disableAllHooks"),
    ("/srv/repo/.claude/settings.json", None, "disableAllHooks"),
]

TEST_DATA = (
    "cases = ['git push --no-verify', 'disableAllHooks', '.git/hooks/pre-push', "
    "'core.hooksPath', 'GIT_CONFIG_COUNT', 'pe-guard uninstall']\n"
)

PASSING_WRITES = [
    ("/srv/repo/.claude/settings.json", '{"permissions": {"allow": []}}'),
    ("/srv/repo/.git/hooks/pre-commit", "#!/bin/sh\n"),
    ("/srv/repo/hooks/pre-push", "#!/bin/sh\n"),  # a hooks folder outside any git directory
    ("/srv/repo/tests/test_filters.py", TEST_DATA),
    ("/srv/repo/tests/support.py", TEST_DATA),
    ("/srv/repo/lib/pe_guard/filters.py", TEST_DATA),
    ("/srv/repo/tools/privacy_check.py", TEST_DATA),
    ("/srv/repo/pragmatic-engineering/notes.md", "notes\n"),
    ("/srv/repo/.git/config", "[remote \"origin\"]\n\turl = x\n"),
    ("/srv/repo/docs/settings.json", '{"disableAllHooks": true}'),
    ("", None),
]


@pytest.mark.parametrize("path,content,word", BLOCKED_WRITES)
def test_writes_that_would_switch_the_guard_off_are_blocked(path, content, word):
    reason = filters.check_file_write(path, content)
    assert reason and word in reason, reason


@pytest.mark.parametrize("path,content", PASSING_WRITES)
def test_ordinary_writes_pass_even_with_guard_words_as_data(path, content):
    assert filters.check_file_write(path, content) is None


@pytest.mark.parametrize("name,expected", [
    ("mcp__gitlab__push_files", True),
    ("mcp__github__create_or_update_file", True),
    ("mcp__github__delete_file", True),
    ("mcp__gitlab__create_merge_request", False),
    ("push_files", False),
    ("mcp__x__push_files_extra", False),
    ("mcp__x__push_files extra", False),  # the whole name must match, not a prefix of it
    ("mcp__x__push-files", True),  # hyphenated spellings of the same tools
    ("mcp__x__create-or-update-file", True),
    ("mcp__x__delete-file", True),
    ("mcp__x__push-files-extra", False),
    ("Bash", False),
])
def test_remote_write_mcp_tools(name, expected):
    assert filters.is_remote_write_mcp_tool(name) is expected


@pytest.mark.parametrize("name,expected", [
    ("mcp__github__create_pull_request", "create"),
    ("mcp__gitlab__create_merge_request", "create"),
    ("mcp__github__update_pull_request", "update"),
    ("mcp__gitlab__update_merge_request", "update"),
    ("mcp__gitlab__merge_merge_request", "merge"),
    ("mcp__github__merge_pull_request", "merge"),
    ("mcp__gitlab__get_merge_request", None),
    ("mcp__x__create-pull-request", "create"),  # hyphenated spellings of the same tools
    ("mcp__x__update-merge-request", "update"),
    ("mcp__x__merge-pull-request", "merge"),
    ("mcp__x__get-merge-request", None),
    ("Bash", None),
])
def test_merge_request_mcp_tools(name, expected):
    assert filters.mr_action_kind(name) == expected


@pytest.mark.parametrize("command,expected", [
    ("gh pr create --title x --body y", "create"),
    ("gh pr new --fill", "create"),
    ("/opt/homebrew/bin/gh pr edit 5 --body y", "update"),
    ("git push && gh pr merge 3 --squash", "merge"),
    ("glab mr create --title x", "create"),
    ("glab mr update 4 --description z", "update"),
    ("glab mr merge 4", "merge"),
    ("gh pr view 5", None),
    ("echo gh pr", None),
])
def test_pr_commands_are_recognised(command, expected):
    assert filters.pr_command_kind(command) == expected
