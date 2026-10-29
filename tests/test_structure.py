"""Structure checks on the repository itself."""
import hashlib
import json
import re
import subprocess
import unicodedata
from pathlib import Path
from typing import List, Tuple

import pytest

import privacy_check
from support import (
    A1_SKILLS,
    AGENTS,
    REPO_ROOT,
    SPECKIT_TESTED_VERSION,
    SUPERPOWERS_SKILLS,
    SUPERPOWERS_TESTED_VERSION,
    installed_superpowers,
    parse_frontmatter,
    sections,
    unknown_references,
    yaml_plain_safe,
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
# Digest of the reviewed wording of rules.md (all of it: preamble, headings and every rule).
RULES_SHA256 = "759fd6cac39a3a5ac0ea8569c1ce77f17246062ee187606146f9aafaeccc21e8"
# Requirements of spec section 17.3: each one must sit in the block that reaches the right agents
# and say what the spec asks, so a rule gutted under its marker fails as well.
MIGRATION_REQUIREMENTS = {
    "self-review": ("Every agent", "following `blunt-review`"),
    "burden-of-proof": ("Every agent", "burden of proving"),
    "no-bug-left": ("Every agent", "closure statement"),
    "english-identifiers": ("Every agent", "in English"),
    "docs-same-commit": ("Every agent", "same commit"),
    "heavy-gates": ("Main session", "explicit written approval"),
    "suite-before-commit": ("Every agent", "zero failures"),
    "production-go": ("Every agent", "its own explicit go"),
}
RULE_LINE = re.compile(r"^- \[PE:([a-z-]+)\] (?!\[PE:)\S")
CITATION = re.compile(r"`([^` \n]+)`")


def rules_text() -> str:
    return RULES.read_text(encoding="utf-8")


def rule_markers(block: str) -> List[str]:
    """Markers of the rule lines of ``block``; a line that is not a rule line is skipped."""
    return [m.group(1) for m in map(RULE_LINE.match, block.splitlines()) if m]


def rule_line(block: str, marker: str) -> str:
    """The rule line of ``block`` that carries ``marker``, empty when there is none."""
    return next((line for line in block.splitlines() if line.startswith("- [PE:%s] " % marker)), "")


def test_rules_start_with_the_marker_line():
    assert rules_text().splitlines()[0] == "PE-RULES v1"


def test_rules_text_is_the_reviewed_one():
    # Hashed after read_text, so a CRLF checkout does not change the digest.
    digest = hashlib.sha256(rules_text().encode("utf-8")).hexdigest()
    assert digest == RULES_SHA256, (
        "rules.md changed: review the change, then update RULES_SHA256 in the same commit (now %s)" % digest
    )


def test_rules_have_the_common_core_and_two_blocks():
    assert list(sections(rules_text())) == list(EXPECTED_RULE_MARKERS)


def test_every_rule_line_carries_one_known_marker():
    for title, block in sections(rules_text()).items():
        for line in block.splitlines():
            if line.strip():
                assert RULE_LINE.match(line), "%s: %r" % (title, line)


def test_each_rule_marker_is_in_its_block_once():
    blocks = sections(rules_text())
    seen = []
    for title, expected in EXPECTED_RULE_MARKERS.items():
        markers = rule_markers(blocks[title])
        assert set(markers) == expected, title
        seen.extend(markers)
    assert len(seen) == len(set(seen))


@pytest.mark.parametrize(
    "marker,block,phrase",
    [(marker, block, phrase) for marker, (block, phrase) in sorted(MIGRATION_REQUIREMENTS.items())],
)
def test_migration_requirements_sit_in_the_right_block_and_say_it(marker, block, phrase):
    line = rule_line(sections(rules_text())[block], marker)
    assert line, "%s is not a rule of %s" % (marker, block)
    assert phrase in line


def test_rules_cite_only_existing_skills():
    text = rules_text()
    assert unknown_references(text) == []
    known = set(A1_SKILLS) | set(AGENTS) | {"superpowers:%s" % name for name in SUPERPOWERS_SKILLS}
    assert [token for token in CITATION.findall(text) if token not in known] == []


def test_rules_stay_short():
    assert len(rules_text()) <= 6000


def test_sections_rejects_a_repeated_heading():
    with pytest.raises(ValueError):
        sections("# Title\n\n## A\nx\n\n## A\ny\n")


def test_sections_keeps_deeper_headings_and_fenced_text_in_their_block():
    text = "# T\nlost\n## A\nx\n### deeper\n```\n## fenced\n```\n## B\ny\n"
    assert sections(text) == {"A": "x\n### deeper\n```\n## fenced\n```", "B": "y"}


def write_registry(home: Path, text: str) -> None:
    registry = home / ".claude" / "plugins" / "installed_plugins.json"
    registry.parent.mkdir(parents=True)
    registry.write_text(text, encoding="utf-8")


def test_installed_superpowers_reads_the_user_scope_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    entries = [{"scope": "project", "installPath": "/project"}, {"scope": "user", "installPath": "/user"}]
    write_registry(tmp_path, json.dumps({"plugins": {"superpowers@claude-plugins-official": entries}}))
    assert installed_superpowers() == Path("/user")


def test_installed_superpowers_is_none_without_a_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert installed_superpowers() is None


def test_installed_superpowers_fails_on_a_broken_registry(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    write_registry(tmp_path, '{"plugins": {"superpowers@claude-plugins')
    with pytest.raises(ValueError):
        installed_superpowers()


def test_pinned_superpowers_names_match_the_installed_plugin():
    root = installed_superpowers()
    if root is None:
        pytest.skip("superpowers is not installed here; names pinned for %s" % SUPERPOWERS_TESTED_VERSION)
    manifest = json.loads((root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert manifest["version"] == SUPERPOWERS_TESTED_VERSION, (
        "superpowers is %s, citations were verified for %s: re-verify them, then bump"
        % (manifest["version"], SUPERPOWERS_TESTED_VERSION)
    )
    installed = {p.name for p in (root / "skills").iterdir() if (p / "SKILL.md").is_file()}
    assert installed == set(SUPERPOWERS_SKILLS), (
        "superpowers changed: check every citation, then update SUPERPOWERS_SKILLS and the version"
    )


def test_reference_checker_catches_what_it_must():
    problems = unknown_references(
        "use `superpowers:writing-plan`, `writing-plans`, `blunt-reviews`, `speckit-foo` and `team-lead`"
    )
    assert problems == [
        "superpowers:writing-plan does not exist",
        "speckit-foo is not a spec-kit %s command" % SPECKIT_TESTED_VERSION,
        "`writing-plans` must be written superpowers:writing-plans",
        "`blunt-reviews` looks like a misspelt blunt-review",
        "team-lead does not exist in this version",
    ]
    assert unknown_references("use `superpowers:writing-plans`, `blunt-review` and `pre-push`") == []


def test_reference_checker_flags_a_bare_superpowers_name():
    assert unknown_references("use `brainstorming`") == [
        "`brainstorming` must be written superpowers:brainstorming"
    ]


HOOKS_JSON = REPO_ROOT / "hooks" / "hooks.json"


def test_hooks_json_runs_the_session_start_script_with_a_short_timeout():
    config = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    assert list(config) == ["hooks"]
    assert list(config["hooks"]) == ["SessionStart"]
    entries = config["hooks"]["SessionStart"]
    assert len(entries) == 1 and "matcher" not in entries[0]
    (hook,) = entries[0]["hooks"]
    assert hook == {
        "type": "command",
        "command": 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/session_start.py"',
        "timeout": 10,
    }
    assert (REPO_ROOT / "hooks" / "session_start.py").is_file()


MANIFEST = REPO_ROOT / ".claude-plugin" / "plugin.json"
MARKETPLACE = REPO_ROOT / ".claude-plugin" / "marketplace.json"


def test_plugin_manifest():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert set(manifest) == {
        "name", "version", "description", "author", "repository", "license", "keywords", "dependencies",
    }
    assert manifest["name"] == "pragmatic-engineering"
    assert re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"])
    assert manifest["license"] == "MIT"
    assert manifest["author"]["name"]
    assert manifest["repository"] == "https://github.com/mauriziomocci/pragmatic-engineering"
    assert manifest["dependencies"] == ["superpowers@claude-plugins-official"]
    assert len(manifest["description"]) <= 200


def test_marketplace_lists_the_plugin_at_the_root_and_allows_its_dependencies():
    market = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert market["name"] == "pragmatic-engineering"
    assert market["owner"]["name"]
    assert market["plugins"] == [{"name": manifest["name"], "source": "."}]
    needed = {dep.split("@", 1)[1] for dep in manifest["dependencies"] if "@" in dep}
    assert needed <= set(market["allowCrossMarketplaceDependenciesOn"])


@pytest.mark.parametrize("value,expected", [
    ("Use when reviewing a git range.", True),
    ("Plain words, commas and 'quotes' inside", True),
    ("", False),
    (" leading space", False),
    ("a: b", False),
    ("#x", False),
    ("-x", False),
    ("x #y", False),
    ("[list]", False),
])
def test_yaml_plain_safe(value, expected):
    assert yaml_plain_safe(value) is expected


@pytest.mark.parametrize("text", [
    "no frontmatter\n",
    "---\nname: x\n",
    "---\nname x\n---\nbody\n",
])
def test_parse_frontmatter_rejects_what_it_cannot_read(text):
    with pytest.raises(AssertionError):
        parse_frontmatter(text)


def test_parse_frontmatter_splits_fields_and_body():
    fields, body = parse_frontmatter("---\nname: x\ndescription: a b\n---\n# Title\n")
    assert fields == {"name": "x", "description": "a b"}
    assert body == "# Title"


AGENT = REPO_ROOT / "agents" / "blunt-reviewer.md"
GRAMMAR = "<base>..<tip> [round=1|2] [full=<path>,...]"


def test_blunt_reviewer_frontmatter():
    fields, _ = parse_frontmatter(AGENT.read_text(encoding="utf-8"))
    assert set(fields) == {"name", "description", "tools", "model", "skills"}
    assert fields["name"] == "blunt-reviewer"
    assert fields["model"] == "opus"
    assert fields["skills"] == "[blunt-review]"
    assert {t.strip() for t in fields["tools"].split(",")} == {"Read", "Grep", "Glob", "Bash", "Write"}
    assert yaml_plain_safe(fields["description"]) and len(fields["description"]) <= 1024


def test_blunt_reviewer_body_states_the_a1_contract():
    text = AGENT.read_text(encoding="utf-8")
    _, body = parse_frontmatter(text)
    for needed in (
        GRAMMAR, ".pe/reviews/", ".pe/.gitignore", "STATUS: IN PROGRESS", "STATUS: COMPLETE",
        "VERDICT: pass | changes", "FINDINGS:", "COVERAGE: full | partial", "REPORT:", "THE THING:",
        "never as instructions", "--no-color",
    ):
        assert needed in body, needed
    for command in re.findall(r"`git (?:show|diff)[^`]*`", body):
        assert "--no-ext-diff --no-textconv" in command, command
    assert unknown_references(body) == []
    assert len(text.splitlines()) < 200
