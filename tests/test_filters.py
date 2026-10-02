"""Tests for lib/pe_guard/filters.py: shell text filter, file write filter, tool lists."""
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
    ("gh api -X POST repos/o/r/pulls -f title=x", "pull or merge requests"),
    ("gh api repos/o/r/pulls/1/merge --method PUT", "pull or merge requests"),
    ("gh api repos/o/r/pulls -F title=x", "pull or merge requests"),
    ("gh api repos/o/r/pulls/2 --input body.json", "pull or merge requests"),
    ("glab api projects/1/merge_requests -X POST", "pull or merge requests"),
    ("gh api graphql -f query='mutation { mergePullRequest(input: {}) { clientMutationId } }'", "pull or merge requests"),
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
