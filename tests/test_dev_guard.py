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


def run_hook(payload, cwd: Path):
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    return run_script(SCRIPT, [], cwd=cwd, stdin=stdin)


@pytest.fixture
def repo_with_terms(tmp_path):
    repo = init_repo(tmp_path / "repo")
    terms = tmp_path / "terms.txt"
    terms.write_text("Zorblax\n", encoding="utf-8")
    git(repo, "config", "pe.privateTermsFile", str(terms))
    return repo


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


@pytest.mark.parametrize("command,word", [
    ("gh pr create --title x --body \"$(cat <<'EOF'\nUses `sections()` now.\nEOF\n)\"", None),
    ("gh pr create --title x --body \"$(cat <<'EOF'\nRun it from $HOME, see `notes`.\nEOF\n)\"", None),
    ("gh pr create --title x --body \"$(cat <<'EOF'\nMade for Zorblax.\nEOF\n)\"", 'term "Zorblax"'),
    ("gh pr create --title x --body-file - <<'EOF'\nClean text.\nEOF", None),
])
def test_pr_body_in_a_here_document_is_checked_in_place(repo_with_terms, command, word):
    payload = {"tool_name": "Bash", "cwd": str(repo_with_terms), "tool_input": {"command": command}}
    reason = dev_guard.decide(payload)
    if word is None:
        assert reason is None
    else:
        assert reason and word in reason


