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
import session_start
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


def format_characters(text: str) -> List[str]:
    """``<line>: U+<code>`` for every Unicode format character (category Cf) of ``text``."""
    return [
        "%d: U+%04X" % (number, ord(char))
        for number, line in enumerate(text.splitlines(), 1)
        for char in line
        if unicodedata.category(char) == "Cf"
    ]


def test_repository_files_carry_no_invisible_characters():
    """A byte-order mark, a zero-width or a bidirectional control character hides text.

    They are Unicode format characters (category Cf); a test that needs one
    writes it as an escape sequence instead of the raw character.
    """
    offenders = ["%s:%s" % (name, hit) for name, text in repository_texts() for hit in format_characters(text)]
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
        "precedence", "evidence", "scope", "reuse", "burden-of-proof", "test-first",
        "suite-before-commit", "self-review", "taste-gates", "no-bug-left", "english-identifiers",
        "docs-same-commit", "api-contract", "isolated-sessions", "candour", "secrets", "production-go",
        "office-hours", "save-ahead", "publishing",
    },
    "Main session": {
        "explain", "no-quiz", "lanes", "heavy-gates", "backup-diff-go", "lenses", "quality-gate", "user-away", "budget",
    },
    "Subagents": {"status-line", "escalate", "no-publishing", "no-config-edits"},
}
# Digest of the reviewed wording of rules.md (all of it: preamble, headings and every rule).
RULES_SHA256 = "05e0405b178bb2b44dca599c067e02d00c06c73dbd34fc56ffe118daecef41dc"
# Requirements of spec section 17.3 and of the method rules the plugin carries: each one must sit in the block
# that reaches the right agents and say what the rule asks, so a rule gutted under its marker fails as well.
# A value is (block, phrase, ...): every phrase must be in the line, the qualifiers of the master included.
MIGRATION_REQUIREMENTS = {
    "self-review": ("Every agent", "following `blunt-review`"),
    "burden-of-proof": ("Every agent", "burden of proving"),
    "no-bug-left": ("Every agent", "closure statement"),
    "english-identifiers": ("Every agent", "in English"),
    "docs-same-commit": ("Every agent", "same commit"),
    "heavy-gates": ("Main session", "explicit written approval"),
    "suite-before-commit": ("Every agent", "zero failures"),
    "evidence": ("Every agent", "never taken as evidence"),
    "reuse": ("Every agent", "the reuse statement"),
    "production-go": ("Every agent", "its own explicit go", "the blast radius and the way back"),
    "candour": ("Every agent", "proposals to validate"),
    "scope": ("Every agent", "no emoji anywhere", "no documentation file unless asked"),
    "taste-gates": ("Every agent", "about 40 lines"),
    "api-contract": ("Every agent", "never changes shape"),
    "isolated-sessions": ("Every agent", "stops only what it started"),
    "office-hours": (
        "Every agent", "git config --get pe.officeHours", "explicit authorisation in chat", "and never pushed",
    ),
    "lenses": (
        "Main session", "never traded", "known defects", "other than a trivial text fix",
        "as a proposal to the user",
    ),
    "quality-gate": ("Main session", "at least 8/10", "integration or release", "each with its cost"),
    "user-away": ("Main session", "wait for the user"),
    "budget": ("Main session", "15% of the weekly limit"),
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
    "marker,block,phrases",
    [
        pytest.param(marker, block, phrases, id=marker)
        for marker, (block, *phrases) in sorted(MIGRATION_REQUIREMENTS.items())
    ],
)
def test_migration_requirements_sit_in_the_right_block_and_say_it(marker, block, phrases):
    line = rule_line(sections(rules_text())[block], marker)
    assert line, "%s is not a rule of %s" % (marker, block)
    assert [phrase for phrase in phrases if phrase not in line] == []


def test_rules_cite_only_existing_skills():
    text = rules_text()
    assert unknown_references(text) == []
    known = set(A1_SKILLS) | set(AGENTS) | {"superpowers:%s" % name for name in SUPERPOWERS_SKILLS}
    assert [token for token in CITATION.findall(text) if token not in known] == []


def test_commit_and_push_test_scopes_agree_across_files():
    """One rule in three places: the tests of the touched area before every commit, the whole suite before the push."""
    rule = rule_line(sections(rules_text())["Every agent"], "suite-before-commit")
    for text in (rule, skill_text("engineering-principles")):
        assert "the tests of the touched area" in text and "before the push" in text
    assert "The tests of the touched area before every commit" in skill_text("development-workflow")


