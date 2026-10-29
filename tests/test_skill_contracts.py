"""Contract of every A1 skill: frontmatter, required sections and phrases, size, references."""
import re
from dataclasses import dataclass
from typing import Dict, Tuple

import pytest

from support import (
    A1_SKILLS,
    REPO_ROOT,
    SUPERPOWERS_SKILLS,
    parse_frontmatter,
    sections,
    unknown_references,
    yaml_plain_safe,
)

SKILLS_DIR = REPO_ROOT / "skills"
MAX_LINES = 500
MAX_CHARS = 18000  # after a compaction only the first 5,000 tokens of a skill are re-attached
MAX_DESCRIPTION = 1024
FORBIDDEN = ("Jira", "HackSoftware", "Two Scoops", "PostgreSQL", "Django", "select_related", "Co-Authored-By")
# The three files that tell a sub-agent how to open its deliverable file; rules.md is pinned by digest.
STATUS_LINE_FILES = ("rules.md", "agents/blunt-reviewer.md", "skills/continuity-note/SKILL.md")
STATUS_LINE = re.compile(r"`(STATUS: IN PROGRESS - done:[^`]*)`")


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
            "When to use", "Understand and reuse", "Design", "Delivered API contracts", "Scalability and cost", "Tests",
            "No bug left behind", "Secure coding", "Secrets hygiene", "Writing", "Further reading",
        ),
        phrases=(
            "superpowers:test-driven-development", "Searched", "easy to change", "N+1",
            "All tests pass, no known residual bugs", "it works and I do not know why",
            "property-based", "diataxis.fr", "Context7", "file::function",
            "The Pragmatic Programmer", "Fundamentals of Software Engineering", "entry page",
            "When the placement is not trivial", "One direction, with no cycles", "One owner for each concept",
            "Invariants in the data", "more than three modules", "import-contract check",
            "A delivered contract never changes shape", "on a separate line at the top of the message",
            "scenario table", "in a single pass", '"contract unchanged"', '"CONTRACT CHANGE"',
            "the tests of the touched area", "before the push", "proven with the real command it runs",
            "stops only what it started, by name", "a manual for them",
        ),
        absent=("the suite that the project's configuration declares", "Dependencies point one way"),
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
            "**Verified**:", "**Inferred**:", "**Assumed**:", "**Unverifiable**:",  # the four bullets of Pass 5
            "apply all four techniques",
            "the name of the report that would give the exact one",
        ),
        absent=(
            "iterative-requirements-analysis", "financial-reconciliation", "smonta", "combacia", "Origine",
            "rules cycle",  # the section is called "Rule cycle"
        ),
    ),
    "blunt-review": Contract(
        sections=(
            "When to use", "Senior reviewer mode", "Output shape", "Forbidden", "Taste lens", "Systemic before local",
            "Burden of proof on adding", "The eight-point review", "Lenses by kind of work",
            "Blocking findings", "Independent review with blunt-reviewer", "The review cycle after fixes",
            "Receiving findings",
        ),
        phrases=(
            "THE THING:", "THE DECISION:", "no findings", "file:line", "a role, not a person",
            "delete existing code > do nothing > extend something that already exists > write something new",
            "what breaks if it is deleted", "in doubt it is blocking", "blunt-reviewer", "round=2", "full=",
            "Round 1", "Round 2", "superpowers:receiving-code-review", "adversarial-review-panel",
            "mcp-code-review",
            "<tip before the fixes>..<tip after the fixes>", "the range of the latest fixes",  # what each round gets
            "REPORT: none", "Docstrings are complete",
        ),
        absent=(
            "Delivering work", "Pythonic",
            "whole range",  # round 1 is the range of the fixes, not of the work
            "a dependency that duplicates",  # not in the rule it summarises
        ),
    ),
    "adversarial-review-panel": Contract(
        sections=(
            "What this is for", "When to run it (and when not to)", "The four lenses",
            "Cross-examination (one pass, after the lenses)", "Resolving conflicts: precedence, not a judge",
            "Output shape (mandatory)", "After the decision: the review cycle", "Common failure modes",
        ),
        phrases=(
            "THE DECISION:", "Missed by all:", "no objection", "blunt-review",
            "delete > do nothing > extend what exists > write new", "what breaks if we delete this?",
        ),
    ),
    "development-workflow": Contract(
        sections=(
            "The three lanes", "Feature lane: phases and gates", "One chain per feature",
            "Superpowers skills by phase", "Three-step design", "Tasks, models and escalation",
            "Instruction layers", "Rule cycle", "Shared files", "Phase 6 and the merge request",
            "Closure", "Continuity",
        ),
        phrases=tuple("superpowers:" + name for name in sorted(SUPERPOWERS_SKILLS)) + (
            "speckit-specify", "speckit-clarify", "speckit-plan", "speckit-tasks", "speckit-implement",
            "spec-kit 0.8.9", "docs/superpowers/specs/", "specs/NNN-slug/", "is it clear?",
            "Opus", "Sonnet", "Haiku", "tracer bullet", "spike", "work log", "merge-base",
            "blunt-reviewer", "semver", "safe-operations",
            "evidence-based-investigation", "spec-driven-layout", "continuity-note", "teach",
            "autonomous-execution", "blunt-review", "adversarial-review-panel",
            "The tests of the touched area before every commit",  # one test scope per commit, as the task routine
            "which comes only in phase 7",
        ),
        claude_md_sections=("Feature lane: phases and gates", "Instruction layers", "Rule cycle", "Shared files"),
        absent=("phase-model-skill-mapping", "--no-ff", "Jira", "The project's suite before every commit"),
    ),
    "spec-driven-layout": Contract(
        sections=(
            "When to use", "Where spec-kit keeps its files", "Commands by phase", "Phases and artifacts",
            "How much to materialise", "Constitution precedence", "Templates",
        ),
        phrases=(
            "specs/NNN-slug/", ".specify/memory/constitution.md", ".specify/templates/", "spec-kit 0.8.9",
            "speckit-specify", "speckit-clarify", "speckit-plan", "speckit-tasks", "speckit-implement",
            "development-workflow",
            "YYYYMMDD-HHMMSS",  # the numbering of a project created with --timestamp
            ".specify/templates/overrides/",  # first in spec-kit's template lookup order
        ),
        absent=(
            ".specify/specs", "global CLAUDE.md", "memory backup",
            "runs without any spec-kit convention",  # a leftover of spec-kit as opt-in
            "Otherwise the artifacts follow",  # specify init always fills .specify/templates/
        ),
    ),
    "autonomous-execution": Contract(
        sections=(
            "Authorisation", "Preconditions", "Per-task loop", "Unrelated bugs and repository hygiene",
            "Decisions taken alone", "Closure: the internal phase 6", "Red flags",
        ),
        phrases=(
            "never to merge", "blunt-reviewer", "blunt-review", "merge-base", "adversarial-review-panel",
            "superpowers:subagent-driven-development", "superpowers:test-driven-development",
            "Decisions taken alone", "Observations on the spec", "MERGEABLE", "NOT MERGEABLE",
            "engineering-principles", "partial closure", "how to check the CI", "safe-operations",
            "conflicts with the target",
            "is not a protected branch",  # an unattended run never commits its tasks onto main
            "never a reason to try another route", "stops the run at once",  # a refusal is not a detour
            "auto-merge",  # scheduling a merge is merging
            "git 2.38", "git rev-parse -q --verify MERGE_HEAD",
        ),
        user_only=True,
        absent=("git-commit-assistant", "/opt/homebrew", "Autorizzazione", "carve-out", "such as 2.32"),
    ),
    "teach": Contract(
        sections=(
            "When to use", "Brief explanations", "Teaching code in six layers", "Resuming a session",
            "What teach never does",
        ),
        phrases=(
            "is it clear?", "The problem", "The path through the code", "Choices and discarded alternatives",
            "A concrete case", "Limits", "How to check it yourself", "continuity-note", "file::function",
            "no quiz",
            "accepted that cost",  # the weak check is a trade-off the user chose, declared, not a gap
        ),
        absent=("whenever it is relevant",),  # an instruction with no trigger
    ),
    "continuity-note": Contract(
        sections=(
            "When this is the right tool", "What goes in (and what stays out)", "Document structure",
            "Rules that make a handoff trustworthy", "Where to save it", "The progress note",
            "Status line of deliverable files",
        ),
        phrases=(
            "Redact secrets", "reference, don't duplicate", ".pe/progress.md", "STATUS: IN PROGRESS",
            "STATUS: COMPLETE", "## Next steps",
        ),
        extra_files=("LICENSE",),
    ),
    "safe-operations": Contract(
        sections=(
            "When to use", "Before", "Production and shared systems", "Long operations", "After",
            "Effects on third parties", "What stays with the user",
        ),
        phrases=(
            "active target", "dry run", "blast radius", "way back", "explicit go", "every level",
            "not a responding service", "whoever owns", "development-workflow",
        ),
    ),
    "quality-scoring": Contract(
        sections=(
            "When to use", "The lenses", "The perimeter", "Findings", "Classes", "Mechanical thresholds",
            "The score", "Who scores", "The score sheet", "Calibration",
        ),
        phrases=(
            "S1, critical", "S2, serious", "S3, medium", "file:line", "One finding is one root cause",
            "8 means no S1, no S2 and at most four S3", "Five S3 give 7.5", "never from whoever did the work",
            "re-checks the other's S1 and S2", "CALIBRATING (k/5)", "STABLE", "five consecutive applications",
            "on at least two projects", "two points or more", "the rubric never changes without the user",
            "C901, PLR0912, PLR0915 and PLR1702", "blunt-reviewer", "blunt-review", "development-workflow",
            "engineering-principles",
            # the one scale that blunt-review's blocking findings use
            "a scenario that fails", "an invariant contradicted by the code", "a security or privacy problem",
            "an operation with no way back", "a missing or tautological test on a behaviour that changed",
            "a document contradicted by the code",
            "interface-quality",
        ),
    ),
    "interface-quality": Contract(
        sections=(
            "When to use", "Simplicity first", "Measured before proposing", "The UX study",
            "APIs are an interface", "The UX lens and the review lens", "The user lens",
        ),
        phrases=(
            "One page, one job, one primary action", "never alphabetically", "both themes",
            "375, 768 and 1280 px", "4.5:1", "3:1", "44 px", "2.5.5", "2.5.8", "prefers-reduced-motion", "axe",
            "approved before its code", "never replaces it", "a delivered contract never changes shape",
            "one round", "an agreement without an independent check is a finding", "never Haiku",
            "at most three personas", "four questions", "from templates, not seen on screen",
            "blunt-review", "quality-scoring", "engineering-principles",
        ),
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
    # The body only: the description promises, and a promise in the description must not shield a missing rule.
    _, text = parse_frontmatter(skill_text(name))
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
    # Strict: a skill cites its siblings by bare name, so a backticked name that is no component
    # (a typo too far from any real name for the distance check) is a broken reference.
    assert unknown_references(skill_text(name), strict=True) == []


@pytest.mark.parametrize("name", sorted(CONTRACTS))
def test_extra_files(name):
    for extra in CONTRACTS[name].extra_files:
        assert (SKILLS_DIR / name / extra).is_file(), extra


def test_status_line_has_one_spelling():
    spelled = {
        name: set(STATUS_LINE.findall((REPO_ROOT / name).read_text(encoding="utf-8")))
        for name in STATUS_LINE_FILES
    }
    assert all(spelled.values()), spelled
    assert len(set.union(*spelled.values())) == 1, spelled


def test_quality_scoring_names_the_calibration_log_in_the_form_claude_code_substitutes():
    """Claude Code replaces ${CLAUDE_PLUGIN_DATA} in a skill's body; the bare $CLAUDE_PLUGIN_DATA is not replaced,
    and the variable is not set in the shell the model runs."""
    _, body = parse_frontmatter(skill_text("quality-scoring"))
    assert "`${CLAUDE_PLUGIN_DATA}/calibration.md`" in body
    assert "$CLAUDE_PLUGIN_DATA" not in body.replace("${CLAUDE_PLUGIN_DATA}", "")


def test_every_a1_skill_has_a_contract():
    assert set(CONTRACTS) == set(A1_SKILLS)


def test_no_skill_directory_outside_the_list():
    present = {p.name for p in SKILLS_DIR.iterdir() if p.is_dir()}
    assert present == set(A1_SKILLS)
