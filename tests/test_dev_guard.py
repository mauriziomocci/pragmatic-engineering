"""Tests for tools/dev_guard.py, the project PreToolUse hook of step zero."""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

import dev_guard
import privacy_check
from support import REPO_ROOT, git, init_repo, run_script

SCRIPT = REPO_ROOT / "tools" / "dev_guard.py"
GUARD_WORDS = "git push --no-verify; disableAllHooks; .git/hooks/pre-push; core.hooksPath; GIT_CONFIG_COUNT"
HINT = "--body-file <path>"
# What each reason of the pull request text check says, so that a row proves which rule stopped it.
HEREDOC = "here-document"
STDIN = "comes from standard input"
EXPANSION = "substitution, a shell variable or another expansion"
STALE = "writes or names the body file elsewhere"
XARGS = "xargs builds the gh or glab command line when it runs"
CHANGES_FOLDER = "changes folder"
MISSING = "missing, a device, a pipe, a folder"
ATTACHED = "attached to a short option"


def run_hook(payload, cwd: Path):
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    return run_script(SCRIPT, [], cwd=cwd, stdin=stdin)


def bash_payload(repo: Path, command: str):
    return {"tool_name": "Bash", "cwd": str(repo), "tool_input": {"command": command}}


def repo_with_term(tmp_path: Path, term: str) -> Path:
    repo = init_repo(tmp_path / "repo")
    terms = tmp_path / "terms.txt"
    terms.write_text(term + "\n", encoding="utf-8")
    git(repo, "config", "pe.privateTermsFile", str(terms))
    return repo


@pytest.fixture
def repo_with_terms(tmp_path):
    return repo_with_term(tmp_path, "Zorblax")


@pytest.fixture
def repo_with_apostrophe_term(tmp_path):
    return repo_with_term(tmp_path, "Dell'Acqua")


def test_unknown_tool_passes(tmp_path):
    proc = run_hook({"tool_name": "Read", "tool_input": {"file_path": ".git/hooks/pre-push"}}, tmp_path)
    assert proc.returncode == 0, proc.stderr


def test_missing_tool_name_passes(tmp_path):
    assert run_hook({"tool_input": {"command": "git status"}}, tmp_path).returncode == 0


@pytest.mark.parametrize("payload,word", [
    ({"tool_input": {"command": "git push --no-verify"}}, "--no-verify"),
    ({"toolName": "Bash", "toolInput": {"command": "git push --no-verify"}}, "--no-verify"),
    ({"tool_name": "Bash", "toolInput": {"command": "git push --no-verify"}}, "--no-verify"),
    ({"tool_name": "Write", "toolInput": {"file_path": ".git/hooks/pre-push", "content": "exit 0\n"}}, "pre-push hook"),
])
def test_inputs_without_the_known_fields_are_checked_as_text(tmp_path, payload, word):
    proc = run_hook(payload, tmp_path)
    assert proc.returncode == 2
    assert word in proc.stderr


def test_null_tool_input_passes_for_shell(tmp_path):
    assert run_hook({"tool_name": "Bash", "tool_input": None}, tmp_path).returncode == 0


def test_unparsable_input_blocks(tmp_path):
    proc = run_hook("not json", tmp_path)
    assert proc.returncode == 2
    assert "unreadable hook input" in proc.stderr


def test_input_that_is_not_utf8_blocks(tmp_path):
    strict = dict(os.environ, PYTHONIOENCODING="utf-8:strict")  # some locales decode stdin leniently
    proc = subprocess.run([sys.executable, str(SCRIPT)], input=b'{"tool_name": "\xff"}', cwd=str(tmp_path),
                          capture_output=True, timeout=60, env=strict)
    assert proc.returncode == 2
    assert b"unreadable hook input" in proc.stderr


def test_non_object_input_blocks(tmp_path):
    assert run_hook("[1, 2]", tmp_path).returncode == 2


def test_input_nested_beyond_the_recursion_limit_blocks(tmp_path):
    """json.loads raises RecursionError, not ValueError, there: a traceback exits with 1, which does not block."""
    proc = run_hook("[" * 5000 + "]" * 5000, tmp_path)
    assert proc.returncode == 2
    assert "unreadable hook input" in proc.stderr


def test_broken_shared_module_blocks(tmp_path):
    copy = tmp_path / "copy"
    for part in ("tools", "lib"):
        shutil.copytree(str(REPO_ROOT / part), str(copy / part), ignore=shutil.ignore_patterns("__pycache__"))
    (copy / "lib" / "pe_guard" / "filters.py").write_text("def broken(:\n", encoding="utf-8")
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": "git status"}})
    proc = run_script(copy / "tools" / "dev_guard.py", [], cwd=tmp_path, stdin=payload)
    assert proc.returncode == 2
    assert "cannot load the checks" in proc.stderr


@pytest.mark.parametrize("tool", ["Bash", "PowerShell", "Monitor", "mcp__terminal__run_in_terminal"])
def test_every_shell_tool_is_filtered(tmp_path, tool):
    proc = run_hook({"tool_name": tool, "tool_input": {"command": "git push --no-verify"}, "cwd": str(tmp_path)}, tmp_path)
    assert proc.returncode == 2
    assert proc.stderr.startswith("dev_guard: ")


def test_shell_tool_without_command_field_checks_every_string():
    payload = {"tool_name": "PowerShell", "tool_input": {"script": "git -c core.hookspath=x push"}}
    reason = dev_guard.decide(payload)
    assert reason and "core.hooksPath" in reason


def test_write_to_the_pre_push_stub_blocks(tmp_path):
    payload = {"tool_name": "Write", "tool_input": {"file_path": str(tmp_path / ".git" / "hooks" / "pre-push"), "content": "exit 0\n"}}
    reason = dev_guard.decide(payload)
    assert reason and "pre-push hook" in reason


def test_edit_that_would_add_disable_all_hooks_blocks(tmp_path):
    settings = tmp_path / ".claude" / "settings.local.json"
    settings.parent.mkdir()
    settings.write_text('{"permissions": {}}\n', encoding="utf-8")
    payload = {"tool_name": "Edit", "tool_input": {
        "file_path": str(settings), "old_string": '"permissions": {}',
        "new_string": '"disableAllHooks": true, "permissions": {}', "replace_all": False}}
    reason = dev_guard.decide(payload)
    assert reason and "disableAllHooks" in reason