def test_missing_pr_body_file_blocks(repo_with_terms):
    payload = {"tool_name": "Bash", "cwd": str(repo_with_terms),
               "tool_input": {"command": "gh pr create --title x -F missing.md"}}
    proc = run_hook(payload, repo_with_terms)
    assert proc.returncode == 2
    assert "check failed" in proc.stderr


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
    # cat reads the file named after the operator, not the here-document
    "gh pr create --title x --body \"$(cat <<'EOF' body.md\nClean text.\nEOF\n)\"",
    "gh pr create --title x --body \"$(cat <<EOF body.md\nClean text.\nEOF\n)\"",
    # the only here-document belongs to another command, so standard input is not fed by the command
    "cat body.md | gh pr create --title x --body-file - ; git commit -F - <<'EOF'\nA message.\nEOF",
    "gh pr create --title x --body-file - && git commit -F - <<'EOF'\nA message.\nEOF",
    "git commit -F - <<'EOF'\nA message.\nEOF\ncat body.md | gh pr create --title x --body-file -",
    # a relative body file is read from the folder the hook starts in, which a cd in the command changes
    "cd sub && gh pr create --title x --body-file body.md",
    "pushd sub; gh pr create --title x --body-file body.md",
    "(cd sub && gh pr edit 3 -F body.md)",
    # a pipe whose first command also reads a file (bash prints the file), something between cat and gh, a second
    # input that wins over the here-document, an operator written inside a quoted title, an unquoted tag
    "cat <<'EOF' body.md | gh pr create --title x --body-file -\nClean text.\nEOF",
    "cat body.md <<'EOF' | gh pr create --title x --body-file -\nClean text.\nEOF",
    "cat <<'EOF' | sed 'r body.md' | gh pr create --title x --body-file -\nClean text.\nEOF",
    "cat <<'EOF' | gh pr create --title x --body-file - < body.md\nClean text.\nEOF",
    "gh pr create --title x --body-file - <<'EOF' < body.md\nClean text.\nEOF",
    "gh pr create --title x --body-file - < body.md <<'EOF'\nClean text.\nEOF",
    "cat body.md | gh pr create --title \"<<EOF\" --body-file -",
    "cat <<EOF | gh pr create --title x --body-file -\nClean text.\nEOF",
    # a command after the terminator inside the substitution: bash puts what it prints into the body
    "gh pr create --title x --body \"$(cat <<'EOF'\nIntro.\nEOF\ncat body.md\n)\"",
    "gh pr create --title x --body \"$(cat <<'EOF'\nIntro.\nEOF\ntrue; cat body.md\n)\"",
    "gh pr create --title x --body \"$(cat <<'EOF'\nIntro.\nEOF\n  cat body.md ; echo\n)\"",
    "gh pr create --title x --body \"$(cat <<EOF\nClean text.\nEOF\n)\"",
    # standard input outside the two shapes: a here-document inside a substitution, a pipe or a < into gh, a second
    # input next to the here-document (zsh joins the pipe and the here-document), redirections glued to each other
    "cat body.md | gh pr create --body-file - --title $(cat <<'EOF'\nTitle\nEOF\n)",
    "gh pr create --body-file - --title $(cat <<'EOF'\nT\nEOF\n) < body.md",
    "cat body.md | gh pr create --title x --body-file - <<'EOF'\nClean body.\nEOF",
    "gh pr create --title x --body-file - <'/dev/null'<body.md",
    "gh pr create --title x --body-file - <<'EOF'<body.md\nClean body.\nEOF",
    # a separator, an operator or an escaped quote inside a quoted string, which only a parser of quotes could place
    "cat body.md | gh pr create --title \"x; cat <<'E'\" --body-file -",
    "cat body.md | gh pr create --title \"x; y\" --body-file - --label \"<<EOF\"",
    "cat body.md | gh pr create --body-file - --title \"a \\\" <<b\"",
    # an escaped quote that keeps a double-quoted string open past the operator, whose substitution then runs
    "gh pr create --body-file - --title \"a \\\" <<'EOF'\n$(cat body.md)\"\nEOF",
    # a command after the terminator, then a line that looks like a second one
    "gh pr create --title x --body-file - <<'EOF'\nClean.\nEOF\ncat body.md | gh pr edit 1 --body-file -\nEOF",
    # a first command that is not gh or glab (GNU xargs -a adds the words of the file to gh's arguments)
    "xargs -a body.md gh pr create --title x --body-file - <<'EOF'\nClean.\nEOF",
    # a standard input name spelt with quotes the shell removes, or ended by a separator
    "cat body.md | gh pr create --title x --body-file \"\"-",
    "cat body.md | gh pr create --title x --body-file -; true",
    # a line that is the tag with a tab, a trailing blank or a carriage return ends no plain here-document in bash or
    # zsh, so the substitution goes on and zsh runs cat body.md into the body
    "gh pr create --title x --body \"$(cat <<'EOF'\nIntro.\n\tEOF\n)\nEOF\ncat body.md\n)\"",
    "gh pr create --title x --body \"$(cat <<'EOF'\nIntro.\nEOF \n)\nEOF\ncat body.md\n)\"",
    "gh pr create --title x --body \"$(cat <<'EOF'\nIntro.\nEOF\r\n)\nEOF\ncat body.md\n)\"",
    # an operator line that a backslash continues: the body starts after the continued lines, which run as a command
    "cat <<'EOF' | gh pr create \\\n  --head \"$(cat title.txt)\" \\\n  --title x --body-file -\nClean text.\nEOF",
    "cat <<'EOF' \\\nbody.md | gh pr create --title x --body-file -\nClean text.\nEOF",
    "cat <<'EOF' | gh pr create --title x \\\n  --body-file - < body.md\nClean text.\nEOF",
    # the same without standard input, where only the cutting of here-document bodies stands in the way; likewise a
    # quoted string still open at the end of the operator line, and an operator a backslash escapes
    "gh pr create --title x --body y <<'EOF' \\\n  --head \"$(cat title.txt)\"\nClean.\nEOF",
    "gh pr create --body x <<'EOF' --title \"a\n$(cat body.md)\"\nfoo\nEOF",
    "gh pr create --title x --body y \\<<'EOF'\ngh pr edit 1 --body \"$(cat body.md)\"\nEOF",
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
    "gh pr create --title =gh --body-file - <<'EOF'\nClean.\nEOF",
    # clean, but outside the two shapes for standard input: accepted over-blocks (a redirection, a continuation, a
    # newline inside quotes, a second command that reads its own standard input, a body that only names the option:
    # the names are read from the whole text, so that one in a line the cutting of bodies wrongly hid still counts)
    "gh pr create --title x --body-file - 2>&1 <<'EOF'\nClean body.\nEOF",
    "gh pr create --title x --body-file - \\\n  <<'EOF'\nClean body.\nEOF",
    "gh pr create --title 'two\nlines' --body-file - <<'EOF'\nClean body.\nEOF",
    "git commit -F - <<'EOF'\nA message.\nEOF\ngh pr create --title x --body \"$(cat <<'EOF'\nClean body.\nEOF\n)\"",
    "gh pr create --title x --body \"$(cat <<'EOF'\nPass --body-file - to read standard input.\nEOF\n)\"",
])
def test_pr_body_in_a_form_the_hook_cannot_locate_blocks_with_the_hint(repo_with_terms, command):
    (repo_with_terms / "body.md").write_text("Made for Zorblax.\n", encoding="utf-8")
    payload = {"tool_name": "Bash", "cwd": str(repo_with_terms), "tool_input": {"command": command}}
    reason = dev_guard.decide(payload)
    assert reason and "--body-file <path>" in reason and "absolute path" in reason