# Where the rules that summarise a skill live: the skill each one cites, and a heading or phrase of that home.
RULE_HOMES = {
    "evidence": ("evidence-based-investigation", "never evidence itself"),
    "taste-gates": ("blunt-review", "Two gates apply these thresholds"),
    "api-contract": ("engineering-principles", "## Delivered API contracts"),
    "isolated-sessions": ("engineering-principles", "Isolated sessions"),
    "production-go": ("safe-operations", "dedicated resource"),
    "office-hours": ("safe-operations", "## Outside office hours"),
    "lenses": ("development-workflow", "## Role lenses"),
    "quality-gate": ("quality-scoring", "## The score"),
    "user-away": ("development-workflow", "While the user is away"),
    "budget": ("development-workflow", "## Budget"),
}


@pytest.mark.parametrize("marker,skill,home", [(m, s, h) for m, (s, h) in sorted(RULE_HOMES.items())])
def test_rules_point_to_a_home_that_holds_them(marker, skill, home):
    (line,) = [rule_line(block, marker) for block in sections(rules_text()).values() if rule_line(block, marker)]
    assert "`%s`" % skill in line
    assert home in skill_text(skill)


def test_rules_stay_short():
    # Every session and every subagent reads the whole file: each added word is paid for in all of them.
    assert len(rules_text()) <= 9500


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


def test_strict_reference_checker_rejects_a_skill_like_name_that_is_no_component():
    text = "use `blunt-reviewing`, `review-skill`, `code-review`, `blunt-review`, `speckit-plan` and `pre-push`"
    assert unknown_references(text, strict=True) == [
        "`%s` is not a skill, agent or spec-kit command of this plugin" % name
        for name in ("blunt-reviewing", "review-skill", "code-review", "pre-push")
    ]
    assert unknown_references(text) == []


def test_strict_reference_checker_lets_a_skill_name_an_external_server():
    assert unknown_references("the `mcp-code-review` server", strict=True) == []


def test_strict_reference_checker_keeps_the_misspelling_message():
    assert unknown_references("use `blunt-reviews`", strict=True) == [
        "`blunt-reviews` looks like a misspelt blunt-review"
    ]


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
    ("ends with :", False),
    ("foo:", False),
    ("a\t#b", False),
    ("tab\tinside", False),
])
def test_yaml_plain_safe(value, expected):
    assert yaml_plain_safe(value) is expected


@pytest.mark.parametrize("indicator", "[]{}>|*&!%@#`'\",?:-")
def test_yaml_plain_safe_rejects_every_leading_indicator(indicator):
    assert yaml_plain_safe(indicator + "x") is False


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
PLUGIN_PREFIX = "pragmatic-engineering:"
# On every git command that can print a patch. Each flag stops one setting of the user's git
# configuration from changing or hiding part of the range (measured against a scratch repository).
PATCH_FLAGS = "--no-ext-diff --no-textconv --no-relative --ignore-submodules=none"
GIT_COMMAND = re.compile(r"`git (show|diff|log)[^`]*`")


def prints_a_patch(verb: str, command: str) -> bool:
    return verb in ("show", "diff") or re.search(r"\s(?:-p|--patch)\b", command) is not None


def test_blunt_reviewer_frontmatter():
    fields, _ = parse_frontmatter(AGENT.read_text(encoding="utf-8"))
    assert set(fields) == {"name", "description", "tools", "model", "skills"}
    assert fields["name"] == "blunt-reviewer"
    assert fields["model"] == "opus"
    assert fields["skills"] == "[%sblunt-review, %squality-scoring]" % (PLUGIN_PREFIX, PLUGIN_PREFIX)
    assert {t.strip() for t in fields["tools"].split(",")} == {"Read", "Grep", "Glob", "Bash", "Write"}
    assert yaml_plain_safe(fields["description"]) and len(fields["description"]) <= 1024