def test_edit_that_removes_disable_all_hooks_passes(tmp_path):
    settings = tmp_path / ".claude" / "settings.local.json"
    settings.parent.mkdir()
    settings.write_text('{"disableAllHooks": true, "permissions": {}}\n', encoding="utf-8")
    payload = {"tool_name": "Edit", "tool_input": {
        "file_path": str(settings), "old_string": '"disableAllHooks": true, ', "new_string": ""}}
    assert dev_guard.decide(payload) is None


def test_edits_of_files_holding_guard_words_as_test_data_pass(tmp_path):
    tests_dir = tmp_path / "repo" / "tests"
    tests_dir.mkdir(parents=True)
    target = tests_dir / "test_filters.py"
    target.write_text("CASES = []\n", encoding="utf-8")
    edit = {"tool_name": "Edit", "tool_input": {
        "file_path": str(target), "old_string": "CASES = []", "new_string": "CASES = [%r]" % GUARD_WORDS}}
    write = {"tool_name": "Write", "tool_input": {
        "file_path": str(tests_dir / "support.py"), "content": "WORDS = %r\n" % GUARD_WORDS}}
    assert dev_guard.decide(edit) is None
    assert dev_guard.decide(write) is None


def test_content_after_edit_applies_the_replacement(tmp_path):
    path = tmp_path / "f.txt"
    path.write_text("a a a", encoding="utf-8")
    assert dev_guard.content_after_edit(path, "a", "b", False) == "b a a"
    assert dev_guard.content_after_edit(path, "a", "b", True) == "b b b"
    assert dev_guard.content_after_edit(path, "zzz", "new", False) == "a a anew"
    assert dev_guard.content_after_edit(tmp_path / "missing.txt", "x", "y", False) == "y"


def test_remote_write_mcp_tool_blocks():
    reason = dev_guard.decide({"tool_name": "mcp__github__push_files", "tool_input": {}})
    assert reason and "MCP tools that write to a remote" in reason


def test_pr_create_with_a_private_term_blocks(repo_with_terms):
    payload = {"tool_name": "Bash", "cwd": str(repo_with_terms),
               "tool_input": {"command": 'gh pr create --title "Zorblax support" --body x'}}
    reason = dev_guard.decide(payload)
    assert reason and 'term "Zorblax" in the command' in reason


def test_clean_pr_create_passes(repo_with_terms):
    payload = {"tool_name": "Bash", "cwd": str(repo_with_terms),
               "tool_input": {"command": 'gh pr create --title "Add filters" --body "Tests included."'}}
    assert dev_guard.decide(payload) is None


def test_pr_body_file_is_checked(repo_with_terms):
    (repo_with_terms / "body.md").write_text("Made for Zorblax.\n", encoding="utf-8")
    payload = {"tool_name": "Bash", "cwd": str(repo_with_terms),
               "tool_input": {"command": "gh pr edit 3 --body-file body.md"}}
    reason = dev_guard.decide(payload)
    assert reason and 'term "Zorblax" in body file body.md' in reason


def test_pr_block_says_where_the_data_is(repo_with_terms):
    home_dir = "/" + "Users" + "/alice/plugins/pe"
    payload = {"tool_name": "Bash", "cwd": str(repo_with_terms),
               "tool_input": {"command": "cd %s && gh pr create --title x --body y" % home_dir}}
    reason = dev_guard.decide(payload)
    assert reason and "pattern home-path-macos in the command" in reason
    assert "not only the title and the body" in reason


@pytest.mark.parametrize("command", [
    'gh pr create --title x --body "$(cat body.md)"',
    "gh pr create --title x --body `cat body.md`",
    "gh pr create --title x -F - < body.md",
    "cat body.md | gh pr create --title x --body-file -",
    "gh pr create --title x --body \"$(cat <<EOF\n$(cat body.md)\nEOF\n)\"",
    "cat <<'EOF' | gh pr create --title \"$(cat title.txt)\" --body-file -\nClean body.\nEOF",
    "gh pr create --body-file - <<'EOF' --title \"$(cat title.txt)\"\nClean body.\nEOF",
    "gh pr create --body-file - <<'EOF' --title `cat title.txt`\nClean body.\nEOF",
    "gh pr create --title x --body-file /dev/stdin < body.md",
    "cat body.md | gh pr create --title x --body-file /dev/fd/0",
    'gh pr create --title x --body "Notes from $HOME"',
    'gh pr create --title "Release $1" --body x',
    "gh pr create --title x --body-file - <<EOF\nNotes from ${HOME}\nEOF",
])
def test_pr_body_the_hook_cannot_read_blocks(repo_with_terms, command):
    (repo_with_terms / "body.md").write_text("Made for Zorblax.\n", encoding="utf-8")
    payload = {"tool_name": "Bash", "cwd": str(repo_with_terms), "tool_input": {"command": command}}
    reason = dev_guard.decide(payload)
    assert reason and "--body-file <path>" in reason


