"""End-to-end check of the rules import: main session, subagent and a missing rules file.

It starts Claude Code for real with `claude -p`, so it needs the claude CLI,
superpowers installed and the user's Claude Code login; the default run
excludes it. Run it with: python3 -m pytest -m e2e tests/e2e -v
Every assertion names what it proves, so a red says which property failed:
(a) the imported rules reached the agent, (b) the agent followed rules that
exist only in the rules file. The tools that read files or run commands are
removed from every session, and the stream is checked for any other tool
call, so the probe value can reach the agent only through the import.
The explanation check runs without the plugin, so that no skill can bring
the question it looks for. PE_E2E_RED selects one deliberate break, used
only to see each check fail: no-import, no-status-line, no-explain or
no-safety-line.
"""
import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pytest

import session_start
from support import REPO_ROOT, installed_superpowers

pytestmark = pytest.mark.e2e
TIMEOUT = 600
MAX_TURNS = "10"
PROBE = "Session probe: "
PROBE_FILE = "probe.txt"
DISALLOWED_TOOLS = "Read,Grep,Glob,Bash,Monitor"
READ_FREE_TOOLS = {"Skill", "ToolSearch", "TodoWrite"}  # none of them can read a file
PROBE_WRITERS = {"Write", "Edit"}  # only in the subagent check, and only on probe.txt
HINT_WORDS = ("rules.md", "CLAUDE.md", "Session probe")
REFUSAL = re.compile(
    r"\binjection\b|\bsuspicious\b|\bignor(?:e|ing) (?:these|the|those|any) (?:rules|instructions)\b", re.IGNORECASE
)
RED = os.environ.get("PE_E2E_RED", "")
DROPPED_RULE = {"no-status-line": "[PE:status-line]", "no-explain": "[PE:explain]"}


