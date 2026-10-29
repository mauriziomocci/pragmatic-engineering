"""Contract of every A1 skill: frontmatter, required sections and phrases, size, references."""
from dataclasses import dataclass
from typing import Dict, Tuple

import pytest

from support import A1_SKILLS, REPO_ROOT, parse_frontmatter, sections, unknown_references, yaml_plain_safe

SKILLS_DIR = REPO_ROOT / "skills"
MAX_LINES = 500
MAX_CHARS = 18000  # after a compaction only the first 5,000 tokens of a skill are re-attached
MAX_DESCRIPTION = 1024
FORBIDDEN = ("Jira", "HackSoftware", "Two Scoops", "PostgreSQL", "Django", "select_related", "Co-Authored-By")


@dataclass(frozen=True)
class Contract:
    sections: Tuple[str, ...]
    phrases: Tuple[str, ...] = ()
    user_only: bool = False
    claude_md_sections: Tuple[str, ...] = ()
    extra_files: Tuple[str, ...] = ()
    absent: Tuple[str, ...] = ()  # source text that the rewrite must drop


CONTRACTS: Dict[str, Contract] = {
    "engineering-principles": Contract(
        sections=(
            "When to use", "Understand and reuse", "Design", "Scalability and cost", "Tests",
            "No bug left behind", "Secure coding", "Secrets hygiene", "Writing", "Further reading",
        ),
        phrases=(
            "superpowers:test-driven-development", "Searched", "easy to change", "N+1",
            "All tests pass, no known residual bugs", "it works and I do not know why",
            "property-based", "diataxis.fr", "Context7", "file::function",
            "The Pragmatic Programmer", "Fundamentals of Software Engineering", "entry page",
        ),
    ),
    "evidence-based-investigation": Contract(
        sections=(
            "When to use", "When not to use", "Investigation rules", "Confidence levels",
            "The multi-pass loop", "Scoping a defect", "Scoping techniques for fixes and data corrections",
            "Output rules", "Anti-patterns",
        ),
        phrases=(
            "superpowers:systematic-debugging",
            "Verified in the real environment",
            "Tests passing, deployed, real-environment verification pending",
            "Unit tests only",
            "working twin",
            "Symptom | Identified cause | Required fix | Covered by this fix?",
            "This fix resolves",
            "It does NOT resolve",
            "own recent changes",
            "Verified", "Inferred", "Assumed", "Unverifiable",
        ),
        absent=("iterative-requirements-analysis", "financial-reconciliation", "smonta", "combacia", "Origine"),
    ),
}


def skill_text(name: str) -> str:
    return (SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_frontmatter(name):
    fields, _ = parse_frontmatter(skill_text(name))
    expected = {"name", "description"} | ({"disable-model-invocation"} if CONTRACTS[name].user_only else set())
    assert set(fields) == expected
    assert fields["name"] == name
    assert yaml_plain_safe(fields["description"])
    assert len(fields["description"]) <= MAX_DESCRIPTION
    if CONTRACTS[name].user_only:
        assert fields["disable-model-invocation"] == "true"


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_required_sections_in_order(name):
    _, body = parse_frontmatter(skill_text(name))
    present = [title for title in sections(body) if title in CONTRACTS[name].sections]
    assert present == list(CONTRACTS[name].sections)


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_required_phrases(name):
    text = skill_text(name)
    missing = [phrase for phrase in CONTRACTS[name].phrases if phrase not in text]
    assert missing == []


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_dropped_source_text_stays_out(name):
    text = skill_text(name)
    assert [phrase for phrase in CONTRACTS[name].absent if phrase in text] == []


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_size(name):
    text = skill_text(name)
    assert len(text.splitlines()) < MAX_LINES
    assert len(text) <= MAX_CHARS


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_no_stack_or_personal_rules(name):
    text = skill_text(name).lower()
    assert [word for word in FORBIDDEN if word.lower() in text] == []


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_no_claude_md_in_the_description(name):
    fields, _ = parse_frontmatter(skill_text(name))
    assert "CLAUDE.md" not in fields["description"]


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_claude_md_only_as_a_configuration_layer(name):
    _, body = parse_frontmatter(skill_text(name))
    allowed = CONTRACTS[name].claude_md_sections
    for title, content in sections(body).items():
        if "CLAUDE.md" in content:
            assert title in allowed, title
    assert "CLAUDE.md" not in body.split("\n## ", 1)[0]


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_cited_skills_exist(name):
    assert unknown_references(skill_text(name)) == []


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_extra_files(name):
    for extra in CONTRACTS[name].extra_files:
        assert (SKILLS_DIR / name / extra).is_file(), extra


def test_contract_names_are_a1_skills():
    assert set(CONTRACTS) <= set(A1_SKILLS)
