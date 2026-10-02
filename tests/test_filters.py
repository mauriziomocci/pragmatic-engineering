"""Tests for lib/pe_guard/filters.py: shell text filter, file write filter, tool lists."""
import itertools
import random
import re
import string
import time

import pytest

from pe_guard import filters

# a read that names pulls and has a field: chained to a write the first version of the filter could not see, it made
# that version block the whole command
CHAINED_READ = "; gh api -X GET repos/o/r/pulls -f state=open"

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
    # the abbreviation is found anywhere in a run of letters and hyphens, as the linear form of the pattern must keep
    ("git push x--pu=merge_request.create origin", "push options"),
    ("git push --pu--pu=merge_request.create origin", "push options"),
    ("git push --pu--pu --pu-opt merge_request.create origin", "push options"),
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
    # PATCH and DELETE write without any field
    ("gh api -X PATCH repos/o/r/pulls/1", "pull or merge requests"),
    ("gh api --method DELETE repos/o/r/pulls/1/requested_reviewers", "pull or merge requests"),
    # a GraphQL query held in a shell variable: the expansion is outside the syntax the parser models
    (
        "Q='mutation { mergePullRequest(input: {pullRequestId: \"X\"}) { clientMutationId } }'; "
        "gh api graphql -f query=\"$Q\"",
        "pull or merge requests",
    ),
    (
        "Q='mutation { mergePullRequest(input: {pullRequestId: \"X\"}) { clientMutationId } }'\n"
        "gh api graphql -F query=\"$Q\"",
        "pull or merge requests",
    ),
    # separators inside process substitution (bash, zsh) and parameter expansion
    ("gh api repos/o/r/pulls/1/merge -t <(true; true) -X PUT", "pull or merge requests"),
    ("gh api repos/o/r/pulls/1/merge -t =(true; true) -X PUT", "pull or merge requests"),
    ("gh api repos/o/r/pulls/1/merge -t >(cat | cat) -X PUT", "pull or merge requests"),
    ("gh api repos/o/r/pulls/1/merge${x//;/} -X PUT", "pull or merge requests"),
    ("gh api repos/o/r/pulls${x:+&} -f title=x -f head=a -f base=main", "pull or merge requests"),
    # a quoted mention of gh api inside a write is a value: it does not cut the write in two
    (
        "gh api repos/o/r/pulls -H 'User-Agent: gh api client' -f title=x -f head=a -f base=main",
        "pull or merge requests",
    ),
    ('gh api repos/o/r/pulls/1/merge -H "X-Note: gh api x" -X PUT', "pull or merge requests"),
    # allowlist boundaries: each case is a write (bash or zsh) that the parser would read as a read if the allowlist
    # accepted the character named in the comment
    ("gh api repos/o/r/pulls -f title=x -f head=a -f base=main # -X GET", "pull or merge requests"),  # comment
    ("gh api repos/o/r/pulls -f title=x -f head=a -f base=main -t a\\ -XGET", "pull or merge requests"),  # backslash
    ("gh api repos/o/r/pulls -f title=x -f head=a -f base=main -t > -X GET", "pull or merge requests"),  # >
    ("gh api repos/o/r/pulls -f title=x -f head=a -f base=main -t <<< -X GET", "pull or merge requests"),  # <
    ("gh api repos/o/r/pulls -f title=x -f head=a -f base=main -t a\u00a0-XGET", "pull or merge requests"),  # non-ASCII
    ("gh api repos/o/r/pulls -f title=x -f head=a -f base=main -t a\r-XGET", "pull or merge requests"),  # other blanks
    ('gh api repos/o/r/pulls -f title=x -f head=a -f base=main -H "x:p\\" -X GET "q\\"', "pull or merge requests"),
    ('gh api repos/o/r/pulls -f title=x -f head=a -f base=main -H "x:p\\" -X GET -t "y\\"', "pull or merge requests"),
    ("gh api repos/o/r/pulls/1/merge -X `echo PUT`" + CHAINED_READ, "pull or merge requests"),  # backtick
    ('gh api repos/o/r/pulls/1/merge -X "`echo PUT`"' + CHAINED_READ, "pull or merge requests"),
    ("EP=repos/o/r/pulls; gh api -X POST $EP -f title=x", "pull or merge requests"),  # dollar
    ("gh api repos/o/r/pulls/1/merge {-X,} PUT" + CHAINED_READ, "pull or merge requests"),  # braces (bash)
    ("gh api repos/o/r/pulls/1/merge -X P*" + CHAINED_READ, "pull or merge requests"),  # globs, with a file PUT
    ("gh api repos/o/r/pulls/1/merge -X PU?" + CHAINED_READ, "pull or merge requests"),
    ("gh api repos/o/r/pulls/1/merge -X [P]UT" + CHAINED_READ, "pull or merge requests"),
    ("hash -d m=PUT; gh api repos/o/r/pulls/1/merge -X ~m" + CHAINED_READ, "pull or merge requests"),  # tilde (zsh)
    # the shell removes quotes: a quoted command name, option or method is still that word
    ("'gh' api repos/o/r/pulls/1/merge -X PUT" + CHAINED_READ, "pull or merge requests"),
    ("gh api repos/o/r/pulls/1/merge '-X' PUT" + CHAINED_READ, "pull or merge requests"),
    ("gh api repos/o/r/pulls/1/merge -X P'U'T" + CHAINED_READ, "pull or merge requests"),
    # gh found by a path, by zsh's =gh, or by another case on a case-insensitive file system
    ("/usr/local/bin/gh api repos/o/r/pulls/1/merge -X PUT" + CHAINED_READ, "pull or merge requests"),
    ("GH api repos/o/r/pulls/1/merge -X PUT" + CHAINED_READ, "pull or merge requests"),
    ("=gh api repos/o/r/pulls/1/merge -X PUT" + CHAINED_READ, "pull or merge requests"),
    # option spellings gh's flag parser accepts: a value attached with or without =, bundled short options
    ("gh api repos/o/r/pulls/1/merge -X=PUT" + CHAINED_READ, "pull or merge requests"),
    ("gh api repos/o/r/pulls -ftitle=x -fhead=a -fbase=main" + CHAINED_READ, "pull or merge requests"),
    ("gh api repos/o/r/pulls/1/merge -iXPUT" + CHAINED_READ, "pull or merge requests"),
    ("gh api repos/o/r/pulls/1/merge -iX PUT" + CHAINED_READ, "pull or merge requests"),
    # a call that another program launches may get arguments the text does not show (xargs appends -X PUT here)
    ("echo -X PUT | xargs gh api repos/o/r/pulls/1/merge", "pull or merge requests"),
    # a quoted argument may be a command line for another shell: it is read as a command of its own
    ("sh -c 'gh api repos/o/r/pulls/1/merge -X PUT'" + CHAINED_READ, "pull or merge requests"),
    ("sh -c 'gh api graphql -F query=@m.graphql'", "pull or merge requests"),
    ("sh -c 'gh api repos/o/r/pulls/$(echo 1; echo)/merge -X PUT'" + CHAINED_READ, "pull or merge requests"),
    # gh hands the options written before its subcommand to that subcommand
    ("gh --hostname x api repos/o/r/pulls/1/merge -X PUT", "pull or merge requests"),
    ("gh --hostname x api repos/o/r/pulls/1/merge -X PUT" + CHAINED_READ, "pull or merge requests"),
    ("gh -X PUT api repos/o/r/pulls/1/merge", "pull or merge requests"),
    ("gh -X PUT api repos/o/r/pulls/1/merge" + CHAINED_READ, "pull or merge requests"),
    ('EP=repos/o/r/pulls/1/merge; gh -X PUT api "$EP"', "pull or merge requests"),  # seen by the whole-text verdict
    # an option with its value attached takes no value of its own: api, or the next option, comes right after it
    ("gh -XPUT api repos/o/r/pulls/1/merge", "pull or merge requests"),
    ("gh --hostname=x -X PUT api repos/o/r/pulls/1/merge", "pull or merge requests"),
    ("gh -F query=@m.graphql api graphql", "pull or merge requests"),  # a field before api belongs to the call
    # a path that merely ends in the word graphql is not the GraphQL endpoint
    ("gh api 'repos/o/r/pulls/1/merge?note=graphql' -X PUT", "pull or merge requests"),
    # graphql in the query string or the fragment of a REST endpoint is no GraphQL endpoint either, however it is
    # spelled: the endpoint is the path before the first ? or #
    ("gh api 'repos/o/r/pulls/1/merge?x=/graphql' -X PUT", "pull or merge requests"),
    ("gh api 'repos/o/r/pulls/1/merge#/graphql' -X PUT", "pull or merge requests"),
    ("gh api 'repos/o/r/pulls/1/merge?x=%2Fgraphql' -X PUT", "pull or merge requests"),
    ("gh api 'repos/o/r/pulls?x=/graphql' -f title=x -f head=a -f base=main", "pull or merge requests"),
    ("glab api 'projects/1/merge_requests/1/merge?x=/graphql' -X PUT", "pull or merge requests"),
    # the GraphQL endpoint spelled as a path, a URL, with a host, a query string or a trailing slash
    ("gh api /graphql -F query=@m.graphql", "pull or merge requests"),
    ("gh api /graphql -F query=@m.graphql" + CHAINED_READ, "pull or merge requests"),
    ("gh api https://api.github.com/graphql -F query=@m.graphql", "pull or merge requests"),
    ("gh api https://api.github.com/graphql -F query=@m.graphql" + CHAINED_READ, "pull or merge requests"),
    ("gh api api.github.com/graphql --input query.json", "pull or merge requests"),
    ("gh api '/graphql?x=1' -F query=@m.graphql", "pull or merge requests"),
    ("gh api graphql/ -F query=@m.graphql", "pull or merge requests"),
    ("gh api /graph%71l -F query=@m.graphql", "pull or merge requests"),  # percent-encoded, decoded by the server
    # a percent-encoded endpoint: the server decodes it
    ("gh api repos/o/r/pu%6Cls/1/merge -X PUT", "pull or merge requests"),
    # gh's parser strips one = from an attached value: -X==GET sends the method =GET, which gh rejects, not GET
    ("gh api -X==GET repos/o/r/pulls -f state=open", "pull or merge requests"),
    # a second positional argument leaves the arguments unknown; so do PowerShell's arrays and splatting, which turn
    # a,-X or @a into several arguments
    ("gh api repos/o/r/pulls/1/merge -t a,-X PUT", "pull or merge requests"),
    ("gh api repos/o/r/pulls/1/merge -t a,-X,PUT" + CHAINED_READ, "pull or merge requests"),
    ("gh api repos/o/r/pulls/1/merge -t @a" + CHAINED_READ, "pull or merge requests"),
    # a command line printf builds: the placeholders are a second and a third positional argument of the call
    ("printf 'gh api repos/o/r/pulls/1/merge %s PUT' -X | sh" + CHAINED_READ, "pull or merge requests"),
]