@pytest.mark.parametrize("command", [
    # shape (A): gh and its words, ending in the here-document
    "gh pr create --title \"Clean title\" --body-file - <<'EOF'\nClean body.\nEOF",
    "gh pr create --title x --body-file - <<'EOF'\nNo -Fbody.md, no cd, no $(cat x) here.\nEOF",
    "/opt/homebrew/bin/gh pr create --title v1.2:fix,50%+@me --body-file=/dev/fd/0 <<\"EOF\"\nClean body.\nEOF\n\n  \n",
    "gh pr create --title x --body-file - <<-'EOF'\n\tClean body.\n\tEOF",
    # a tab before the tag ends no plain here-document: the line is body, as in bash and zsh
    "gh pr create --title x --body-file - <<'EOF'\nIndented:\n\tEOF\nEOF",
    # shape (B): cat with the here-document, piped into gh and its words
    "cat <<'EOF' | gh pr create --title x --body-file -\nClean body.\nEOF",
    "cat <<-'EOF' | gh pr create --title x --body-file -\n\tClean body.\n\tEOF",
    "cat <<\"EOF\" | gh pr create --title x -F /dev/stdin\nClean body.\nEOF",
    # the substitution, whose here-document body is the text
    "gh pr create --title x --body \"$(cat <<'EOF'\nClean body.\nEOF\n)\"",
    "gh pr create --title x --body \"$(cat <<'EOF'\nClean body.\nEOF\n   )\"",
    # a < or a << or a | inside quotes is text
    "cat <<'EOF' | gh pr create --title \"a | b\" --body-file -\nClean body.\nEOF",
    "gh pr create --title \"Handle <T> generics\" --body-file - <<'EOF'\nClean body.\nEOF",
])
def test_pr_body_in_a_here_document_of_its_own_command_passes(repo_with_terms, command):
    payload = {"tool_name": "Bash", "cwd": str(repo_with_terms), "tool_input": {"command": command}}
    assert dev_guard.decide(payload) is None


@pytest.mark.parametrize("command", [
    # a here-string is no here-document: a line that looks like its terminator ends nothing, and the line before it
    # runs as written
    "cat <<< 'x'\ngh pr create --title t --body \"$(cat body.md)\"\nx",
    "cat <<<'x'\ngh pr create --title t --body \"$(cat body.md)\"\nx",
    # an operator written inside a quoted string, without a terminator, is no here-document either: reading the rest
    # of the text as its body would hide the substitution below it, which does run
    "gh pr create --title t --body \"Uses <<'EOF' in scripts\nand $(cat body.md)\"",
    "gh pr create --title t --body-file - <<'EOF'\nNo end here.\n$(cat body.md)",
])
def test_an_operator_that_is_no_here_document_does_not_hide_what_follows(repo_with_terms, command):
    payload = {"tool_name": "Bash", "cwd": str(repo_with_terms), "tool_input": {"command": command}}
    reason = dev_guard.decide(payload)
    assert reason and "--body-file <path>" in reason


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


