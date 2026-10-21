"""Structure checks on the repository itself."""
import re
import subprocess
import unicodedata
from pathlib import Path
from typing import List, Tuple

import pytest

import privacy_check
from support import (
    A1_SKILLS,
    REPO_ROOT,
    SUPERPOWERS_SKILLS,
    SUPERPOWERS_TESTED_VERSION,
    installed_superpowers,
    sections,
    unknown_references,
)


def repository_files() -> List[Path]:
    """Tracked files plus untracked files that git does not ignore."""
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=str(REPO_ROOT), capture_output=True, check=True,
    ).stdout
    return [REPO_ROOT / name for name in out.decode("utf-8").split("\0") if name]


def repository_texts() -> List[Tuple[Path, str]]:
    """Relative path and decoded text of every repository file that is not binary."""
    texts = []
    for path in repository_files():
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" in data[:8000]:
            continue
        texts.append((path.relative_to(REPO_ROOT), data.decode("utf-8", "replace")))
    return texts


def test_repository_files_carry_no_generic_privacy_pattern():
    offenders = []
    for name, text in repository_texts():
        names = privacy_check.find_generic(text)
        if names:
            offenders.append("%s: %s" % (name, ", ".join(names)))
    assert offenders == []


def test_repository_files_carry_no_invisible_characters():
    """A byte-order mark, a zero-width or a bidirectional control character hides text.

    They are Unicode format characters (category Cf); a test that needs one
    writes it as an escape sequence instead of the raw character.
    """
    offenders = []
    for name, text in repository_texts():
        for number, line in enumerate(text.splitlines(), 1):
            for char in line:
                if unicodedata.category(char) == "Cf":
                    offenders.append("%s:%d: U+%04X" % (name, number, ord(char)))
    assert offenders == []


README = REPO_ROOT / "README.md"


def test_readme_drops_the_retired_understanding_gate():
    text = README.read_text(encoding="utf-8").lower()
    assert "understanding gate" not in text
    assert "comprehension gate" not in text


def test_readme_names_every_repository_tool():
    text = README.read_text(encoding="utf-8")
    missing = [p.name for p in sorted((REPO_ROOT / "tools").glob("*.py")) if p.name not in text]
    assert missing == []


RULES = REPO_ROOT / "rules.md"
EXPECTED_RULE_MARKERS = {
    "Every agent": {
        "precedence", "evidence", "reuse", "burden-of-proof", "test-first",
        "suite-before-commit", "self-review", "no-bug-left", "english-identifiers",
        "docs-same-commit", "candour", "secrets", "production-go", "save-ahead", "publishing",
    },
    "Main session": {"explain", "no-quiz", "lanes", "heavy-gates", "backup-diff-go"},
    "Subagents": {"status-line", "escalate", "no-publishing", "no-config-edits"},
}
# Requirements of spec section 17.3: each one must sit in the block that reaches the right agents.
MIGRATION_REQUIREMENTS = {
    "self-review": "Every agent",
    "burden-of-proof": "Every agent",
    "no-bug-left": "Every agent",
    "english-identifiers": "Every agent",
    "docs-same-commit": "Every agent",
    "heavy-gates": "Main session",
    "suite-before-commit": "Every agent",
    "production-go": "Every agent",
}
RULE_LINE = re.compile(r"^- \[PE:([a-z-]+)\] \S")


def rule_markers(block: str):
    return [RULE_LINE.match(line).group(1) for line in block.splitlines() if line.startswith("- ")]


def test_rules_start_with_the_marker_line():
    assert RULES.read_text(encoding="utf-8").splitlines()[0] == "PE-RULES v1"


def test_rules_have_the_common_core_and_two_blocks():
    assert list(sections(RULES.read_text(encoding="utf-8"))) == list(EXPECTED_RULE_MARKERS)


def test_every_rule_line_carries_one_known_marker():
    blocks = sections(RULES.read_text(encoding="utf-8"))
    for block in blocks.values():
        for line in block.splitlines():
            if line.startswith("- "):
                assert RULE_LINE.match(line), line


def test_each_rule_marker_is_in_its_block_once():
    blocks = sections(RULES.read_text(encoding="utf-8"))
    seen = []
    for title, expected in EXPECTED_RULE_MARKERS.items():
        markers = rule_markers(blocks[title])
        assert set(markers) == expected, title
        seen.extend(markers)
    assert len(seen) == len(set(seen))


@pytest.mark.parametrize("marker,block", sorted(MIGRATION_REQUIREMENTS.items()))
def test_migration_requirements_sit_in_the_right_block(marker, block):
    assert marker in rule_markers(sections(RULES.read_text(encoding="utf-8"))[block])


def test_rules_cite_only_existing_skills():
    assert unknown_references(RULES.read_text(encoding="utf-8")) == []


def test_rules_stay_short():
    assert len(RULES.read_text(encoding="utf-8")) <= 6000


def test_pinned_superpowers_names_match_the_installed_plugin():
    root = installed_superpowers()
    if root is None:
        pytest.skip("superpowers is not installed here; names pinned for %s" % SUPERPOWERS_TESTED_VERSION)
    installed = {p.name for p in (root / "skills").iterdir() if (p / "SKILL.md").is_file()}
    assert installed == set(SUPERPOWERS_SKILLS), (
        "superpowers changed: check every citation, then update SUPERPOWERS_SKILLS and the version"
    )


def test_reference_checker_catches_what_it_must():
    problems = unknown_references(
        "use `superpowers:writing-plan`, `writing-plans`, `blunt-reviews`, `speckit-foo` and `team-lead`"
    )
    assert len(problems) == 5
    assert unknown_references("use `superpowers:writing-plans`, `blunt-review` and `pre-push`") == []