# Reads blocked by design: the whole-text verdict stands because the command leaves the syntax the parser models,
# or a call in it cannot be judged. This is the price of failing closed; a change that opens one of these must be a
# deliberate decision.
OVER_BLOCKS = [
    "gh api -X GET repos/o/r/pulls \\\n  -f state=open",  # a backslash, even a line continuation
    "gh api -X GET repos/o/r/pulls/$(git rev-parse HEAD) -f state=open",  # a substitution
    "gh api -X GET repos/o/r/pulls/5#comment-1 -f state=open",  # a hash, even inside a word
    "gh api -X GET repos/o/r/pulls -f n=$# -f state=open",
    "gh api -X GET repos/{owner}/{repo}/pulls -f state=open",  # gh's placeholders use braces
    "gh api -X GET repos/o/r/pulls -f state=open 2>&1",  # a redirection
    "gh api -X GET repos/o/r/pulls -f state=open & gh api -X GET repos/o/r/pulls -f state=closed",  # a lone &
    'echo "run gh api" && gh api -X GET repos/o/r/pulls -f state=open',  # a quoted call with no endpoint
    # gh not launched by the shell itself (a wrapper, or a mention inside a text): its arguments may differ
    "env gh api -X GET repos/o/r/pulls -f state=open",
    # options before api: which word gh takes for its subcommand depends on them
    "gh --hostname x api -X GET repos/o/r/pulls -f state=open",
    # a call inside a quoted command line is vouched for only when the whole command is in the modelled syntax
    "sh -c 'gh api -X GET repos/o/r/pulls -f state=open' 2>&1",
    'echo "run gh api now" && gh api -X GET repos/o/r/pulls -f state=open',
    "git commit -m 'switch to gh api graphql' && "
    "gh api graphql -f query='query { repository { pullRequest(number: 1) { id } } }'",
    "glab api --unknown v -X GET projects/1/merge_requests -F state=opened",  # an option gh api does not have
    # the parser cannot tell what PowerShell's splatting or an array makes of these arguments, and so does not judge
    # them, though in bash they are plain reads
    "gh api -X GET repos/o/r/pulls -f state=open --jq @json",
    "gh api -X GET repos/o/r/pulls -f labels=a,-b",
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
    # reads in the syntax the parser models stay open: quotes of both kinds, chained reads, option spellings
    "echo \"it's fine\" && gh api -X GET repos/o/r/pulls -f state=open",
    "gh api -X GET repos/o/r/pulls -f title='#5' -f state=open",  # a hash inside quotes is not a comment
    "gh api -X GET repos/o/r/pulls -f state=open --jq '.[0].title' | head -1",
    "gh api -X GET repos/o/r/pulls -f state=open && "
    "gh api graphql -f query='query { repository(owner:\"o\",name:\"r\") { pullRequest(number: 5) { title } } }'",
    "gh api -X=GET repos/o/r/pulls -f state=open -q.title --jq=.title -Hx:y --header=x:y",
    "gh api -X GET repos/o/r/pulls\t-f labels=a,b -f q=a@b+c%20d",  # a tab and the safe punctuation
    "gh api repos/o/r/pulls -H 'X-Note: -X PUT'",  # a write marker inside a quoted value is a value
    # a GraphQL query read inline is a read, whatever spelling of the endpoint
    "gh api /graphql -f query='query { repository(owner:\"o\",name:\"r\") { pullRequest(number: 5) { title } } }'",
    # a call whose own literal endpoint names no pull request is not a pull request write, whatever else is said
    "echo pulls; gh api -X PUT repos/o/r/issues/1 -f state=closed",
    # syntax outside the model blocks nothing on its own: the whole-text verdict needs an api call, a write marker
    # and a pull or merge request word, and the call here names none
    "gh api repos/o/r/issues 2>&1 -f title=x",
    "git add -f docs/pulls.md 2>&1",
    # only gh api and glab api calls are looked at, whatever else a command says about pulls
    "git add -f docs/pulls.md",
    # a flag of the next command is not a field of the api call before it
    "gh api repos/o/r/pulls; git add -f x",
    "gh api repos/o/r/pulls | grep -f patterns",
    "gh api repos/o/r/pulls\ngit add -f x",
    "gh api repos/o/r/pulls && git add -f x",
    # assignments before the command word are part of the command the shell launches
    "GH_HOST=github.example.org GH_PAGER='cat -s' gh api -X GET repos/o/r/pulls -f state=open",
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


@pytest.mark.parametrize("command", OVER_BLOCKS)
def test_reads_the_parser_cannot_vouch_for_stay_blocked(command):
    reason = filters.check_shell_command(command)
    assert reason and "pull or merge requests" in reason, reason


# options of gh api (gh 2.100.0, gh api --help) that take no value, and those whose value is neither the method nor a
# field: a read that uses any of them is still a read
SWITCHES = ["-i", "--include", "--paginate", "--silent", "--slurp", "--verbose", "--allow-escape-sequences"]
OTHER_VALUE_OPTIONS = ["-H", "-p", "-q", "-t", "--cache", "--header", "--hostname", "--jq", "--preview", "--template"]


@pytest.mark.parametrize("option", SWITCHES + [option + " v" for option in OTHER_VALUE_OPTIONS])
def test_a_read_with_any_option_of_gh_api_stays_open(option):
    assert filters.check_shell_command("gh api %s -X GET repos/o/r/pulls -f state=open" % option) is None


# what the module docstring declares open
OPEN_FORMS = [
    'gh api "$EP" -f title=x',  # endpoint in a shell variable
    'git push "-o" merge_request.create',  # quoted option flag of git
    'git push -o "$OPT"',  # option value in a variable
    "gp -o merge_request.create",  # alias or function that hides the command
    'eval "$cmd"',
    "$cmd",
    "curl -X POST https://api.example.org/repos/o/r/pulls -d x",  # another client calling the API directly
    "gh api repos/o/r/pulls/1/merge -iX PUT",  # bundled short options are not parsed
    "glab api --unknown-value-flag v graphql -F query=@m.graphql",  # a glab-only option's value hides the endpoint
    # a command line that another program builds from text is read as written, even next to a read that names pulls
    "sh -c 'g$(echo h) api repos/o/r/pulls/1/merge -X PUT'" + CHAINED_READ,
    "sh -c 'g`echo h` api repos/o/r/pulls/1/merge -X PUT'" + CHAINED_READ,
    "sh -c 'g\\h api repos/o/r/pulls/1/merge -X PUT'" + CHAINED_READ,
    "sh -c 'gh ap\\i repos/o/r/pulls/1/merge -X PUT'" + CHAINED_READ,
    "printf 'gh api repos/o/r/pulls/1/merge%s' ' -X PUT' | sh" + CHAINED_READ,
    # the program name or the arguments come from another command: $0 is the word after the quoted text, and xargs
    # appends the words echo prints to the gh it starts
    "sh -c '$0 api repos/o/r/pulls/1/merge -X PUT' gh" + CHAINED_READ,
    "echo api repos/o/r/pulls/1/merge -X PUT | xargs gh" + CHAINED_READ,
]


@pytest.mark.parametrize("command", OPEN_FORMS)
def test_forms_a_textual_filter_cannot_see_stay_open_as_the_module_declares(command):
    assert filters.check_shell_command(command) is None


@pytest.mark.parametrize("command", [
    "gh api -f a=b repos/o/r/issues " * 2000,
    "gh -a " * 20000,  # each gh starts a run of options with gh as values: scanning every run again is quadratic
])
def test_thousands_of_api_calls_in_one_command_are_checked_in_linear_time(command):
    """Each api call is analysed once, on its own text: re-reading the tail for every call would take seconds."""
    started = time.perf_counter()
    assert filters.check_shell_command(command) is None
    assert time.perf_counter() - started < 1.0


def test_a_long_run_of_push_option_prefixes_is_checked_in_linear_time():
    """A hook that times out lets the tool run, so 100 KB of repeated --pu must not take a second."""
    command = "git status " + "--pu" * 25000
    started = time.perf_counter()
    assert filters.check_shell_command(command) is None
    assert time.perf_counter() - started < 1.0


# The whole-text verdict of the first version of the filter (commit e0eac43), copied here so that the oracle does not
# depend on the code it checks: a command with a gh or glab api call, a write marker anywhere in it and a pull or merge
# request word anywhere in it is a write.
_WHOLE_API = re.compile(r"\b(?:gh|glab)\s+api\b", re.IGNORECASE)
_WHOLE_MR = re.compile(r"pulls|merge_requests|pullrequest|mergerequest", re.IGNORECASE)
_WHOLE_METHOD = re.compile(r"(?:-X\s*|--method[\s=]+)[\"']?(?:post|put|patch|delete)\b", re.IGNORECASE)
_WHOLE_FIELD = re.compile(r"(?:^|\s)(?:-f|--field|--raw-field|--input)(?=[\s=]|$)", re.IGNORECASE)


def whole_text_blocks(command):
    return bool(
        _WHOLE_API.search(command)
        and (_WHOLE_METHOD.search(command) or _WHOLE_FIELD.search(command))
        and _WHOLE_MR.search(command)
    )


# The allowlist of the syntax the parser models, written again as a scanner rather than a regular expression: outside
# quotes only letters, digits, _ - . / = : @ , + %, space, tab, newline, ; | and &&; single-quoted text with anything;
# double-quoted text without $, backtick or backslash.
MODELLED_OUTSIDE_QUOTES = frozenset(string.ascii_letters + string.digits + "_-./=:@,+% \t\n;|")


def written_in_modelled_syntax(command):
    position = 0
    while position < len(command):
        char = command[position]
        if char in "'\"":
            end = command.find(char, position + 1)
            if end < 0 or (char == '"' and set(command[position + 1:end]) & set("$`\\")):
                return False
            position = end + 1
        elif command.startswith("&&", position):
            position += 2
        elif char in MODELLED_OUTSIDE_QUOTES:
            position += 1
        else:
            return False
    return True


# calls that read, written in the modelled syntax
CLEAN_READS = [
    "gh api -X GET repos/o/r/pulls -f state=closed -f per_page=100",
    "gh api --method GET repos/o/r/pulls -f state=open",
    "gh api graphql -f query='query { repository(owner:\"o\",name:\"r\") { pullRequest(number: 5) { title } } }'",
    "glab api graphql -f query='query { project(fullPath: \"o/r\") { mergeRequest(iid: \"4\") { title } } }'",
    "gh api repos/o/r/pulls",
    "git status",
    "git commit -m 'read pulls through the graphql api'",
    "curl -X GET https://x",
]
# Pull or merge request writes (and two reads) with a slot {x} for an injected construct. The slot sits where text the
# shell leaves alone keeps the call what it is; what the shell does with a construct (expand, substitute, redirect,
# comment out) may change the call, and that is why the whole-text verdict must stand for it.
WRITE_TEMPLATES = [
    "gh api repos/o/r/pulls/1/merge{x} -X PUT",
    "gh api repos/o/r/pulls/1/merge -t a{x} -X PUT",
    "gh api repos/o/r/pulls/1/merge -t {x} -X PUT",
    "gh api repos/o/r/pulls{x} -f title=x -f head=a -f base=main",
    "gh api repos/o/r/pulls -H {x} -f title=x -f head=a -f base=main",
    "gh api -X POST repos/o/r/pulls -f title={x}",
    "glab api projects/1/merge_requests{x} -X POST",
    "gh api graphql -H {x} -f query='mutation { mergePullRequest(input: {pullRequestId: \"X\"}) { clientMutationId } }'",
    "gh api graphql -F query=@m.graphql{x}",
    "gh api -f graphql=1 -X PUT repos/o/r/pulls/1/merge{x}",
    "gh --hostname x api repos/o/r/pulls/1/merge{x} -X PUT",  # options between the client and api
    "gh -X PUT api repos/o/r/pulls/1/merge{x}",
    "gh api /graphql -F query=@m.graphql{x}",  # the GraphQL endpoint as a path and as a URL
    "gh api https://api.github.com/graphql -F query=@m.graphql{x}",
    # a REST endpoint with graphql in its query string or fragment, quoted so that the command stays in the syntax the
    # parser models: it is not the GraphQL endpoint, whatever follows it
    "gh api 'repos/o/r/pulls/1/merge?x=/graphql'{x} -X PUT",
    "gh api 'repos/o/r/pulls/1/merge#/graphql'{x} -X PUT",
    "gh api 'repos/o/r/pulls?x=/graphql'{x} -f title=x -f head=a -f base=main",
    "glab api 'projects/1/merge_requests/1/merge?x=/graphql'{x} -X PUT",
]
READ_TEMPLATES = [
    "gh api -X GET repos/o/r/pulls{x} -f state=open",
    "gh api -X GET repos/o/r/pulls -t {x} -f state=open",
]
# The shell's alphabet, not the parser's: every printable ASCII character but the bare separators ; | and newline
# (they cut a write into two commands that do not write; SEPARATORS chain commands instead), other blanks, characters
# outside ASCII, and constructs built from them: quotes, expansions, substitutions, redirections, globs, comments.
SHELL_CONSTRUCTS = [char for char in string.printable if char not in ";|\n"] + [
    "\x00", "\u00a0", "\u2028", "\u00e9", "\uff1b",
    "''", '""', "'a;b'", '"a;b"', "'a b'", "'gh api x'", '"gh api x"', "'gh api'", "'-X GET'", '"-X GET"',
    "$x", "${x}", "${x//;/}", "${x:+&}", "${x:-a b}", "$(true; true)", "`true; true`", "$((1 + 1))", "$'a;b'", '$"a"',
    '"$x"', '"$(true; true)"', '"`true; true`"', '"\\""', "\\;", "\\\n", "\\ ",
    "<(true; true)", ">(cat | cat)", "=(true; true)", "(true; true)", "{ true; true; }", "{a,b}", "{1..2}",
    "*", "[ab]", "~", "~root", "!!", "!x", "#x", "2>&1", "&>/dev/null", ">|x", "<<<x", "<x", ">x", ">>x", "<>x",
    "|&", "&", "<<EOF\nx\nEOF\n",
]
MODELLED_SEPARATORS = [" && ", " || ", "; ", " | ", "\n"]
SEPARATORS = MODELLED_SEPARATORS + [" & "]


def injected(templates, construct):
    """Each template with the construct in its slot; a blank never fills a whole option value (it would shift the
    arguments, and the write would no longer be one)."""
    return [
        template.replace("{x}", construct) for template in templates if construct.strip() or " {x} " not in template
    ]


def generated_commands():
    """(command, made only of reads): chains of reads and writes, and calls with an injected construct, alone and
    next to a read that names pulls."""
    reads = [(read, True) for read in CLEAN_READS]
    writes = [(write.replace(" {x} ", " x:y ").replace("{x}", ""), False) for write in WRITE_TEMPLATES]
    for (first, first_read), (second, second_read) in itertools.product(reads + writes, repeat=2):
        for separator in SEPARATORS:
            yield first + separator + second, first_read and second_read
    marked = []
    for construct in SHELL_CONSTRUCTS:
        marked += [(command, False) for command in injected(WRITE_TEMPLATES, construct)]
        marked += [(command, True) for command in injected(READ_TEMPLATES, construct)]
    for command, read in marked:
        yield command, read
        for clean in (CLEAN_READS[0], CLEAN_READS[2]):
            yield command + "; " + clean, read
            yield clean + "\n" + command, read
    chooser = random.Random(20261002)
    for _ in range(3000):
        parts = [chooser.choice(reads + writes + marked) for _ in range(3)]
        separators = [chooser.choice(SEPARATORS) for _ in range(2)]
        command = parts[0][0] + separators[0] + parts[1][0] + separators[1] + parts[2][0]
        yield command, all(read for _, read in parts)


def test_a_command_the_whole_text_rule_blocked_stays_blocked_unless_modelled_and_made_of_reads():
    """Monotonic: what the first version blocked is open only when written in the modelled syntax and made of reads."""
    lifted = kept = 0
    for command, reads_only in generated_commands():
        if not whole_text_blocks(command):
            continue
        if filters.check_shell_command(command) is None:
            assert reads_only and written_in_modelled_syntax(command), command
            lifted += 1
        else:
            kept += 1
    assert lifted > 100 and kept > 3000, (lifted, kept)  # the generator really exercised both sides


def test_chains_of_clean_reads_stay_open():
    for first, second in itertools.product(CLEAN_READS, repeat=2):
        for separator in MODELLED_SEPARATORS:
            assert filters.check_shell_command(first + separator + second) is None, first + separator + second


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
    # options between the words belong to gh, glab and their subcommand: they do not hide the command
    ("gh -R o/r pr create --title x", "create"),
    ("gh pr -R o/r create --title x", "create"),
    ("gh --repo=o/r pr create --title x", "create"),
    ("gh --repo o/r pr edit 5 --body y", "update"),
    ("gh -R o/r pr -R o/r merge 3", "merge"),
    ("glab mr -R o/r create --title x", "create"),
    ("glab --repo o/r mr update 4", "update"),
    ("gh pr --help create", "create"),  # an option without a value, then the verb
    ("/opt/homebrew/bin/gh -R o/r pr new --fill", "create"),
    ("GH PR -r o/r CREATE --title x", "create"),
    # a backslash-newline between the words is a line continuation, not the end of the command
    ("gh -R o/r \\\n pr create --title x", "create"),
    ("gh pr \\\n create --title x", "create"),
    ("gh pr -R o/r \\\n  edit 5", "update"),
    # inside a word it joins the two halves, as the shell does: one word create here, one word o/rpr there
    ("gh pr cre\\\nate --title x", "create"),
    ("g\\\nh pr create --title x", "create"),
    ("gh -R o/r\\\npr create", None),
    # a verb counts only right after pr or mr and the options that follow it, never from another subcommand
    ("gh -R o/r pr view 5", None),
    ("gh pr list --search create", None),
    ("gh -R o/r issue create", None),
    ("gh repo create x", None),
    ("gh pr view 5 -R o/r edit", None),
    ("gh pr -R o/r", None),
    ("gh mr create", None),
    ("glab pr create", None),
    # quoted command words stay open, like the other forms a textual filter cannot see
    ('gh pr "create" --title x', None),
    ("'gh' pr create --title x", None),
])
def test_pr_commands_are_recognised(command, expected):
    assert filters.pr_command_kind(command) == expected


@pytest.mark.parametrize("command", [
    "gh -a " * 20000,  # every gh starts a run of options with the next gh as a value
    "gh pr -a " * 20000,
    "gh pr " + "-a " * 50000,
    "gh " + "-a " * 50000,
    "gh pr " + "-a b " * 30000,
    "glab mr " * 12000,
    "gh pr -a " * 20000 + "view",
], ids=["gh-runs", "gh-pr-runs", "options-after-pr", "options-after-gh", "options-with-values", "glab-mr-runs", "view-last"])
def test_long_runs_of_options_are_read_for_a_pr_command_in_linear_time(command):
    """The hook has 15 seconds and a hook that times out lets the tool run: no run of options may cost a second."""
    started = time.perf_counter()
    assert filters.pr_command_kind(command) is None
    assert time.perf_counter() - started < 1.0
