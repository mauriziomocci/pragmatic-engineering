"""Tests for hooks/session_start.py, the plugin's SessionStart hook."""
import json
import os
import stat
from pathlib import Path

import pytest

import session_start as ss
from support import REPO_ROOT, run_script

SCRIPT = REPO_ROOT / "hooks" / "session_start.py"
EXPECTED_SAFETY_LINE = (
    "If the pragmatic-engineering rules (marker PE-RULES v1) or its skills are missing from this "
    "session, tell the user before doing any work: the plugin is uninstalled or disabled."
)


def plugin_root(tmp_path: Path, text: str = "PE-RULES v1\nrules\n") -> Path:
    root = tmp_path / "root"
    root.mkdir()
    (root / "rules.md").write_text(text, encoding="utf-8")
    return root


def run_hook(home: Path, data: Path, source: str = "startup", env_extra=None):
    env = {"HOME": str(home), "CLAUDE_PLUGIN_ROOT": str(REPO_ROOT), "CLAUDE_PLUGIN_DATA": str(data)}
    if env_extra:
        env.update(env_extra)
    stdin = json.dumps({"hook_event_name": "SessionStart", "source": source, "cwd": str(home)})
    return run_script(SCRIPT, [], cwd=home, stdin=stdin, env=env)


def test_safety_line_is_the_agreed_text():
    assert ss.SAFETY_LINE == EXPECTED_SAFETY_LINE


def test_sync_rules_copies_when_missing(tmp_path):
    root, data = plugin_root(tmp_path), tmp_path / "data"
    assert ss.sync_rules(root, data) is True
    assert (data / "rules.md").read_text(encoding="utf-8") == "PE-RULES v1\nrules\n"


def test_sync_rules_is_quiet_when_unchanged(tmp_path):
    root, data = plugin_root(tmp_path), tmp_path / "data"
    ss.sync_rules(root, data)
    assert ss.sync_rules(root, data) is False


def test_sync_rules_updates_when_changed(tmp_path):
    root, data = plugin_root(tmp_path), tmp_path / "data"
    ss.sync_rules(root, data)
    (root / "rules.md").write_text("PE-RULES v1\nnew rules\n", encoding="utf-8")
    assert ss.sync_rules(root, data) is True
    assert "new rules" in (data / "rules.md").read_text(encoding="utf-8")


def test_import_line_uses_the_home_shortcut(tmp_path):
    home = tmp_path / "home"
    data_rules = home / ".claude" / "plugins" / "data" / "pe" / "rules.md"
    assert ss.import_line(data_rules, home) == "@~/.claude/plugins/data/pe/rules.md"


def test_import_line_outside_home_is_absolute(tmp_path):
    data_rules = tmp_path / "elsewhere" / "rules.md"
    assert ss.import_line(data_rules, tmp_path / "home") == "@" + data_rules.as_posix()


def write_claude_md(home: Path, text: str) -> Path:
    path = home / ".claude" / "CLAUDE.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_import_lines_empty_when_both_lines_are_present(tmp_path):
    home = tmp_path / "home"
    data_rules = home / ".claude" / "plugins" / "data" / "pe" / "rules.md"
    write_claude_md(home, "# Mine\n\n@~/.claude/plugins/data/pe/rules.md\n%s\n" % EXPECTED_SAFETY_LINE)
    assert ss.import_lines(data_rules, home) == []


def test_import_lines_when_claude_md_missing(tmp_path):
    home = tmp_path / "home"
    data_rules = home / ".claude" / "plugins" / "data" / "pe" / "rules.md"
    assert ss.import_lines(data_rules, home) == ["@~/.claude/plugins/data/pe/rules.md", EXPECTED_SAFETY_LINE]


def test_import_lines_when_claude_md_unreadable(tmp_path):
    home = tmp_path / "home"
    data_rules = home / ".claude" / "plugins" / "data" / "pe" / "rules.md"
    path = write_claude_md(home, "@~/.claude/plugins/data/pe/rules.md\n")
    path.chmod(0)
    try:
        if os.access(str(path), os.R_OK):
            pytest.skip("running with privileges that ignore file permissions")
        assert ss.import_lines(data_rules, home) == ["@~/.claude/plugins/data/pe/rules.md", EXPECTED_SAFETY_LINE]
    finally:
        path.chmod(stat.S_IRUSR | stat.S_IWUSR)


