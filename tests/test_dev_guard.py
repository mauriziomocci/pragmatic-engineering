"""Tests for tools/dev_guard.py, the project PreToolUse hook of step zero."""
import json
import os
import shutil
import subprocess
import sys
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
    with pytest.raises(privacy_check.GitError):  # privacy_check turns a git timeout into a GitError
        dev_guard.decide(payload)


def test_internal_error_on_a_known_tool_blocks(tmp_path):
    payload = {"tool_name": "Bash", "cwd": str(tmp_path / "does-not-exist"),
               "tool_input": {"command": "gh pr create --title x"}}
    proc = run_hook(payload, tmp_path)
    assert proc.returncode == 2
    assert "check failed" in proc.stderr