@pytest.mark.parametrize("command", [
    # the standard form of a body written in the command, with and without text that holds a term or a substitution
    "gh pr create --title x --body \"$(cat <<'EOF'\nUses `sections()` now.\nEOF\n)\"",
    "gh pr create --title x --body \"$(cat <<'EOF'\nRun it from $HOME, see `notes`.\nEOF\n)\"",
    "gh pr create --title x --body \"$(cat <<'EOF'\nMade for Zorblax.\nEOF\n)\"",
    "gh pr create --title x --body \"$(cat <<'EOF'\nClean body.\nEOF\n)\"",
    "gh pr create --title x --body \"$(cat <<'EOF'\nClean body.\nEOF\n   )\"",
    "gh pr create --title x --body-file - <<'EOF'\nClean text.\nEOF",
    "gh pr create --title \"Clean title\" --body-file - <<'EOF'\nClean body.\nEOF",
    "/opt/homebrew/bin/gh pr create --title v1.2:fix,50%+@me --body-file=/dev/fd/0 <<\"EOF\"\nClean body.\nEOF\n\n  \n",
    "gh pr create --title x --body-file - <<-'EOF'\n\tClean body.\n\tEOF",
    "gh pr create --title x --body-file - <<'EOF'\nIndented:\n\tEOF\nEOF",
    "cat <<'EOF' | gh pr create --title x --body-file -\nClean body.\nEOF",
    "cat <<-'EOF' | gh pr create --title x --body-file -\n\tClean body.\n\tEOF",
    "cat <<\"EOF\" | gh pr create --title x -F /dev/stdin\nClean body.\nEOF",
    "cat <<'EOF' | gh pr create --title \"a | b\" --body-file -\nClean body.\nEOF",
    "gh pr create --title \"Handle <T> generics\" --body-file - <<'EOF'\nClean body.\nEOF",
    # a here-document of any spelling: unquoted, escaped or hyphenated tag, a second command's, in a quoted title
    "gh pr create --title x --body-file - <<EOF\nNotes from ${HOME}\nEOF",
    "gh pr create --title x --body \"$(cat <<EOF\nClean text.\nEOF\n)\"",
    "cat <<EOF | gh pr create --title x --body-file -\nClean text.\nEOF",
    "git commit -F - <<'EOF'\nA message.\nEOF\ngh pr create --title x --body y",
    "cat body.md | gh pr create --title \"<<EOF\" --body-file -",
    "gh pr create --title t --body \"Uses <<'EOF' in scripts\nand $(cat body.md)\"",
    "gh pr create --title t --body-file - <<'EOF'\nNo end here.\n$(cat body.md)",
    # a here-string reads its word at run time as well
    "cat <<< 'x'\ngh pr create --title t --body \"$(cat body.md)\"\nx",
    "cat <<<'x'\ngh pr create --title t --body \"$(cat body.md)\"\nx",
    "gh pr create --title t --body <<< Clean",
    # an operator in a quoted string, after a comment sign, in the body of an unquoted here-document: the shell may
    # not read it as one, and then the substitution next to it runs
    "gh pr create --title t --body \"Use <<'EOF' in scripts\n$(cat body.md)\nEOF\n\"",
    "gh pr create --title t --body-file sub/body.md # <<'EOF'\ngh pr edit 1 --body \"$(cat body.md)\"\nEOF",
    "cat <<EOF\n<<'X'\nEOF\ngh pr edit 1 --body \"$(cat body.md)\"\nX",
    # operators the shell reads in spite of what surrounds them: after a continued line, after a backslash, behind an
    # escaped quote that keeps a string open, in a command whose first word is not gh
    "cat <<'EOF' | gh pr create \\\n  --head \"$(cat title.txt)\" \\\n  --title x --body-file -\nClean text.\nEOF",
    "gh pr create --title x --body y <<'EOF' \\\n  --head \"$(cat title.txt)\"\nClean.\nEOF",
    "gh pr create --title x --body y \\<<'EOF'\ngh pr edit 1 --body \"$(cat body.md)\"\nEOF",
    "gh pr create --body-file - --title \"a \\\" <<'EOF'\n$(cat body.md)\"\nEOF",
])
def test_pr_command_with_a_here_document_or_a_here_string_blocks_with_the_hint(repo_with_terms, command):
    (repo_with_terms / "body.md").write_text("Made for Zorblax.\n", encoding="utf-8")
    reason = dev_guard.decide(bash_payload(repo_with_terms, command))
    assert reason and HEREDOC in reason and HINT in reason and "absolute path" in reason


def test_missing_pr_body_file_blocks(repo_with_terms):
    payload = {"tool_name": "Bash", "cwd": str(repo_with_terms),
               "tool_input": {"command": "gh pr create --title x -F missing.md"}}
    proc = run_hook(payload, repo_with_terms)
    assert proc.returncode == 2
    assert MISSING in proc.stderr and HINT in proc.stderr


@pytest.mark.parametrize("command", [
    'gh -R o/r pr create --title "Zorblax" --body x',
    'gh pr -R o/r create --title "Zorblax" --body x',
    'gh --repo=o/r pr create --title "Zorblax" --body x',
    'gh --repo o/r pr edit 3 --title "Zorblax"',
    'glab mr -R o/r create --title "Zorblax"',
    # a backslash-newline between the words is a line continuation, not the end of the command
    'gh -R o/r \\\n pr create --title "Zorblax" --body x',
    'gh pr \\\n create --title "Zorblax" --body x',
    # inside a word it joins the two halves, as bash and zsh do: gh gets create
    "gh pr cre\\\nate --title Zorblax",
])
def test_pr_command_with_options_between_its_words_is_checked(repo_with_terms, command):
    payload = {"tool_name": "Bash", "cwd": str(repo_with_terms), "tool_input": {"command": command}}
    reason = dev_guard.decide(payload)
    assert reason and 'term "Zorblax" in the command' in reason


def test_a_term_cut_in_two_by_a_backslash_newline_is_found(repo_with_terms):
    """The shell joins Zorb, the backslash-newline and lax: gh gets Zorblax."""
    reason = dev_guard.decide(bash_payload(repo_with_terms, "gh pr create --title Zorb\\\nlax --body y"))
    assert reason and 'term "Zorblax" in the command' in reason


def test_a_single_quoted_backslash_newline_is_checked_as_written_too(repo_with_terms):
    """The shell keeps the pair inside single quotes, so gh gets the trailing backslash that joining the lines drops."""
    home_dir = "C:\\" + "Users" + "\\alice\\"  # in parts: the repository carries no generic privacy pattern
    command = "gh pr create --title x --body '%s\n'" % home_dir
    reason = dev_guard.decide(bash_payload(repo_with_terms, command))
    assert reason and "pattern home-path-windows in the command" in reason


@pytest.mark.parametrize("command", [
    "gh pr create --title 'Fix Dell'\\''Acqua import' --body y",  # the usual apostrophe inside single quotes
    "gh pr create --title \"Fix Dell'Acqua import\" --body y",
    "gh pr create --title Fix --body 'for Dell'\\''Acqua'\\''s team'",
    "gh pr create --title 'Fix Dell'\"'\"'Acqua import' --body y",  # the other usual idiom
    "gh pr create --title Fix\\ Dell\\'Acqua --body y",  # a backslash before each blank and the apostrophe
    "gh pr create --title \"Fix Dell\"\\''Acqua'\" import\" --body y",  # three kinds of quoting in one word
])
def test_a_term_with_an_apostrophe_is_found_however_the_apostrophe_is_written(repo_with_apostrophe_term, command):
    """The shell joins the pieces and removes the quoting: gh gets Fix Dell'Acqua import."""
    reason = dev_guard.decide(bash_payload(repo_with_apostrophe_term, command))
    assert reason and "term \"Dell'Acqua\" in the command" in reason