def test_import_lines_asks_only_for_the_missing_safety_line(tmp_path):
    home = tmp_path / "home"
    data_rules = home / ".claude" / "plugins" / "data" / "pe" / "rules.md"
    write_claude_md(home, "See @~/.claude/plugins/data/pe/rules.md for the rules.\n")
    assert ss.import_lines(data_rules, home) == [EXPECTED_SAFETY_LINE]


def test_build_output_is_none_when_there_is_nothing_to_say():
    assert ss.build_output(False, []) is None


def test_build_output_speaks_to_claude_and_to_the_user():
    out = ss.build_output(True, ["@~/x/rules.md", EXPECTED_SAFETY_LINE])
    context = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert out["systemMessage"] == context
    assert "@~/x/rules.md" in context and EXPECTED_SAFETY_LINE in context
    assert "next session" in context


@pytest.mark.parametrize("source", ["startup", "resume", "clear", "compact", "fork"])
def test_main_copies_the_rules_and_prints_the_missing_lines_for_every_source(tmp_path, source):
    home, data = tmp_path / "home", tmp_path / "home" / ".claude" / "plugins" / "data" / "pe"
    home.mkdir()
    proc = run_hook(home, data, source)
    assert proc.returncode == 0, proc.stderr
    out = json.loads(proc.stdout)
    assert "@~/.claude/plugins/data/pe/rules.md" in out["hookSpecificOutput"]["additionalContext"]
    assert (data / "rules.md").read_bytes() == (REPO_ROOT / "rules.md").read_bytes()


def test_main_is_silent_when_everything_is_in_place(tmp_path):
    home, data = tmp_path / "home", tmp_path / "home" / ".claude" / "plugins" / "data" / "pe"
    home.mkdir()
    run_hook(home, data)
    write_claude_md(home, "@~/.claude/plugins/data/pe/rules.md\n%s\n" % EXPECTED_SAFETY_LINE)
    proc = run_hook(home, data)
    assert proc.returncode == 0
    assert proc.stdout.strip() == ""


def test_main_with_unusual_paths(tmp_path):
    home = tmp_path / "home with space's àccent"
    data = home / ".claude" / "plugins" / "data" / "pe"
    home.mkdir()
    proc = run_hook(home, data)
    assert proc.returncode == 0, proc.stderr
    assert (data / "rules.md").is_file()
    assert "@~/.claude/plugins/data/pe/rules.md" in proc.stdout


def test_main_without_the_data_variable_explains_and_does_not_fail(tmp_path, monkeypatch):
    monkeypatch.delenv("CLAUDE_PLUGIN_DATA", raising=False)  # the suite may run inside a plugin session
    home = tmp_path / "home"
    home.mkdir()
    env = {"HOME": str(home), "CLAUDE_PLUGIN_ROOT": str(REPO_ROOT)}
    proc = run_script(SCRIPT, [], cwd=home, stdin="{}", env=env)
    assert proc.returncode == 0
    assert "data folder" in proc.stdout


def test_main_with_invalid_input_does_not_fail(tmp_path):
    home, data = tmp_path / "home", tmp_path / "data"
    home.mkdir()
    env = {"HOME": str(home), "CLAUDE_PLUGIN_ROOT": str(REPO_ROOT), "CLAUDE_PLUGIN_DATA": str(data)}
    assert run_script(SCRIPT, [], cwd=home, stdin="not json", env=env).returncode == 0


def test_main_with_the_rules_file_missing_from_the_plugin_explains_and_does_not_fail(tmp_path):
    home, data, root = tmp_path / "home", tmp_path / "data", tmp_path / "plugin-without-rules"
    home.mkdir()
    root.mkdir()
    env = {"HOME": str(home), "CLAUDE_PLUGIN_ROOT": str(root), "CLAUDE_PLUGIN_DATA": str(data)}
    proc = run_script(SCRIPT, [], cwd=home, stdin="{}", env=env)
    assert proc.returncode == 0
    assert "the rules check failed" in proc.stdout