@pytest.fixture(autouse=True)
def user_claude_md_without_the_plugin_lines():
    """The check tells the two imports apart only while ~/.claude/CLAUDE.md lacks the plugin's lines."""
    try:
        text = (Path.home() / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
    except OSError:
        return
    found = [word for word in ("PE-RULES", session_start.SAFETY_LINE) if word in text]
    found += re.findall(r"@\S*rules\.md", text)
    if found:
        pytest.fail(
            "~/.claude/CLAUDE.md already carries lines of the plugin (%s): this check cannot tell which "
            "import brought the rules; the repetition after the pilot is designed before C" % found
        )


def claude(workdir: Path, prompt: str, with_plugin: bool = True) -> List[Dict[str, Any]]:
    """Run one non-interactive session in ``workdir`` and return its stream-json events."""
    if shutil.which("claude") is None:
        pytest.fail("the claude CLI is not on PATH")
    command = [
        "claude", "-p", prompt, "--setting-sources", "project,local", "--strict-mcp-config",
        "--no-session-persistence", "--permission-mode", "acceptEdits", "--max-turns", MAX_TURNS,
        "--disallowedTools", DISALLOWED_TOOLS, "--output-format", "stream-json", "--verbose",
    ]
    if with_plugin:
        superpowers = installed_superpowers()
        if superpowers is None:
            pytest.fail("superpowers is not installed; the plugin depends on it")
        command += ["--plugin-dir", str(REPO_ROOT), "--plugin-dir", str(superpowers)]
    proc = subprocess.run(
        command, cwd=str(workdir), capture_output=True, text=True, timeout=TIMEOUT, stdin=subprocess.DEVNULL
    )
    assert proc.returncode == 0, proc.stderr[-2000:]
    return [json.loads(line) for line in proc.stdout.splitlines() if line.strip().startswith("{")]


def final_text(events: List[Dict[str, Any]]) -> str:
    results = [event for event in events if event.get("type") == "result"]
    assert results, "no result event in the stream"
    return str(results[-1].get("result", ""))


def tool_uses(events: List[Dict[str, Any]]) -> List[Tuple[str, Dict[str, Any], Any]]:
    """(tool name, tool input, parent_tool_use_id) of every tool call in the stream."""
    calls = []
    for event in events:
        if event.get("type") != "assistant":
            continue
        for block in (event.get("message") or {}).get("content", []):
            if isinstance(block, dict) and block.get("type") == "tool_use":
                calls.append((block.get("name"), block.get("input") or {}, event.get("parent_tool_use_id")))
    return calls


def assert_nothing_read_from_disk(calls: List[Tuple[str, Dict[str, Any], Any]], with_subagent: bool = False) -> None:
    """(a) holds only if no tool call, in the session or in a subagent, could fetch the probe value.

    Only the subagent check may launch a subagent, and only there may Write or Edit touch a file: probe.txt,
    which the subagent writes and then updates, as the status line rule asks.
    """
    allowed = READ_FREE_TOOLS | ({"Agent"} | PROBE_WRITERS if with_subagent else set())
    for name, tool_input, parent in calls:
        assert name in allowed, "(a) inconclusive: %s is not allowed in this check (parent %s)" % (name, parent)
        if name in PROBE_WRITERS:
            target = str(tool_input.get("file_path", ""))
            assert target.endswith(PROBE_FILE), "(a) inconclusive: unexpected write to %s" % target
        elif name != "Agent":  # our own prompt names the probe line; nothing else should
            text = json.dumps(tool_input)
            assert not any(word in text for word in HINT_WORDS), "(a) inconclusive: %s looked for the rules" % name


def assert_not_treated_as_injection(text: str) -> None:
    match = REFUSAL.search(text)
    assert match is None, "(b) the rules were treated as an injection (%r): %r" % (match.group(0), text[:300])


def rules_copy(nonce: str) -> str:
    text = (REPO_ROOT / "rules.md").read_text(encoding="utf-8")
    dropped = DROPPED_RULE.get(RED)
    if dropped:
        text = "".join(line + "\n" for line in text.splitlines() if dropped not in line)
    return text + "\n" + PROBE + nonce + "\n"


def project_claude_md(safety_line: bool = True) -> str:
    head = "rules.md" if RED == "no-import" else "@rules.md"
    tail = session_start.SAFETY_LINE + "\n" if safety_line and RED != "no-safety-line" else ""
    return head + "\n\n" + tail


@pytest.fixture
def project(tmp_path):
    workdir = tmp_path / "project"
    workdir.mkdir()
    nonce = uuid.uuid4().hex[:12]
    (workdir / "rules.md").write_text(rules_copy(nonce), encoding="utf-8")
    (workdir / "CLAUDE.md").write_text(project_claude_md(), encoding="utf-8")
    return workdir, nonce


def test_main_session_sees_the_imported_rules(project):
    workdir, nonce = project
    prompt = "Your working rules end with a line that starts with 'Session probe:'. Reply with its value only."
    events = claude(workdir, prompt)
    assert_nothing_read_from_disk(tool_uses(events))
    text = final_text(events)
    assert nonce in text, "(a) the imported rules did not reach the main session"
    assert_not_treated_as_injection(text)


def test_subagent_sees_the_imported_rules_and_heads_its_deliverable(project):
    """Without the plugin, whose skills could carry the status-line rule, the rule can come only from the import."""
    workdir, nonce = project
    (workdir / "CLAUDE.md").write_text(project_claude_md(safety_line=False), encoding="utf-8")
    sub_prompt = (
        "Your working rules end with a line that starts with 'Session probe:'. Create the file %s in the "
        "current directory, following your working rules for deliverable files, and write that value in it."
        % PROBE_FILE
    )
    prompt = (
        "Use the Agent tool exactly once, with subagent_type general-purpose and exactly this prompt, adding "
        "nothing to it: %s Then reply done." % json.dumps(sub_prompt)
    )
    events = claude(workdir, prompt, with_plugin=False)
    calls = tool_uses(events)
    assert_nothing_read_from_disk(calls, with_subagent=True)
    agent_calls = [call for call in calls if call[0] == "Agent"]
    assert agent_calls, "no subagent was launched"
    assert all(nonce not in json.dumps(call[1]) for call in agent_calls), "the value was handed to the subagent"
    writes = [call for call in calls if call[0] in PROBE_WRITERS]
    assert writes and all(call[2] for call in writes), (
        "(a) the subagent wrote no %s: the imported rules did not reach it, or it could not write" % PROBE_FILE
    )
    content = (workdir / PROBE_FILE).read_text(encoding="utf-8")
    assert nonce in content, "(a) the imported rules did not reach the subagent"
    assert content.lstrip().startswith("STATUS:"), "(b) the subagent did not head its deliverable with a status line"
    assert_not_treated_as_injection(final_text(events))


def test_main_session_follows_the_explanation_rule_without_calling_it_an_injection(project):
    """Without the plugin, whose teach skill carries the same question, it can come only from the import."""
    workdir, _ = project
    (workdir / "CLAUDE.md").write_text(project_claude_md(safety_line=False), encoding="utf-8")
    events = claude(workdir, "In two sentences, explain what git rebase does.", with_plugin=False)
    assert_nothing_read_from_disk(tool_uses(events))
    text = final_text(events).lower()
    assert "clear?" in text or "chiaro?" in text, "(b) the explanation did not end with the question 'is it clear?'"
    assert_not_treated_as_injection(text)


def test_missing_rules_file_lets_the_safety_line_speak(tmp_path):
    workdir = tmp_path / "project"
    workdir.mkdir()
    (workdir / "CLAUDE.md").write_text(project_claude_md(), encoding="utf-8")
    events = claude(workdir, "In two sentences, explain what git rebase does.", with_plugin=False)
    assert_nothing_read_from_disk(tool_uses(events))
    text = final_text(events).lower()
    assert "pragmatic-engineering" in text, "the safety line did not make the agent name the missing plugin"
    assert any(word in text for word in ("missing", "not loaded", "not installed", "uninstalled", "disabled"))