@pytest.mark.parametrize("command", [
    "gh pr create --title Zorb\"\"lax --body y",  # empty quotes in the middle of the term
    "gh pr create --title 'Zorb''lax' --body y",
    "gh pr create --title Zorb\\lax --body y",  # a backslash before a letter is dropped
    "gh pr create --title \"Zor\"b'l'ax --body y",
    "gh pr comment 1 --body Z\\o\\r\\b\\l\\a\\x",
])
def test_a_term_split_by_quotes_or_backslashes_is_found(repo_with_terms, command):
    """The shell removes the quoting before gh sees the words, so gh gets Zorblax."""
    reason = dev_guard.decide(bash_payload(repo_with_terms, command))
    assert reason and 'term "Zorblax" in the command' in reason


def test_pr_body_file_of_a_command_with_options_between_its_words_is_checked(repo_with_terms):
    (repo_with_terms / "body.md").write_text("Made for Zorblax.\n", encoding="utf-8")
    payload = {"tool_name": "Bash", "cwd": str(repo_with_terms),
               "tool_input": {"command": "gh -R o/r pr create --title x --body-file body.md"}}
    reason = dev_guard.decide(payload)
    assert reason and 'term "Zorblax" in body file body.md' in reason


@pytest.mark.parametrize("command", [
    # a body file passed attached to its option, or bundled with other short options, is not found by name
    "gh pr create --title x -Fbody.md",
    "gh pr create --title x -dF body.md",
    "gh pr create --title x -dFbody.md",
    "gh pr create --title x -dF=body.md",
    # a relative body file is read from the folder the hook starts in, which a cd in the command changes
    "cd sub && gh pr create --title x --body-file body.md",
    "pushd sub; gh pr create --title x --body-file body.md",
    "(cd sub && gh pr edit 3 -F body.md)",
    # a body file that is a device, another process's file, a pipe or a folder: the hook would read its own input, or
    # wait, or fail
    "cat body.md | gh pr create --title x --body-file /proc/self/fd/0",
    "gh pr create --title x --body-file /dev/fd/3 3< body.md",
    "cat body.md | gh pr create --title x --body-file " + "../" * 40 + "dev/stdin",
    "cat body.md | gh pr create --title x --body-file /dev//stdin",
    "cat body.md | gh pr create --title x --body-file //dev/stdin",
    "gh pr create --title x --body-file /dev/tty",
    "gh pr create --title x --body-file .git",
    # process substitution (zsh also spells it =(...)), tilde and zsh's =command, each expanded at run time
    "gh pr create --title x --body-file <(cat body.md)",
    "gh pr create --title x --body y > >(tee pr.log)",
    "gh pr create --title x --body-file =(cat body.md)",
    "gh pr create --title x --body y --head ~/branch",
    "gh pr create --title x --body-file ~/pr-body.md",
    "gh pr create --title =gh --body y",
    # standard input: a name spelt with quotes the shell removes, or ended by a separator
    "cat body.md | gh pr create --title x --body-file \"\"-",
    "cat body.md | gh pr create --title x --body-file -; true",
])
def test_pr_body_in_a_form_the_hook_cannot_locate_blocks_with_the_hint(repo_with_terms, command):
    (repo_with_terms / "body.md").write_text("Made for Zorblax.\n", encoding="utf-8")
    reason = dev_guard.decide(bash_payload(repo_with_terms, command))
    assert reason and HINT in reason and "absolute path" in reason


# Rows with the reason that must stop each one, run through the hook as a process, so that the exit status is
# what is asserted. A row holds one construct where it can, so that taking its rule away leaves it
# passing or stopped by another reason. The N rows are forms that bash 3.2 or zsh turn into text the hook has not read
# (tags N1 to N7 are those of .superpowers/sdd/plan-a1/task-3-rereview-3.md).
HOOK_BLOCKS = [
    # the usual body in a substitution: in bash 3.2 a ")" in the body ends the substitution and the rest expands (N1),
    # as does a line that is the tag followed by ")" (N2)
    ("gh pr create --title \"Fix paths\" --body \"$(cat <<'EOF'\n## Summary\n1) Stop writing to $HOME directly\n"
     "2) Read the branch from `cat title.txt`\nEOF\n)\"", HEREDOC),
    ("gh pr create --title x --body \"$(cat <<'EOF'\nSmall fix :)\nSee $(cat body.md)\nEOF\n)\"", HEREDOC),
    ("gh pr create --title \"$(cat <<'EOF'\nFix the thing\nEOF)\" --head \"$(cat title.txt)\" "
     "--body \"$(cat <<'EOF'\nClean body.\nEOF\n)\"", HEREDOC),
    # an ANSI-C string keeps the operator line open (N3) and spells a term with an escape; a locale string
    ("gh pr create --title x --body y <<'EOF' --label $'it\\'s\n' --head \"$(cat title.txt)\"\nClean.\nEOF", HEREDOC),
    ("gh pr create --title $'Zorbl\\x61x' --body y", EXPANSION),
    ("gh pr create --title x --body y --label $'it\\'s'", EXPANSION),
    ("gh pr create --title $\"Zorblax\" --body y", EXPANSION),
    # zsh expands a tilde or =command after empty quotes (N4)
    ("gh pr create --title x --body y --head ''~/branch", EXPANSION),
    ("gh pr create --title x --body y --head \"\"~/branch", EXPANSION),
    ("gh pr create --title ''=gh --body y", EXPANSION),
    ("gh pr create --title \"\"=ls --body y", EXPANSION),
    # a here-document with a backslash or a hyphen in its tag, whose body holds the operator of another one (N7)
    ("cat <<\\EOF\n<<'X'\nEOF\ngh pr edit 1 --body \"$(cat body.md)\"\nX", HEREDOC),
    ("cat <<'PR-BODY'\n<<'X'\nPR-BODY\ngh pr edit 1 --body \"$(cat body.md)\"\nX", HEREDOC),
    # any << blocks: a here-document, even a quoted one, a here-string, an operator cut in two by a continuation
    ("gh pr create --title x --body y <<'EOF'\nClean.\nEOF", HEREDOC),
    ("gh pr create --title x --body y <<< Clean", HEREDOC),
    ("gh pr create --title x --body y <\\\n<'EOF'\nClean.\nEOF", HEREDOC),
    # standard input as the body file, whatever feeds it: no shape is allowed
    ("cat body.md | gh pr create --title x --body-file -", STDIN),
    ("cat body.md | gh pr create --title x -F /dev/stdin", STDIN),
    ("cat body.md | gh pr create --title x --body-file=/dev/fd/0", STDIN),
    ("gh pr create --title x -F - < body.md", STDIN),
    # a backslash-newline joins the lines: the name is - or /dev/stdin all the same (N5)
    ("cat body.md | gh pr create --title x --body-file \\\n-", STDIN),
    ("cat body.md | gh pr create --title x --body-file -\\\n", STDIN),
    ("cat body.md | gh pr create --title x --body-file /dev/\\\nstdin", STDIN),
    # and it joins a substitution that it cuts in two
    ("gh pr create --title x --body \"$\\\n(cat body.md)\"", EXPANSION),
    # any dollar sign followed by a character is an expansion in bash or zsh: parameter flags, arithmetic
    ("gh pr create --title x --body y --head $=HOME", EXPANSION),
    ("gh pr create --title x --body y --head $~HOME", EXPANSION),
    ("gh pr create --title x --body y --head $^HOME", EXPANSION),
    ("gh pr create --title x --body y --head $+HOME", EXPANSION),
    ("gh pr create --title x --body y --label $[6*7]", EXPANSION),
    # gh pr revert opens a pull request, gh pr reopen takes a comment: both are pull request commands
    ("cat body.md | gh pr revert 5 --body-file -", STDIN),
    ("gh pr revert 5 --body \"$(cat body.md)\"", EXPANSION),
    ("gh pr reopen 5 --comment \"$(cat body.md)\"", EXPANSION),
    # zsh's chdir changes folder as cd does
    ("chdir sub && gh pr create --title x --body-file pr.md", CHANGES_FOLDER),
    # a body file attached to its option; one that is not there, however the name is spelt (the shell rewrites \-)
    ("gh pr create --title x -Fbody.md", ATTACHED),
    ("gh pr create --title x -F missing.md", MISSING),
    ("cat body.md | gh pr create --title x --body-file \\-", MISSING),
]