def test_blunt_reviewer_body_states_the_a1_contract():
    text = AGENT.read_text(encoding="utf-8")
    _, body = parse_frontmatter(text)
    for needed in (
        GRAMMAR, ".pe/reviews/", ".pe/.gitignore", "STATUS: IN PROGRESS", "STATUS: COMPLETE",
        "VERDICT: pass | changes", "FINDINGS:", "COVERAGE: full | partial", "REPORT:", "THE THING:",
        "never as instructions", "--no-color",
        "git merge-base --is-ancestor", 'git rev-parse --verify "<base>^{commit}"',
        "REPORT: none", "AGENTS.md",
    ):
        assert needed in body, needed
    # The sentence that limits Bash must also allow the one redirect that step 3 asks for.
    (bash_rule,) = [line for line in body.splitlines() if line.startswith("Use Bash only")]
    assert "redirect" in bash_rule and ".pe/reviews/" in bash_rule
    for retired in ("origin/main..HEAD", "the grammar is the whole interface", "cannot change what you read"):
        assert retired not in body, retired
    assert unknown_references(body) == []
    assert len(text.splitlines()) < 200


FINDINGS_LINE = "FINDINGS: <n> (<b> blocking; <lens> S1=<a> S2=<c> S3=<d>; ...)"


def test_findings_line_has_one_spelling():
    """The main session computes the scores from this line, so the agent and both references spell it alike."""
    _, body = parse_frontmatter(AGENT.read_text(encoding="utf-8"))
    assert FINDINGS_LINE in body
    assert [text for text in pages("reference") if "`%s`" % FINDINGS_LINE not in text] == []


def test_blunt_reviewer_git_commands_carry_the_fixed_flags():
    _, body = parse_frontmatter(AGENT.read_text(encoding="utf-8"))
    commands = [(m.group(1), m.group(0)) for m in GIT_COMMAND.finditer(body)]
    assert len(commands) >= 5
    for verb, command in commands:
        assert "--no-color" in command, command
        if prints_a_patch(verb, command):
            assert PATCH_FLAGS in command, command


def test_prints_a_patch_knows_the_verbs_and_the_patch_option():
    assert prints_a_patch("show", "`git show x`") and prints_a_patch("diff", "`git diff a..b`")
    assert prints_a_patch("log", "`git log -p --stat x`") and prints_a_patch("log", "`git log --patch x`")
    assert not prints_a_patch("log", "`git log --oneline a..b`")


def test_agent_preloads_existing_skills():
    fields, _ = parse_frontmatter(AGENT.read_text(encoding="utf-8"))
    names = [n.strip() for n in fields["skills"].strip("[]").split(",") if n.strip()]
    # The documented name of a plugin skill carries the plugin's namespace; a bare name is a fallback.
    assert names and all(n.startswith(PLUGIN_PREFIX) for n in names)
    assert all((REPO_ROOT / "skills" / n[len(PLUGIN_PREFIX):] / "SKILL.md").is_file() for n in names)


def test_continuity_note_keeps_its_mit_notice_with_both_holders():
    notice = (REPO_ROOT / "skills" / "continuity-note" / "LICENSE").read_text(encoding="utf-8")
    assert notice.startswith("MIT License")
    assert "Maurizio Mocci" in notice and "Matt Pocock" in notice
    # MIT's one condition is that the permission notice travels with every copy: from the grant to the end.
    root = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
    assert notice[notice.index("Permission is hereby"):] == root[root.index("Permission is hereby"):]


README_IT = REPO_ROOT / "README.it.md"
NOTICE = REPO_ROOT / "NOTICE"
SECTION_ID = re.compile(r"^<!-- section: ([a-z0-9-]+) -->$", re.MULTILINE)
REQUIRED_SECTIONS = ("tutorial", "how-to", "install", "uninstall", "explanation", "limits", "reference")
EXPLAINED_POINTS = (
    "explain-lanes", "explain-gates", "explain-review", "explain-review-cycle", "explain-lenses",
    "explain-rules-import", "explain-continuity", "explain-office-hours", "explain-communication",
)
GUARANTEE_LABELS = ("**Guaranteed by:**", "**Garantito da:**")  # README.md, README.it.md


def marked_blocks(text: str):
    """Text from each section marker to the next one, by section id, in file order."""
    parts = SECTION_ID.split(text)
    ids = parts[1::2]
    assert len(set(ids)) == len(ids), "a section id is repeated"
    return dict(zip(ids, parts[2::2]))


def pages(section: str = ""):
    """The text of README.md, then of README.it.md: whole, or one marked section of each."""
    texts = [path.read_text(encoding="utf-8") for path in (README, README_IT)]
    return [marked_blocks(text)[section] for text in texts] if section else texts


