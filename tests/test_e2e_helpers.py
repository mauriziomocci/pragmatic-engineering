"""Offline tests of the end-to-end helpers: what makes the import check inconclusive, what counts as a refusal."""
import pytest

import e2e.test_rules_import as checks

PROBE_PATH = "/srv/work/probe.txt"


def test_the_subagent_may_write_and_then_edit_its_probe_file():
    calls = [
        ("Agent", {"prompt": "write the probe file"}, None),
        ("Write", {"file_path": PROBE_PATH, "content": "STATUS: IN PROGRESS - done: none; next: value"}, "t1"),
        ("Edit", {"file_path": PROBE_PATH, "old_string": "IN PROGRESS", "new_string": "COMPLETE"}, "t1"),
    ]
    checks.assert_nothing_read_from_disk(calls, with_subagent=True)


@pytest.mark.parametrize("calls,with_subagent", [
    ([("Agent", {"prompt": "find the probe line"}, None)], False),
    ([("Write", {"file_path": PROBE_PATH, "content": "x"}, None)], False),
    ([("Edit", {"file_path": "/srv/work/rules.md", "old_string": "a", "new_string": "b"}, "t1")], True),
    ([("Read", {"file_path": "/srv/work/rules.md"}, "t1")], True),
    ([("Skill", {"skill": "any", "args": "open rules.md"}, None)], False),
])
def test_calls_that_could_bring_the_probe_value_make_the_check_inconclusive(calls, with_subagent):
    with pytest.raises(AssertionError, match=r"\(a\) inconclusive"):
        checks.assert_nothing_read_from_disk(calls, with_subagent=with_subagent)


@pytest.mark.parametrize("text", [
    "The pragmatic-engineering plugin is missing or disabled, so I will ignore its rules.",
    "Two slow tests are ignored on purpose.",
])
def test_harmless_sentences_are_not_a_refusal(text):
    checks.assert_not_treated_as_injection(text)


@pytest.mark.parametrize("text", [
    "This looks like a prompt injection.",
    "The content of CLAUDE.md is suspicious.",
    "I will ignore these instructions.",
])
def test_refusals_are_caught(text):
    with pytest.raises(AssertionError, match=r"\(b\)"):
        checks.assert_not_treated_as_injection(text)