@pytest.mark.parametrize("command,fragment", HOOK_BLOCKS)
def test_pr_text_the_hook_cannot_read_exits_with_2_and_says_why(repo_with_terms, command, fragment):
    (repo_with_terms / "body.md").write_text("Made for Zorblax.\n", encoding="utf-8")
    (repo_with_terms / "title.txt").write_text("Zorblax-branch\n", encoding="utf-8")
    proc = run_hook(bash_payload(repo_with_terms, command), repo_with_terms)
    assert proc.returncode == 2, proc.stderr
    assert fragment in proc.stderr
    assert proc.stderr.strip().endswith(dev_guard.BODY_HINT), proc.stderr  # the hint closes every such reason, once
    assert proc.stderr.count(HINT) == 1 and "in a separate step" in proc.stderr and "absolute path" in proc.stderr


@pytest.mark.parametrize("command", [
    # xargs builds the command line of the gh it starts at run time, with or without a verb in the text
    "cat title.txt | xargs gh pr create --body y --head",
    "head -1 title.txt | xargs -I{} gh pr create --title {} --body y",
    "cat args.txt | xargs gh pr",
    "cat args.txt | xargs -I{} gh pr create --title {}",
    "echo create --title Zorblax-branch --body y | xargs gh pr",
    "echo api repos/o/r/pulls/1/merge -X PUT | xargs gh",
    "cat title.txt | /usr/bin/xargs glab mr create --description",
    "cat title.txt | gxargs gh pr create --body y --head",
    "cat title.txt | xargs \\\n  gh pr create --body y --head",
    "xargs -a body.md gh pr create --title x --body y",  # GNU xargs -a adds the words of the file
    "echo xargs gh",  # the hook does not parse: the words xargs and then gh, in this order, block
    # the command line is a quoted argument of a shell that xargs starts, or the gh word is quoted itself
    "cat title.txt | xargs -I{} sh -c 'gh pr create --title {} --body y'",
    "cat title.txt | xargs -I{} bash -c \"gh pr create --title {} --body y\"",
    "cat title.txt | xargs -I{} \"gh\" pr create --title {}",
    # a read: there is no pull request and no body, so the reason does not speak of one
    "printf '%s\\n' 1 2 | xargs -n1 gh pr view",
    "gh pr list --json number -q '.[].number' | xargs -n1 gh pr view",
])
def test_xargs_that_starts_gh_blocks_with_exit_2_and_no_body_file_advice(repo_with_terms, command):
    (repo_with_terms / "title.txt").write_text("Zorblax-branch\n", encoding="utf-8")
    proc = run_hook(bash_payload(repo_with_terms, command), repo_with_terms)
    assert proc.returncode == 2, proc.stderr
    assert XARGS in proc.stderr
    assert HINT not in proc.stderr and "pull request" not in proc.stderr and "body" not in proc.stderr, proc.stderr


@pytest.mark.parametrize("command", [
    "cp notes.md {body} && gh pr create --title x --body-file {body}",
    "cp notes.md b.md && gh pr create --title x --body-file {body}",  # the copy is named by the basename only
    "cd {folder} && cp notes.md b.md && gh pr create --title x --body-file {body}",
    "gh pr create --title x --body-file {body}; echo > {body}",
    "echo > {body}; gh pr edit 3 -F {body}",
    "gh pr edit 3 --body-file={body} && tee b.md < notes.md",
    "printf '%s' hi >{body} && gh pr create --title x -F \"{body}\"",
    # the same name spelt with a quote inside a word, or in other letter case (the disk of a Mac ignores the case)
    "cp notes.md \"b\".md && gh pr create --title x --body-file {body}",
    "cp notes.md B.MD && gh pr create --title x --body-file {body}",
])
def test_a_body_file_that_the_command_writes_or_names_elsewhere_blocks(repo_with_terms, tmp_path, command):
    """The hook reads the file before the command runs, so a cp or a redirect in the same command makes it stale."""
    body = tmp_path / "b.md"
    body.write_text("Clean text.\n", encoding="utf-8")
    command = command.format(body=body, folder=tmp_path)
    proc = run_hook(bash_payload(repo_with_terms, command), repo_with_terms)
    assert proc.returncode == 2, proc.stderr
    assert STALE in proc.stderr and HINT in proc.stderr
    assert proc.stderr.count("in a separate step") == 1  # the hint says it once, the reason does not repeat it


