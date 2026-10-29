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
            "property-based", "Context7", "file::function",
            "The Pragmatic Programmer", "Fundamentals of Software Engineering", "documentation-quality",
            "When the placement is not trivial", "One direction, with no cycles", "One owner for each concept",
            "Invariants in the data", "more than three modules", "import-contract check",
            "A delivered contract never changes shape", "on a separate line at the top of the message",
            "scenario table", "in a single pass", '"contract unchanged"', '"CONTRACT CHANGE"',
            "the tests of the touched area", "before the push", "proven with the real command it runs",
            "stops only what it started, by name",
            "an autonomy profile that opens `contract`",
            "until the API's first release or first client, the lenses may change its shape, with its documentation and "
            "the test's delivered schema updated in the same commit, and the spec quotes the decision log entry",
            # independent work that needs its own context: one phrase, so the order is pinned too,
            # and no claim that every host has the tools
            "in this order: a new session through the desktop app's `start_session` tool, when the session has it; "
            "otherwise a `spawn_task` chip the user opens with one click; otherwise a subagent in its own git worktree",
            "not of the plugin, which cannot add them",
            "other than a lens or a review, which stays the subagent its skill names",
        ),
        absent=(
            "the suite that the project's configuration declares", "Dependencies point one way",
            "Documentation is divided by type", "keeps a manual for them",  # one home: documentation-quality
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
            "**Verified**:", "**Inferred**:", "**Assumed**:", "**Unverifiable**:",  # the four bullets of Pass 5
            "apply all four techniques",
            "the name of the report that would give the exact one",
            "never evidence itself",
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
            "what breaks if it is deleted", "in doubt the more severe class holds", "blunt-reviewer", "round=2", "full=",
            "Round 1", "Round 2", "superpowers:receiving-code-review", "adversarial-review-panel",
            "mcp-code-review",
            "<tip before the fixes>..<tip after the fixes>", "the range of the latest fixes",  # what each round gets
            "REPORT: none", "Docstrings are complete",
            "C901, PLR0912, PLR0915 and PLR1702", "before a branch is integrated", "# taste-exempt: <reason>",
            "Ruff has no rule for the 40 lines", "S1 or S2 in `quality-scoring`", "Every finding carries its lens and its class",
            "five S3 give 7.5 with the verdict `pass`", "reads the score, not only the verdict",
            "is itself the finding (see `documentation-quality`)",  # the four kinds live in that skill
        ),
        absent=(
            "Delivering work", "Pythonic",
            "whole range",  # round 1 is the range of the fixes, not of the work
            "a dependency that duplicates",  # not in the rule it summarises
            "in doubt it is blocking",  # one scale: the classes of quality-scoring decide
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
            "Role lenses", "Budget", "Instruction layers", "Rule cycle", "Shared files", "Phase 6 and the merge request",
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
            "PM lens", "UX lens", "user lens", "review lens", "pre-mortem of three lines", "measured cost",
            "an agreement without an independent check is a finding", "possible theatre", "Never traded",
            "scope is cut, never quality", "30 minutes", "five costs", "never decided in the user's absence",
            "Decision log", "found by a lens or later by people", "quality-scoring", "interface-quality",
            '"contract unchanged"', '"fix or defer?"', "transactions, security, permissions and migrations",
            "under 10-15 lines",
            # the autonomy: who opens it, where it is read, what it opens and what never moves
            "Gate 2 has one: an autonomy that opens `spec`.", "for a named piece of work or day with a hard stop",
            "git config --local --get pe.autonomy", "a profile only the user sets, never an agent even when asked",
            "never from the global value or a versioned file",
            "hands the lenses `spec` (gate 2, after the three-step design and a review cycle closed on `pass`), "
            "`schema` (data model) and `design` (outside the window) unless the user's words or the profile narrow them, "
            "and, by profile only, `contract`",
            "deletions outside the worktree, merges into protected branches", "nothing else moves", "the user's answer in chat prevails",
        ),
        claude_md_sections=("Feature lane: phases and gates", "Instruction layers", "Rule cycle", "Shared files"),
        absent=(
            "phase-model-skill-mapping", "--no-ff", "Jira", "The project's suite before every commit",
            "Gate 2 has none",  # an autonomy that opens spec is its one exception
            "`publish`",  # publishing is not an opening of the plugin, a declared difference from the master
        ),
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
            "Outside the office hours of `safe-operations` the invocation does not push",
            "the decision log entry of an autonomy that opens `spec`", "the gate of phase 2 has no other exception",
        ),
        user_only=True,
        absent=(
            "git-commit-assistant", "/opt/homebrew", "Autorizzazione", "carve-out", "such as 2.32",
            "the gate of phase 2 has no exception",
        ),
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
            "git -C <folder>",
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
            "When to use", "Before", "Production and shared systems", "Outside office hours", "Long operations",
            "After", "Effects on third parties", "What stays with the user",
        ),
        phrases=(
            "active target", "dry run", "blast radius", "way back", "explicit go", "every level",
            "not a responding service", "whoever owns", "development-workflow",
            "dedicated resource", "only when the change is additive", "as a side effect",
            "git config --get pe.officeHours", "pe.weekendFrom", "pe.holidays", "easter+N", "pe.personalRemotes",
            "read with `date`, never estimated", "only as local commits", "hard stop", "real dates, never faked ones",
            "keep the machine awake", "Deletions outside the work's own folder",
            "`06-21` runs from 06:00 up to 20:59",  # the end hour is outside the window
            # one command re-creates every commit with both dates of the moment; a cherry-pick of the range keeps one
            '`git rebase --exec "git commit --amend --no-edit --reset-author" <base>`',
            "An autonomy that opens `design`",
            "the authorisation with its hard stop is still needed: a chat autonomy that covers the night is one, a profile never is",
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
            "engineering-principles", "interface-quality",
            # the formula of the gate, step by step: a changed penalty or cap moves every score
            "each S1 takes 4 points away and caps the lens at 4",
            "each S2 takes 1.5 points away and caps the lens at 7",
            "each S3 takes 0.5 points away", "rounded down to the half point",
            # the one scale that blunt-review's blocking findings use
            "a scenario that fails", "an invariant contradicted by the code", "a security or privacy problem",
            "an operation with no way back", "a missing or tautological test on a behaviour that changed",
            "a document contradicted by the code",
            # an accepted change must outlive a plugin update, and the log must show it
            "with its date and the reason", "never in the files of the plugin",
            "from the last place it is installed",
            "nor the autonomy exception",  # a contract changed under the profile is no S1
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
            "the AAA criterion 2.5.5",  # 44 px is a default here, not a level of WCAG AA
            "otherwise the user approves it",  # a project with no designer still has an approver
            # the round of the master: the answer step, the third attack axis and the exemption
            "answers or changes the proposal", "impact on code and architecture", "except a trivial text fix",
            "recognition over recall", "never their components inside the project's template",
            "choices among existing values", "assume the persona does not understand", "is a tracked task",
            "or to the PM lens under an autonomy that opens `spec`",
        ),
    ),
    "documentation-quality": Contract(
        sections=(
            "When to use", "Four kinds of documentation", "Only what exists", "The manual for daily users",
            "Where the other rules live",
        ),
        # Each phrase is the wording of one rule and occurs once in the body, so deleting or turning
        # the rule turns the suite red; a common word ("reference") would be satisfied by any sentence.
        # The four checks of "Only what exists" are pinned by ONLY_WHAT_EXISTS, in both skills.
        phrases=(
            "https://diataxis.fr is recommended reading, and nothing here is copied from it",
            "Load it before writing, splitting, reorganising or reviewing documentation",
            "and four situations cover them all",
            "a **tutorial** takes a newcomer", "a **how-to guide** gives someone who already knows the product",
            "a **reference** describes the machinery", "an **explanation** says why",
            "Does the page guide what the reader does, or what the reader knows?",
            "Is the reader learning, or working?",
            "Doing and learning is a tutorial; doing and working, a how-to guide; "
            "knowing and working, a reference; knowing and learning, an explanation.",
            "mixes two kinds and is split: one kind per page", "One exception is declared, the entry page",
            "left out or labelled as planned, with no instructions to follow", "is named as such",
            "A project with an administration interface, used every day by the people who run the product",
            "not for the system administrators", "stay out of it",
            "lists the chapters of the manual it affects", "the work is not done until those chapters",
            "generated by a script", "never taken by hand", "with one command",
            "The text lives once, in Markdown", "no format is kept up to date by hand",
            "has its shape: `engineering-principles`",
            "`blunt-review` repeats these checks for the reviewer agent, which cannot load this skill",
            "and its thresholds: `quality-scoring`",
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


# What makes a finding blocking: the S1 and S2 examples of quality-scoring, which blunt-review must repeat.
ONE_SCALE = {
    "S1": (
        "a scenario that fails", "an invariant contradicted by the code", "a security or privacy problem",
        "an operation with no way back",
    ),
    "S2": ("a missing or tautological test on a behaviour that changed", "a document contradicted by the code"),
}


CLASS_OF_A_CLAUSE = re.compile(r"\b(?:is|are) (S[123])\b")


def classes_blunt_review_gives(blocking: str) -> Dict[str, str]:
    """The clauses of the scale sentence of blunt-review, each with the class its 'are S1' or 'is S3' states."""
    scale = blocking.split("there is one scale:", 1)[1].split(". ", 1)[0]
    return {clause: found.group(1) for clause in scale.split(";") if (found := CLASS_OF_A_CLAUSE.search(clause))}


def test_blocking_findings_use_the_one_scale_of_quality_scoring():
    """A phrase has the same class in both skills, and a class given to it as 'not blocking' is no scale at all."""
    blocking = sections(parse_frontmatter(skill_text("blunt-review"))[1])["Blocking findings"]
    classes = sections(parse_frontmatter(skill_text("quality-scoring"))[1])["Classes"]
    rows = {row.split("|")[1].strip()[:2]: row for row in classes.splitlines() if row.startswith("| S")}
    given = classes_blunt_review_gives(blocking)
    for grade, phrases in ONE_SCALE.items():
        for phrase in phrases:
            assert [g for g, row in rows.items() if phrase in row] == [grade], ("quality-scoring", grade, phrase)
            in_review = [(clause, g) for clause, g in given.items() if phrase in clause]
            assert len(in_review) == 1, ("blunt-review", phrase)
            clause, review_grade = in_review[0]
            assert review_grade == grade and "not blocking" not in clause, ("blunt-review", grade, phrase)


# The four checks on what a document may claim. blunt-review repeats them for the reviewer agent, which cannot
# load documentation-quality, and the test keeps the two copies equal, as ONE_SCALE does for the classes.
ONLY_WHAT_EXISTS = (
    "A document describes the system as it is today: a claim is checked against the code, "
    "never against the previous version of the document.",
    "A command, a flag or a path that does not exist is not described as present.",
    "A document that describes a control says what the control does not cover, "
    "because stating only what works is marketing.",
    "Counts, lists and examples are checked against the code.",
)
# Where each skill keeps them: a "##" section of the skill, a "###" lens of the review.
WHERE_THE_CHECKS_LIVE = {"documentation-quality": ("Only what exists", 2), "blunt-review": ("Documentation", 3)}


@pytest.mark.parametrize("name", sorted(WHERE_THE_CHECKS_LIVE))
@pytest.mark.parametrize("sentence", ONLY_WHAT_EXISTS)
def test_the_checks_on_what_a_document_may_claim_have_one_text(name, sentence):
    heading, level = WHERE_THE_CHECKS_LIVE[name]
    body = parse_frontmatter(skill_text(name))[1]
    assert sections(body, level)[heading].count(sentence) == 1


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


def test_documentation_quality_stays_within_its_cap():
    """6,000 characters, a third of the cap of a skill: it points to the rules other skills hold, never repeats them."""
    assert len(skill_text("documentation-quality")) <= 6000


def test_every_a1_skill_has_a_contract():
    assert set(CONTRACTS) == set(A1_SKILLS)


def test_no_skill_directory_outside_the_list():
    present = {p.name for p in SKILLS_DIR.iterdir() if p.is_dir()}
    assert present == set(A1_SKILLS)