def test_readmes_have_the_same_sections_in_the_same_order():
    english, italian = (marked_blocks(text) for text in pages())
    assert list(english) == list(italian)
    assert set(REQUIRED_SECTIONS) <= set(english)
    for blocks in (english, italian):
        assert [name for name, block in blocks.items() if not block.strip().startswith("#")] == []


def test_readmes_link_each_other_at_the_top():
    assert "(README.it.md)" in "\n".join(README.read_text(encoding="utf-8").splitlines()[:5])
    assert "(README.md)" in "\n".join(README_IT.read_text(encoding="utf-8").splitlines()[:5])


def test_readmes_name_every_component_and_only_existing_ones():
    names = list(A1_SKILLS) + list(AGENTS) + ["SessionStart"]
    for path in (README, README_IT):
        text = path.read_text(encoding="utf-8")
        assert [name for name in names if "`%s`" % name not in text] == [], path.name
        assert unknown_references(text) == [], path.name
        assert session_start.SAFETY_LINE in text, path.name


def test_readmes_say_what_guarantees_each_explained_point():
    for path, text, label in zip((README, README_IT), pages(), GUARANTEE_LABELS):
        blocks = marked_blocks(text)
        explained = [name for name in blocks if name.startswith("explain-")]
        assert explained == list(EXPLAINED_POINTS), path.name
        assert [name for name in explained if blocks[name].count(label) != 1] == [], path.name