@pytest.mark.parametrize("name,command", [
    # the name is one shell word whatever it holds: a blank inside quotes, a colon, an equals sign, a semicolon inside
    # quotes. The words of the rest of the command are read with the same grammar, so the name is found there
    ("pr body.md", "cp notes.md \"pr body.md\" && gh pr create --title x --body-file \"pr body.md\""),
    ("pr body.md", "cp notes.md 'pr body.md' && gh pr create --title x --body-file 'pr body.md'"),
    ("b:1.md", "cp notes.md b:1.md && gh pr create --title x --body-file b:1.md"),
    ("a=b.md", "cp notes.md a=b.md && gh pr create --title x --body-file a=b.md"),
    ("a;b.md", "cp notes.md 'a;b.md' && gh pr create --title x --body-file 'a;b.md'"),
    # and a name that is only a piece of a word there: the value of an assignment or of an option
    ("b.md", "dd if=notes.md of=b.md && gh pr create --title x --body-file b.md"),
    ("b.md", "cp notes.md out:b.md && gh pr create --title x --body-file b.md"),
])
def test_a_body_file_with_an_unusual_name_written_elsewhere_blocks(repo_with_terms, name, command):
    (repo_with_terms / name).write_text("Clean text.\n", encoding="utf-8")
    proc = run_hook(bash_payload(repo_with_terms, command), repo_with_terms)
    assert proc.returncode == 2, proc.stderr
    assert STALE in proc.stderr


@pytest.mark.parametrize("command", [
    # an odd escaped quote opens a quoted part for a reader that pairs quotes and does not read backslashes: the write
    # ends up inside one long word. The words are read a second way, split at blanks, so that the write is still seen
    "echo 5\\\" && cp notes.md b.md && gh pr create --title \"Fix\" --body-file b.md",
    "echo \"Support 5\\\" screens\" && cp notes.md b.md && gh pr create --title \"Fix\" --body-file b.md",
    "echo it\\'s && cp notes.md b.md && gh pr create --title 'Fix' --body-file b.md",
    "echo 5\\\" && cat notes.md >b.md && gh pr create --title \"Fix\" --body-file b.md",
])
def test_an_odd_escaped_quote_does_not_hide_a_write_of_the_body_file(repo_with_terms, command):
    (repo_with_terms / "b.md").write_text("Clean text.\n", encoding="utf-8")
    proc = run_hook(bash_payload(repo_with_terms, command), repo_with_terms)
    assert proc.returncode == 2, proc.stderr
    assert STALE in proc.stderr


def test_a_body_file_the_command_is_about_to_create_is_said_to_be_written_elsewhere(repo_with_terms):
    """The file is not there yet, which is why the command writes it: that is the reason to give, not the missing file."""
    command = "cp notes.md b.md && gh pr create --title x -F b.md"
    proc = run_hook(bash_payload(repo_with_terms, command), repo_with_terms)
    assert proc.returncode == 2
    assert STALE in proc.stderr and MISSING not in proc.stderr


@pytest.mark.parametrize("command", [
    "gh pr create --title x --body-file {body}",
    "gh pr edit 3 -F {body} -F {body}",
    "git status && gh pr create --title x --body-file={body}",
])
def test_a_clean_absolute_body_file_passes(repo_with_terms, tmp_path, command):
    body = tmp_path / "clean.md"
    body.write_text("Clean text.\n", encoding="utf-8")
    assert dev_guard.decide(bash_payload(repo_with_terms, command.format(body=body))) is None


@pytest.mark.parametrize("name", ["body", "file", "title"])
def test_a_body_file_named_like_a_piece_of_an_option_is_not_stale(repo_with_terms, name):
    """--body-file and --title are in the command, but the file is not named by them: a word must be the whole name."""
    (repo_with_terms / name).write_text("Clean text.\n", encoding="utf-8")
    assert dev_guard.decide(bash_payload(repo_with_terms, "gh pr create --title x --body-file %s" % name)) is None


@pytest.mark.parametrize("name", ["pr", "create", "gh"])
def test_a_body_file_named_like_a_word_of_the_command_itself_stays_an_over_block(repo_with_terms, name):
    """Accepted: gh pr create is in the rest of the command, and the hook does not tell a word of gh from a file."""
    (repo_with_terms / name).write_text("Clean text.\n", encoding="utf-8")
    reason = dev_guard.decide(bash_payload(repo_with_terms, "gh pr create --title x --body-file %s" % name))
    assert reason and STALE in reason


def test_every_body_file_of_a_command_is_read(repo_with_terms):
    for number in range(3):
        (repo_with_terms / ("n%d.md" % number)).write_text("Clean %d.\n" % number, encoding="utf-8")
    (repo_with_terms / "n2.md").write_text("Made for Zorblax.\n", encoding="utf-8")
    command = "gh pr create --title x" + "".join(" -F n%d.md" % number for number in range(3))
    reason = dev_guard.decide(bash_payload(repo_with_terms, command))
    assert reason and 'term "Zorblax" in body file n2.md' in reason


@pytest.mark.parametrize("command", [
    'gh pr create --title "Fix paths" --body "Plain text, 1) one :) two"',
    "gh pr view 5",
    'gh pr comment 1 --body "clean"',
    'gh pr review 1 --approve --body "clean"',
    "gh pr close 1 --comment clean",
    "glab mr note 1 -m clean",
    "gh pr revert 5 --title clean",
    "gh pr reopen 5 --comment clean",
    "gh pr create --title v1.2:fix,50%+@me --body 'A < B, C > D, E | F; G && H'",
    "gh pr create --title 'Costs $ 5' --body y",  # a dollar sign before a blank expands nothing
])
def test_pr_text_written_in_the_command_passes(repo_with_terms, command):
    assert dev_guard.decide(bash_payload(repo_with_terms, command)) is None


@pytest.mark.parametrize("command", [
    "ls | xargs rm",
    "echo ghost | xargs echo",  # ghost is not gh
    "gh pr list --json number | xargs -n1 echo",  # gh comes before xargs: xargs does not start it
    "gh pr create --title x --body y; ls | xargs rm",
    "ls | xargs -a gh-args.txt echo",  # gh-args.txt, gh_files and gh.exe are other words
    "ls | xargs echo gh_files gh.exe",
])
def test_xargs_without_a_gh_or_glab_word_after_it_passes(repo_with_terms, command):
    assert dev_guard.decide(bash_payload(repo_with_terms, command)) is None