# About 200 KB each, and whether the hook blocks it. The first three are runs of quoted here-documents that only the
# cutting of their bodies reads (--body y: no standard input rule stops the check earlier); the rest are the worst
# shapes of the rules for standard input, of the end of the operator line, of the expansions and of body file names.
LONG_COMMANDS = [
    ("gh pr create --title x --body y <<'A'\n" + "<<'A'\nx\n" * 25000, False),  # nothing ends the first one
    ("gh pr create --title x --body y <<'A'\nx\nA\n" + "<<'A'\nx\nA\n" * 25000, False),  # every one ends
    ("gh pr create --title x --body y " + "<<'a'" * 40000, False),  # one line, no newline after any operator
    ("gh pr create --title x --body-file - <<'A'\n" + "<<'A'\nx\n" * 25000, True),  # no terminator
    ("gh pr create --title x --body-file - " + "<<'a'" * 40000, True),  # more than one operator
    ("gh pr create --body-file - " + "a " * 100000 + ";", True),  # words, then a separator
    ("cat <<'A' | gh pr create --body-file - " + "'a'\"b\" " * 25000 + ";\nx\nA", True),  # quoted words
    ("cat <<'A' | gh pr create --title x" + ' -F "-"' * 30000 + "\nx\nA", False),  # standard input names
    ("gh pr create --body-file - <<'A'\n" + "x\n" * 100000, True),  # body lines, no terminator
    ("gh pr create --body-file - <<-'ABCD'\n" + "\t\tABC\n" * 33000 + "\tABCD", False),  # lines almost the terminator
    ("gh pr create --body-file - <<'A'\nx\nA\n" + " \n" * 100000 + "x", True),  # blanks after the terminator, then text
    ("gh pr create --title x --body \"$(cat <<'A'" + ' "a' * 60000 + "\nx\nA\n)\"", True),  # long operator line
    ("gh pr create --title x --body y <<'A' " + '"a' * 100001 + "\nx\nA", False),  # quote open at its end
    ("gh pr create --title x --body y " + "\\<<'a'" * 30000, False),  # escaped operators
    ("gh pr create --title x --body y" + " =" * 100000, False),  # = alone is no zsh expansion
    ("gh pr create --title x --body y " + "a~" * 100000, False),  # ~ inside a word is no tilde expansion
    ("a/" * 100000 + "gh pr create --body-file - <<'A'\nx\nA", False),  # a long path in front of gh
    ("gh pr create --title x --body-file " + '""' * 100000 + "- <<'A'\nx\nA", False),  # one body file word
    ("cat <<'A' | gh pr create --body-file - " + "a " * 100000 + "|\nx\nA", True),  # words, then a second pipe
]


@pytest.mark.parametrize("command,blocked", LONG_COMMANDS, ids=[
    "unterminated", "terminated", "one-line", "stdin-unterminated", "stdin-one-line", "words", "quoted-words",
    "stdin-names", "body-lines", "near-terminators", "blanks-after-terminator", "operator-line", "open-quote",
    "escaped-operators", "equals", "tilde", "client-path", "glued-quotes", "pipe-words",
])
def test_long_commands_are_read_in_linear_time(repo_with_terms, command, blocked):
    """A hook that times out lets the tool run: scanning the rest of the text for every operator took 20 s here."""
    payload = {"tool_name": "Bash", "cwd": str(repo_with_terms), "tool_input": {"command": command}}
    started = time.perf_counter()
    reason = dev_guard.decide(payload)
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


# What the module docstring declares open. Each command passes although the text the shell would send holds private
# data; the cwd file is what the hook reads and the sub file what the command really reads (or the reverse for the
# forms of the first limit, where the command substitution runs in the folder the hook starts in). When one of these
# is closed, this test fails and the docstring must change with it.
OPEN_FORMS = [
    # an operator the shell does not read as one (inside a quoted string, after a comment sign, inside the body of an
    # unquoted here-document) and a bare terminator line after it: taken for a real quoted here-document, so the
    # substitution that does run between them is not seen
    ("gh pr create --title t --body \"Use <<'EOF' in scripts\n$(cat body.md)\nEOF\n\"", "Made for Zorblax.\n", "clean\n"),
    ("gh pr create --title t --body-file sub/body.md # <<'EOF'\ngh pr edit 1 --body \"$(cat body.md)\"\nEOF",
     "Made for Zorblax.\n", "clean\n"),
    ("cat <<EOF\n<<'X'\nEOF\ngh pr edit 1 --body \"$(cat body.md)\"\nX", "Made for Zorblax.\n", "clean\n"),
    # a folder change by another program than cd or pushd: the relative body file is read from the hook's folder
    ("env -C sub gh pr create --title t --body-file body.md", "clean\n", "Made for Zorblax.\n"),
]


@pytest.mark.parametrize("command,here,sub", OPEN_FORMS)
def test_forms_the_hook_cannot_see_stay_open_as_the_module_declares(repo_with_terms, command, here, sub):
    (repo_with_terms / "sub").mkdir()
    (repo_with_terms / "body.md").write_text(here, encoding="utf-8")
    (repo_with_terms / "sub" / "body.md").write_text(sub, encoding="utf-8")
    payload = {"tool_name": "Bash", "cwd": str(repo_with_terms), "tool_input": {"command": command}}
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