def skill_text(name: str) -> str:
    return (REPO_ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")


def guarantee_line(block: str, label: str) -> str:
    return next(line for line in block.splitlines() if label in line)


def test_tutorial_checks_the_rules_with_a_rule_only_rules_md_carries():
    """The marker is also in the safety line, so a session that lost the import still answers a check on it."""
    rules = (REPO_ROOT / "rules.md").read_text(encoding="utf-8")
    elsewhere = [
        path for folder in ("skills", "agents", "hooks") for path in (REPO_ROOT / folder).rglob("*")
        if path.suffix in (".md", ".py", ".json")
    ]
    for tutorial in pages("tutorial"):
        assert "PE-RULES v1" not in tutorial
        tags = set(re.findall(r"PE:[a-z-]+", tutorial))
        assert tags, "the tutorial asks for no rule"
        for tag in tags:
            assert "[%s]" % tag in rules
            assert [path.name for path in elsewhere if tag in path.read_text(encoding="utf-8")] == [], tag


def test_readmes_do_not_list_the_end_to_end_test_as_a_guarantee():
    """A test run on request is evidence on the maintainer's machine, not a mechanism of the reader's session."""
    words = ("end-to-end", "da capo a fondo")
    for text, label, word in zip(pages(), GUARANTEE_LABELS, words):
        guarantees = [line for line in text.splitlines() if line.startswith(label)]
        assert len(guarantees) == len(EXPLAINED_POINTS)
        assert [line for line in guarantees if word in line] == []
    scope = ("is not exercised by it", "non è esercitato da quella prova")
    for text, not_covered in zip(pages("install"), scope):
        assert "`--plugin-dir`" in text and "`@rules.md`" in text and not_covered in text


def test_hook_registration_is_described_with_on_failure_everywhere():
    stale = (
        "only a timeout does not block", "solo un timeout non blocca",
        "A timeout does not block.", "a hook that times out does not block",
    )
    guard = (REPO_ROOT / "tools" / "dev_guard.py").read_text(encoding="utf-8")
    for name, text in zip(("README.md", "README.it.md", "dev_guard.py"), pages() + [guard]):
        for needed in ('"onFailure": "block"', "|| exit 2", "2.1.295"):
            assert needed in text, (name, needed)
        assert [claim for claim in stale if claim in text] == [], name


def test_readmes_list_disable_model_invocation_as_a_fourth_mechanism():
    """Claude Code, not the model's discipline, keeps the model from starting autonomous-execution."""
    fields, _ = parse_frontmatter(skill_text("autonomous-execution"))
    assert fields["disable-model-invocation"] == "true"
    field = "`disable-model-invocation`"
    counts = ("four things are mechanical", "quattro cose sono meccaniche")
    for intro, gates, count, label in zip(pages("explanation"), pages("explain-gates"), counts, GUARANTEE_LABELS):
        assert count in intro and field in intro
        assert field in guarantee_line(gates, label)


def test_readmes_define_a_blocking_test_finding_as_blunt_review_does():
    english = "a missing or tautological test on a behaviour that changed"
    italian = "una prova mancante o tautologica su un comportamento cambiato"
    assert english in skill_text("blunt-review")
    for text, phrase in zip(pages("explain-review"), (english, italian)):
        assert phrase in text


def test_tutorial_quotes_the_notice_the_hook_prints():
    notice = session_start.build_output(True, [])["systemMessage"]
    assert [text for text in pages("tutorial") if notice not in text] == []


def test_install_checks_the_official_marketplace_before_it_installs():
    steps = (
        "claude plugin marketplace list",
        "claude plugin marketplace add anthropics/claude-plugins-official",
        "claude plugin install pragmatic-engineering@pragmatic-engineering",
    )
    for text in pages("install"):
        positions = [text.find(step) for step in steps]
        assert -1 not in positions and positions == sorted(positions)
        assert text.index("/reload-plugins") > positions[-1]


def test_limits_do_not_claim_how_a_compacted_subagent_treats_the_import():
    stale = ("is not read again from disk", "non si rilegge dal disco")
    kept = (
        "a subagent that Claude Code has compacted keeps the imported rules is not verified",
        "un sotto-agente compattato da Claude Code conservi le regole importate non è verificato",
    )
    for text, claim, verified in zip(pages("limits"), stale, kept):
        assert claim not in text and verified in text


def test_readmes_give_the_review_rounds_the_ranges_of_blunt_review():
    skill = skill_text("blunt-review")
    rounds = {n: next(line for line in skill.splitlines() if line.startswith("**Round %s.**" % n)) for n in "12"}
    fixes_range = re.search(r"`(<[^`]*>\.\.<[^`]*>)`", rounds["1"]).group(1)
    assert "the range of the latest fixes" in rounds["2"]
    latest = ("the range of the latest fixes", "l'intervallo delle ultime correzioni")
    whole = ("whole range", "intero intervallo")
    for text, second, stale in zip(pages("explain-review-cycle"), latest, whole):
        assert fixes_range in text and second in text and stale not in text


def test_notice_credits_what_this_version_reuses():
    text = NOTICE.read_text(encoding="utf-8")
    for needed in ("superpowers", "Jesse Vincent", "MIT", "continuity-note", "Matt Pocock", "diataxis.fr"):
        assert needed in text, needed


def test_readmes_date_the_lenses_and_call_them_rules():
    for lenses, date in zip(pages("explain-lenses"), ("29 October 2026", "29 ottobre 2026")):
        assert date in lenses and "`CALIBRATING`" in lenses
        assert "`quality-scoring`" in lenses and "`interface-quality`" in lenses
    for limits, words in zip(pages("limits"), ("not mechanisms", "non meccanismi")):
        assert words in limits


def test_office_hours_guide_gives_every_key_and_the_way_to_turn_it_off():
    for text in pages("office-hours"):
        for needed in (
            "git config --global pe.officeHours 06-21", "pe.weekendFrom", "pe.holidays", "easter+1",
            "pe.personalRemotes", "`none`", "git config --get pe.officeHours",
        ):
            assert needed in text, needed


def test_uninstall_says_the_calibration_log_goes_with_the_data_folder():
    assert [text for text in pages("uninstall") if "`calibration.md`" not in text or "`--keep-data`" not in text] == []


CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
# The complexity check of the CI, with the four ruff rules that blunt-review names and nesting at most 3.
COMPLEXITY_CHECK = (
    "xargs -0 -r ruff check --preview --no-cache --select C901,PLR0912,PLR0915,PLR1702 "
    "--config 'lint.pylint.max-nested-blocks = 3'"
)


def test_ci_runs_the_suite_on_the_oldest_and_the_latest_python():
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    assert 'python: ["3.9", "3.x"]' in text and "python -m pytest -q" in text
    assert "e2e" in text and "superpowers" in text  # the comment that says what does not run there


def test_ci_checks_the_complexity_of_the_changed_python_files():
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    assert '"ruff==0.12.8"' in text and COMPLEXITY_CHECK in text
    assert "fetch-depth: 0" in text and "shell: bash" in text  # the base needs the history, the pipe needs pipefail
    assert "--diff-filter=d" in text and "-- '*.py'" in text
    assert "git hash-object -t tree /dev/null" in text  # a root commit has no parent to compare with


def test_readmes_name_the_ci_workflow():
    for path in (README, README_IT):
        assert "`.github/workflows/ci.yml`" in path.read_text(encoding="utf-8"), path.name