@pytest.mark.parametrize("command", [
    "gh pr comment 1 --body Zorblax",
    "gh pr review 1 --body Zorblax",
    "gh pr close 1 --comment Zorblax",
    "glab mr note 1 -m Zorblax",
    "gh -R o/r pr comment 1 --body Zorblax",
    "gh pr revert 5 --title Zorblax",  # a revert opens a pull request
    "gh pr reopen 5 --comment Zorblax",
])
def test_the_text_of_a_comment_a_review_or_a_closing_comment_is_checked(repo_with_terms, command):
    reason = dev_guard.decide(bash_payload(repo_with_terms, command))
    assert reason and 'term "Zorblax" in the command' in reason


@pytest.mark.parametrize("command,name", [
    ('gh pr create --title x --body-file "-"x', "-x"),
    ('gh pr create --title x --body-file "clean.md"x', "clean.mdx"),
])
def test_a_body_file_name_glued_to_quotes_is_read_as_the_shell_passes_it(repo_with_terms, command, name):
    """The shell joins the quoted part and the rest into one word: gh reads -x, not standard input or clean.md."""
    (repo_with_terms / "clean.md").write_text("clean\n", encoding="utf-8")
    (repo_with_terms / name).write_text("Made for Zorblax.\n", encoding="utf-8")
    payload = {"tool_name": "Bash", "cwd": str(repo_with_terms), "tool_input": {"command": command}}
    reason = dev_guard.decide(payload)
    assert reason and 'term "Zorblax" in body file %s' % name in reason


@pytest.mark.parametrize("target", ["/dev/stdin", "/proc/self/environ"])
def test_a_body_file_linked_to_a_stream_or_a_process_file_blocks_with_the_hint(repo_with_terms, target):
    """The link resolves to the hook's own input, or to a file of the hook's process, not to what gh would read."""
    (repo_with_terms / "body.md").write_text("Made for Zorblax.\n", encoding="utf-8")
    os.symlink(target, str(repo_with_terms / "link.md"))
    payload = {"tool_name": "Bash", "cwd": str(repo_with_terms),
               "tool_input": {"command": "cat body.md | gh pr create --title x --body-file link.md"}}
    reason = dev_guard.decide(payload)
    assert reason and "--body-file <path>" in reason


def test_a_body_file_that_is_a_named_pipe_blocks_without_waiting(repo_with_terms):
    """Opening a pipe nobody writes to waits forever, and a hook that times out lets the tool run."""
    os.mkfifo(str(repo_with_terms / "pipe.md"))
    payload = json.dumps({"tool_name": "Bash", "cwd": str(repo_with_terms),
                          "tool_input": {"command": "gh pr create --title x --body-file pipe.md"}})
    proc = subprocess.run([sys.executable, str(SCRIPT)], input=payload, cwd=str(repo_with_terms),
                          capture_output=True, text=True, timeout=20)
    assert proc.returncode == 2
    assert "--body-file <path>" in proc.stderr


def test_absolute_pr_body_file_after_a_cd_is_checked(repo_with_terms, tmp_path):
    body = tmp_path / "body.md"
    body.write_text("Made for Zorblax.\n", encoding="utf-8")
    payload = {"tool_name": "Bash", "cwd": str(repo_with_terms),
               "tool_input": {"command": "cd sub && gh pr create --title x --body-file %s" % body}}
    reason = dev_guard.decide(payload)
    assert reason and 'term "Zorblax" in body file' in reason


# About 200 KB each, and whether the hook blocks it: the worst shapes of the rules for here-documents, standard input,
# expansions, short options and body file names. A body file that is missing blocks, like any other it cannot read.
LONG_COMMANDS = [
    ("gh pr create --title x --body y " + "<<'a'" * 40000, True),  # here-document operators
    ("gh pr create --title x" + ' -F "-"' * 30000, True),  # standard input names
    ("gh pr create --title x" + " -F a" * 40000, True),  # one body file name, 40000 times
    ("gh pr create --title x --body-file " + "a/" * 100000, True),  # one body file name of 200 KB
    ("gh pr create --title x" + "".join(" -F a%d" % number for number in range(25000)), True),  # distinct names
    ("gh pr create --title x --body y" + " =" * 100000, False),  # = alone is no zsh expansion
    ("gh pr create --title x --body y " + "a~" * 100000, False),  # ~ inside a word is no tilde expansion
    ("gh pr create --title x --body y " + "''" * 100000, False),  # empty quotes with no = or ~ after them
    ("gh pr create --title x --body y " + "-a " * 70000, False),  # short options with no F in them
    ("a/" * 100000 + "gh pr create --title x --body y", False),  # a long path in front of gh
    ("gh pr create --title x --body-file " + '""' * 100000 + "-", True),  # one body file word
    ("gh pr create --title x --body-file b.md" + " \"a\"'b'" * 25000, True),  # one name, then 50000 quoted words
    ("gh pr create --title x --body-file b.md" + " a:b=c" * 33000, True),  # one name, then words with : and =
    ("gh pr create --title x --body y " + "'a'\\''b' " * 20000, False),  # quote removal of a long command
    ("gh pr create --title x --body y; " + "xargs " * 30000, False),  # xargs with no gh after it
    ("xargs " * 30000 + "gh pr view 1", True),  # xargs, then gh at the end
]


@pytest.mark.parametrize("command,blocked", LONG_COMMANDS, ids=[
    "here-documents", "stdin-names", "one-name-repeated", "one-long-name", "distinct-names", "equals", "tilde",
    "empty-quotes", "short-options", "client-path", "glued-quotes", "quoted-words", "colon-words", "quote-removal",
    "xargs-alone", "xargs-then-gh",
])
def test_long_commands_are_read_in_linear_time(repo_with_terms, command, blocked):
    """A hook that times out lets the tool run: a check that costs a second per 200 KB is too slow."""
    started = time.perf_counter()
    reason = dev_guard.decide(bash_payload(repo_with_terms, command))
    elapsed = time.perf_counter() - started
    assert (reason is not None) == blocked, reason
    assert elapsed < 1.0


@pytest.mark.parametrize("payload", [
    {"tool_name": "mcp__github__create_pull_request", "toolInput": {"body": "for Zorblax"}},
    {"tool_name": "mcp__gitlab__update_merge_request", "tool_input": None},
    {"tool_name": "mcp__github__merge_pull_request", "tool_input": "for Zorblax"},
    {"tool_name": "mcp__github__create_pull_request", "tool_input": ["for Zorblax"]},
    {"tool_name": "mcp__gitlab__create_merge_request", "transcript_path": "x"},
])
def test_pr_tool_with_an_input_of_unknown_shape_blocks(payload):
    """No tool_input object: its text cannot be checked, and the rest of the payload says nothing about the PR."""
    reason = dev_guard.decide(payload)
    assert reason and "unknown input shape" in reason


# What the module docstring declares open. Each command passes although the text the shell or gh would send holds
# private data (the last one, although it drops the guard's own registration); the cwd file is what the hook reads
# and the sub file what the command really reads. When one of these is closed, this test fails and the docstring
# must change with it.
OPEN_FORMS = [
    # a folder change by another program than cd or pushd: the relative body file is read from the hook's folder
    ("env -C sub gh pr create --title t --body-file body.md", "clean\n", "Made for Zorblax.\n"),
    # an option name quoted or escaped is not read as the option, so standard input as its value is not seen
    ("cat body.md | gh pr create --title t '-F' -", "Made for Zorblax.\n", "clean\n"),
    ("cat body.md | gh pr create --title t \"--body-file\" -", "Made for Zorblax.\n", "clean\n"),
    ("cat body.md | gh pr create --title t --body\\-file -", "Made for Zorblax.\n", "clean\n"),
    ("cat body.md | gh pr create --title t \\-F -", "Made for Zorblax.\n", "clean\n"),
    # gh fills the body or the title from a place the hook does not read: a template or an attached file the command
    # names, the failed run it recovers, the commit messages (the pre-push checks them), an editor, the browser
    ("gh pr create --title t --template body.md", "Made for Zorblax.\n", "clean\n"),
    ("gh pr create --title t --attach body.md", "Made for Zorblax.\n", "clean\n"),
    ("gh pr create --title t --recover body.md", "Made for Zorblax.\n", "clean\n"),
    ("gh pr create --fill", "clean\n", "clean\n"),
    ("gh pr create --fill-first", "clean\n", "clean\n"),
    ("gh pr create --fill-verbose", "clean\n", "clean\n"),
    ("gh pr create --editor", "clean\n", "clean\n"),
    ("gh pr create --web", "clean\n", "clean\n"),
    ("gh pr comment 1 --editor", "clean\n", "clean\n"),
    # another program runs the gh command and supplies its text (xargs is blocked; find -exec and parallel are not)
    ("find . -name body.md -exec gh pr create --title {} --body y \\;", "Made for Zorblax.\n", "clean\n"),
    ("echo x | parallel gh pr create --title {} --body y", "clean\n", "clean\n"),
    # a step of the same command that writes the body file without spelling its name as the option does
    ("sh gen.sh && gh pr create --title t --body-file body.md", "clean\n", "clean\n"),
    ("curl -sobody.md https://x && gh pr create --title t --body-file body.md", "clean\n", "clean\n"),  # glued value
    # brace expansion builds a term from literal parts (globs do the same with a file named after the term)
    ("gh pr comment 1 --body=Zorbl{b,a}x", "clean\n", "clean\n"),
    # a gh call inside a script file is never seen, like a call held in a variable, an alias or a function
    ("bash make-pr.sh", "clean\n", "clean\n"),
    # the guard's own registration: a shell command that drops it from the settings file is not seen
    ("sed -i '/dev_guard/d' .claude/settings.local.json", "clean\n", "clean\n"),
]


@pytest.mark.parametrize("command,here,sub", OPEN_FORMS)
def test_forms_the_hook_cannot_see_stay_open_as_the_module_declares(repo_with_terms, command, here, sub):
    (repo_with_terms / "sub").mkdir()
    (repo_with_terms / "body.md").write_text(here, encoding="utf-8")
    (repo_with_terms / "sub" / "body.md").write_text(sub, encoding="utf-8")
    assert dev_guard.decide(bash_payload(repo_with_terms, command)) is None


def test_a_settings_write_that_drops_the_guard_registration_stays_open_as_the_module_declares(tmp_path):
    """The Write form of the last row of OPEN_FORMS: the tool is not Bash, so the payload differs."""
    settings = tmp_path / ".claude" / "settings.local.json"
    payload = {"tool_name": "Write", "tool_input": {"file_path": str(settings), "content": '{"permissions": {}}\n'}}
    assert dev_guard.decide(payload) is None


@pytest.mark.parametrize("tool,field", [
    ("mcp__github__create_pull_request", "body"),
    ("mcp__github__update_pull_request", "title"),
    ("mcp__gitlab__update_merge_request", "description"),
    ("mcp__github__merge_pull_request", "commit_message"),
])
def test_mcp_pull_request_text_is_checked(repo_with_terms, tool, field):
    blocked = {"tool_name": tool, "cwd": str(repo_with_terms), "tool_input": {field: "for Zorblax"}}
    clean = {"tool_name": tool, "cwd": str(repo_with_terms), "tool_input": {field: "clean text"}}
    reason = dev_guard.decide(blocked)
    assert reason and 'term "Zorblax" in the tool input' in reason
    assert dev_guard.decide(clean) is None


def test_pr_text_without_terms_configuration_blocks(tmp_path):
    repo = init_repo(tmp_path / "repo")
    payload = {"tool_name": "Bash", "cwd": str(repo), "tool_input": {"command": "gh pr create --title x"}}
    proc = run_hook(payload, repo)
    assert proc.returncode == 2
    assert "git config pe.privateTermsFile" in proc.stderr


def test_a_hanging_git_blocks_instead_of_waiting(tmp_path, monkeypatch):
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_git = fake_bin / "git"
    fake_git.write_text("#!/bin/sh\nexec sleep 5\n", encoding="utf-8")
    fake_git.chmod(0o755)
    monkeypatch.setenv("PATH", str(fake_bin) + os.pathsep + os.environ.get("PATH", ""))
    monkeypatch.setattr(dev_guard, "GIT_TIMEOUT", 0.5)
    payload = {"tool_name": "Bash", "cwd": str(tmp_path), "tool_input": {"command": "gh pr create --title x --body y"}}
    with pytest.raises(privacy_check.GitError, match="timed out"):  # a git timeout is a GitError, not a TermsError
        dev_guard.decide(payload)


def test_internal_error_on_a_known_tool_blocks(tmp_path):
    payload = {"tool_name": "Bash", "cwd": str(tmp_path / "does-not-exist"),
               "tool_input": {"command": "gh pr create --title x"}}
    proc = run_hook(payload, tmp_path)
    assert proc.returncode == 2
    assert "check failed" in proc.stderr
