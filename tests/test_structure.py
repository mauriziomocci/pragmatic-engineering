"""Structure checks on the repository itself."""
import hashlib
import importlib.util
import json
import re
import subprocess
import unicodedata
from pathlib import Path
from typing import List, Set, Tuple

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
RULES_SHA256 = "b5234bc97d0fe51a893ac962872663e8f43ac438df26c3f46dfbe08defc080d4"
# Requirements of spec section 17.3 and of the method rules the plugin carries: each one must sit in the block
# that reaches the right agents and say what the rule asks, so a rule gutted under its marker fails as well.
# A value is (block, phrase, ...): every phrase must be in the line, the qualifiers of the master included.
MIGRATION_REQUIREMENTS = {
    "self-review": (
        "Every agent", "Own work is reviewed before a commit is proposed, every review following `blunt-review`.",
    ),
    "burden-of-proof": (
        "Every agent",
        "Whoever adds code, a dependency, a rule, an option or a part of a spec carries the burden of proving it is "
        "needed, and over-engineering is the defect",
    ),
    "no-bug-left": ("Every agent", "closure statement"),
    "english-identifiers": ("Every agent", "in English"),
    "docs-same-commit": ("Every agent", "same commit"),
    "heavy-gates": ("Main session", "explicit written approval", "an autonomy opening spec approval"),
    "no-quiz": (
        "Main session",
        'The answer to "is it clear?" is awaited only at the two heavy gates and architecture choices, never while '
        "the user is away or during an autonomy",
    ),
    "lanes": (
        "Main session",
        "a feature uses one chain only, superpowers by default and spec-kit when the user asks or the project "
        "adopted it",
    ),
    "suite-before-commit": ("Every agent", "zero failures"),
    "evidence": ("Every agent", "never taken as evidence"),
    "reuse": ("Every agent", "the reuse statement"),
    "production-go": ("Every agent", "its own explicit go", "the blast radius and the way back"),
    "candour": (
        "Every agent",
        "the user's ideas are proposals to validate, not instructions to record: test each against feasibility, cost, "
        "sequence and risk, say first where it does not convince and the smallest next step (hard on the idea, never "
        "on the person), then record it with those caveats",
    ),
    "scope": ("Every agent", "no emoji anywhere", "no documentation file unless asked"),
    "taste-gates": ("Every agent", "about 40 lines"),
    "api-contract": ("Every agent", "never changes shape", "or by a profile while unreleased and unused"),
    "isolated-sessions": ("Every agent", "stops only what it started"),
    "office-hours": (
        "Every agent", "git config --get pe.officeHours", "explicit authorisation in chat", "and never pushed",
        "re-created inside its weekday hours with their real dates",
    ),
    "lenses": (
        "Main session", "never traded", "known defects", "as a proposal to the user",
        "a change to an interface or to API responses, other than a trivial text fix, gets one round of the UX and "
        "review lenses before the spec",
    ),
    "quality-gate": (
        "Main session",
        "Before integration or release every lens the work touches scores at least 8/10 with `quality-scoring`, "
        "from an independent review on evidence",
        "each with its cost",
    ),
    "user-away": (
        "Main session", "wait for the user", "git config --local --get pe.autonomy",
        "unless the user's words or the profile narrow them", "deletions outside the worktree",
        "in chat with a hard stop", "by profile only, an unreleased contract no client uses",
        # the openings the user's own rules define count too
        "an autonomy the user opens in chat with a hard stop, or the profile `git config --local --get pe.autonomy` "
        "gives, opens spec approval, data model, design outside the window and any opening the user's own rules "
        "define, unless the user's words or the profile narrow them, and, by profile only, an unreleased contract no "
        "client uses",
    ),
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


# Language neutrality: the plugin holds for every language, framework and database, so the rules name none and a skill
# or an agent names one only as an example. Names that are also common English words here (Go, C, Spring, Rails as a
# noun, Make) are left out on purpose: a whole-word, case-sensitive match on them would flag ordinary prose.
LANGUAGE_NAMES = (
    "Python", "Django", "Flask", "FastAPI", "pytest", "ruff", "mypy", "JavaScript", "TypeScript", "Node.js", "npm",
    "React", "Vue", "Angular", "Java", "Kotlin", "Gradle", "Maven", "JUnit", "Golang", "Rust", "cargo", "C#", ".NET",
    "dotnet", "PHP", "Laravel", "Composer", "C++", "Ruby", "Rails", "Swift", "PostgreSQL", "Postgres", "MySQL",
    "SQLite", "MongoDB", "ESLint", "Prettier",
)
EXAMPLE_MARKERS = ("for example", "for instance", "such as", "e.g.")
LANGUAGE_NAME = re.compile(
    r"(?<!\w)(?:%s)(?!\w)" % "|".join(re.escape(name) for name in sorted(LANGUAGE_NAMES, key=len, reverse=True)),
    re.IGNORECASE,
)
LIST_ITEM = re.compile(r"\s*(?:[-*]|\d+\.|\|)\s")
SENTENCE_END = re.compile(r"(?<=[.!?])(?<!e\.g\.)(?<!i\.e\.)\s+")


def sentences(text: str) -> List[str]:
    """The sentences of ``text``: a blank line or a list item starts a new block, a wrapped line joins its block."""
    blocks: List[List[str]] = [[]]
    for line in text.splitlines():
        if not line.strip() or LIST_ITEM.match(line):
            blocks.append([])
        if line.strip():
            blocks[-1].append(line.strip())
    return [part for block in blocks for part in SENTENCE_END.split(" ".join(block)) if part]


def unmarked_language_sentences(text: str) -> List[str]:
    """The sentences of ``text`` that name a language, framework, database or tool and carry no example marker."""
    return [
        sentence for sentence in sentences(text)
        if LANGUAGE_NAME.search(sentence) and not any(marker in sentence.lower() for marker in EXAMPLE_MARKERS)
    ]


def test_rules_name_no_language_framework_database_or_tool():
    assert LANGUAGE_NAME.findall(rules_text()) == []


def test_skills_and_agents_name_a_language_only_as_an_example():
    offenders = [
        "%s: %s" % (path, sentence)
        for path, text in repository_texts()
        if (path.parts[0] == "skills" and path.name == "SKILL.md") or (path.parts[0] == "agents" and path.suffix == ".md")
        for sentence in unmarked_language_sentences(text)
    ]
    assert offenders == []


@pytest.mark.parametrize("added", ["Python", "pytest", "C#", "C++", ".NET", "Node.js", "SQLite", "Ruff", "RUFF"])
def test_the_neutrality_check_catches_a_name_and_accepts_it_with_a_marker(added):
    unmarked = "The suite runs with %s on every push." % added
    assert unmarked_language_sentences(unmarked) == [unmarked]
    assert unmarked_language_sentences("The suite runs, for example, with %s on every push." % added) == []
    assert LANGUAGE_NAME.findall(rules_text() + "\n- A rule that names %s." % added) == [added]


def test_the_plugins_own_interpreter_is_not_taken_for_a_language_of_the_users_stack():
    """`python3` runs the plugin's scripts and hooks; the whole-word match leaves it alone, so no allowance is needed."""
    assert unmarked_language_sentences("Run `python3 script.py` from the skill's folder.") == []


def test_the_neutrality_check_reads_a_sentence_across_wrapped_lines_and_stops_at_a_list_item():
    wrapped = "Use the tools of the stack,\nfor example pytest\nand its plugins. Done."
    assert unmarked_language_sentences(wrapped) == []
    assert unmarked_language_sentences("- for example one\n- Python by itself") == ["- Python by itself"]
    assert unmarked_language_sentences("It names Python. For example, it names Go.") == ["It names Python."]
    assert unmarked_language_sentences("It names Pythonic style and cargoes.") == []


def test_rules_stay_short():
    # Every session and every subagent reads the whole file: each added word is paid for in all of them.
    # 9,500 again since the subtraction pass of 29 October 2026: the autonomy of user-away had raised the cap
    # to 9,650, and cutting repetition paid for it, so a new rule now has to remove words before it adds any.
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
        "When the write of the report under `.pe/reviews/` is refused, put the whole report in your final message, "
        "before the five lines, and write `REPORT: inline`; `REPORT: none` keeps its one meaning, that nothing "
        "was reviewed.",
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
REQUIRED_SECTIONS = ("tutorial", "how-to", "install", "uninstall", "explanation", "lifecycle", "limits", "reference")
EXPLAINED_POINTS = (
    "explain-lanes", "explain-gates", "explain-review", "explain-review-cycle", "explain-lenses",
    "explain-rules-import", "explain-working-rules", "explain-continuity", "explain-office-hours",
    "explain-communication",
)
GUARANTEE_LABELS = ("**Guaranteed by:**", "**Garantito da:**")  # README.md, README.it.md
LENS_PARTS = ("lenses-roles", "lenses-together", "lenses-score", "lenses-gate")  # the subsections of explain-lenses


def marked_blocks(text: str):
    """Text from each section marker to the next one, by section id, in file order."""
    parts = SECTION_ID.split(text)
    ids = parts[1::2]
    assert len(set(ids)) == len(ids), "a section id is repeated"
    return dict(zip(ids, parts[2::2]))


def lens_group(text: str) -> str:
    """The section on the lenses with its four subsections: one explained point, whose guarantee closes the last."""
    blocks = marked_blocks(text)
    return "".join(blocks[name] for name in ("explain-lenses",) + LENS_PARTS)


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


def test_readmes_explain_where_good_practices_come_from_with_the_same_shape():
    """The subsection on language neutrality: one heading and two paragraphs in each language, Context7 named."""
    headings = ("### Any language, framework and database", "### Qualsiasi linguaggio, framework e database")
    for text, heading in zip(pages("language-neutral"), headings):
        lines = text.strip().splitlines()
        assert lines[0] == heading
        assert len([part for part in "\n".join(lines[1:]).split("\n\n") if part.strip()]) == 2
        assert "Context7" in text


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
        blocks["explain-lenses"] = lens_group(text)
        assert [name for name in explained if blocks[name].count(label) != 1] == [], path.name


def test_readmes_list_every_rule_of_rules_md_under_the_point_that_explains_it():
    """A rule with no explained point has no home in the explanation: its label must close one of the points."""
    rules = {marker for markers in EXPECTED_RULE_MARKERS.values() for marker in markers}
    for path, text, label in zip((README, README_IT), pages(), GUARANTEE_LABELS):
        blocks = marked_blocks(text)
        blocks["explain-lenses"] = lens_group(text)
        guarantees = "\n".join(
            line for name in EXPLAINED_POINTS for line in blocks[name].splitlines() if line.startswith(label)
        )
        assert sorted(rule for rule in rules if "`%s`" % rule not in guarantees) == [], path.name


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
    italian = "un test mancante o tautologico su un comportamento cambiato"
    assert english in skill_text("blunt-review")
    for text, phrase in zip(pages("explain-review"), (english, italian)):
        assert phrase in text
    assert "una prova mancante" not in "".join(pages())  # "prova" means evidence; a test is a "test" (class S2)


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


REVIEWER_PERMISSIONS = tuple(
    "Bash(git %s --no-color --no-ext-diff --no-textconv --no-relative --ignore-submodules=none:*)" % verb
    for verb in ("show", "diff")
)


def test_install_gives_the_reviewers_permission_rules_and_the_limits_point_to_them():
    """Without them a run without a person reads nothing, so they are a step of the install, not a footnote."""
    pointers = (
        "the two permission rules of the install guide", "le due regole di permesso della guida all'installazione",
    )
    for install, limits, words in zip(pages("install"), pages("limits"), pointers):
        assert [rule for rule in REVIEWER_PERMISSIONS if rule not in install.splitlines()] == []
        assert [rule for rule in REVIEWER_PERMISSIONS if rule in limits] == [] and words in limits


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


def test_readmes_split_the_lenses_into_four_subsections_in_the_same_order():
    for path, text in zip((README, README_IT), pages()):
        ids = list(marked_blocks(text))
        start = ids.index("explain-lenses") + 1
        assert ids[start:start + len(LENS_PARTS)] == list(LENS_PARTS), path.name
        assert [name for name in LENS_PARTS if not marked_blocks(text)[name].strip().startswith("#### ")] == [], path.name


SCORING_RULES = (  # the steps of the score in quality-scoring, in the order the skill applies them
    "apply, in this order",
    "each S1 takes 4 points away and caps the lens at 4",
    "each S2 takes 1.5 points away and caps the lens at 7",
    "each S3 takes 0.5 points away",
    "the floor is 1, and the result is rounded down to the half point",
    "So 8 means no S1, no S2 and at most four S3.",
)


def rules_out_of_order(skill: str) -> List[str]:
    """The steps of ``SCORING_RULES`` missing from ``skill``, or all of them when they are there but out of order."""
    missing = [rule for rule in SCORING_RULES if rule not in skill]
    places = [skill.find(rule) for rule in SCORING_RULES]
    return missing or ([] if places == sorted(places) else list(SCORING_RULES))


def test_readmes_give_the_score_formula_that_quality_scoring_defines():
    """The pinned sentences of the READMEs state these figures and their order, so a change of the skill turns this red."""
    assert rules_out_of_order(skill_text("quality-scoring")) == []


def test_the_score_formula_check_sees_a_step_removed_or_moved():
    """The example of the READMEs holds only if the cap of the S2 comes before the S3 is taken off."""
    skill = skill_text("quality-scoring")
    s2, s3 = SCORING_RULES[2], SCORING_RULES[3]
    assert rules_out_of_order(skill.replace(s2, "")) == [s2]
    assert rules_out_of_order(skill.replace(s2, "@").replace(s3, s2).replace("@", s3)) == list(SCORING_RULES)


def test_readmes_date_the_lenses_and_call_them_rules():
    for lenses, date in zip(map(lens_group, pages()), ("29 October 2026", "29 ottobre 2026")):
        assert date in lenses and "`CALIBRATING`" in lenses
        assert "`quality-scoring`" in lenses and "`interface-quality`" in lenses
    for limits, words in zip(pages("limits"), ("not mechanisms", "non meccanismi")):
        assert words in limits


def test_readmes_follow_the_lenses_with_the_life_cycle_in_three_modes():
    """One part right after the lenses: the three modes under their own headings, then the table that compares them."""
    for path, text in zip((README, README_IT), pages()):
        ids = list(marked_blocks(text))
        assert ids[ids.index("lenses-gate") + 1] == "lifecycle", path.name
        block = marked_blocks(text)["lifecycle"]
        assert block.strip().startswith("### "), path.name
        assert block.count("\n#### ") == 4, path.name  # normal mode, day autonomy, night autonomy, the comparison
        table = [line for line in block.splitlines() if line.startswith("|")]
        assert len(table) == 2 + 4, path.name  # header, separator and one row each for gate 2, away, push and stop
        assert {line.count("|") for line in table} == {5}, path.name  # a label column and the three modes


def normal_mode_steps(block: str):
    """The nine numbered steps of normal mode, by number: each from its number up to the next step or heading."""
    steps = re.finditer(r"^(\d)\. \*\*.*?(?=^\d\. \*\*|^#### |\Z)", block, re.MULTILINE | re.DOTALL)
    return {int(step.group(1)): step.group(0) for step in steps}


def test_readmes_put_the_round_of_the_ux_and_review_lenses_in_phase_2_as_development_workflow_does():
    assert "one round of the UX lens and the review lens first" in skill_text("development-workflow")
    for text, phrase in zip(pages("lifecycle"), ("the UX lens proposes where the button goes",
                                                 "la lente UX propone dove va il pulsante")):
        steps = normal_mode_steps(text)
        assert sorted(steps) == list(range(1, 10))
        assert phrase in steps[3] and phrase not in steps[2]


def test_readmes_say_the_page_is_for_one_person_and_where_a_team_stands():
    said = (
        "This page is written for one person who installs the plugin on their own machine. The plugin keeps its "
        "state there, in its data folder, in your git configuration and in the `.pe/` folders that git ignores, so "
        "by itself it shares nothing between the people of a team; the skills do not say yet who gives the written "
        "approval of a gate when a team works together.",
        "Questa pagina è scritta per una persona che installa il plugin sulla propria macchina. Il plugin tiene lì "
        "il suo stato, nella propria cartella dei dati, nella tua configurazione di git e nelle cartelle `.pe/` che "
        "git ignora, quindi da solo non condivide nulla fra le persone di un team; le skill non dicono ancora chi "
        "dia l'approvazione scritta di un cancello quando lavora un team.",
    )
    for text, sentence in zip(pages(), said):
        assert sentence in text.split("<!-- section:")[0]


TOC_ENTRY = re.compile(r"^( *)- \[[^\]]+\]\(#([^)]+)\)$", re.MULTILINE)
HEADING = re.compile(r"^(#{2,4}) (.+)$")


def github_anchor(heading: str) -> str:
    """The anchor GitHub gives a heading: lower case, punctuation dropped, each space turned into a hyphen."""
    return re.sub(r"[^\w -]", "", heading.lower()).replace(" ", "-")


def headings_by_anchor(text: str):
    """Anchor to (level, id of the section it sits in) for every heading below the title, code fences skipped."""
    found, section, fenced = {}, "", False
    for line in text.splitlines():
        fenced ^= line.lstrip().startswith("```")
        marker, heading = SECTION_ID.match(line), (None if fenced else HEADING.match(line))
        section = marker.group(1) if marker else section
        if heading:
            anchor = github_anchor(heading.group(2))
            assert anchor not in found, "two headings give the same anchor: " + anchor
            found[anchor] = (len(heading.group(1)), section)
    return found


def test_readmes_open_with_a_table_of_contents_that_lists_the_same_headings():
    """Each page lists every heading down to the third level, and the two lists point at the same places."""
    tables = []
    for path, text in zip((README, README_IT), pages()):
        headings = headings_by_anchor(text)
        entries = [(len(indent), anchor) for indent, anchor in TOC_ENTRY.findall(text.split("<!-- section:")[0])]
        assert entries, path.name
        assert [anchor for _, anchor in entries if anchor not in headings] == [], path.name
        listed = {anchor for _, anchor in entries}
        assert [anchor for anchor, (level, _) in headings.items() if level <= 3 and anchor not in listed] == []
        assert [anchor for indent, anchor in entries if indent != 2 * (headings[anchor][0] - 2)] == [], path.name
        tables.append([(indent,) + headings[anchor] for indent, anchor in entries])
    assert tables[0] == tables[1]


RECREATION_STEPS = (  # the four checks of recreate_night_commits.py in its order, as each README words them
    ("four checks", "the files are exactly those of the tag", "the number of commits is the same",
     "the messages are the same", "both dates of every commit fall inside the window"),
    ("quattro controlli", "i file sono esattamente quelli del tag", "il numero dei commit è lo stesso",
     "i messaggi sono gli stessi", "entrambe le date di ogni commit cadono dentro la finestra"),
)


def test_readmes_list_the_four_checks_of_the_re_creation_in_the_order_the_script_runs_them():
    script = REPO_ROOT / "skills" / "safe-operations" / "recreate_night_commits.py"
    spec = importlib.util.spec_from_file_location("recreate_night_commits", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert [name for name, _ in module.CHECKS] == ["tree", "commit count", "messages", "dates"]
    for text, phrases in zip(pages("lifecycle"), RECREATION_STEPS):
        places = [text.find(phrase) for phrase in phrases]
        assert -1 not in places, phrases
        assert places == sorted(places), phrases


OFFICE_HOURS_COMMANDS = (  # the lines of the guide that a reader copies; the placeholder follows the language
    "git config --global pe.officeHours 06-21",
    "git config --global pe.weekendFrom 10",
    "git config --global pe.holidays 01-01,12-25,12-26,easter+1",
    "git config --global pe.personalRemotes https://github.com/<{account}>/",
)


def test_office_hours_guide_gives_every_key_and_the_way_to_turn_it_off():
    for text, account in zip(pages("office-hours"), ("you", "tuo-account")):
        for command in OFFICE_HOURS_COMMANDS:
            assert command.format(account=account) in text.splitlines(), command
        for needed in ("pe.weekendFrom", "pe.holidays", "easter+1", "pe.personalRemotes", "`none`"):
            assert needed in text, needed
        assert "git config --show-origin --get-regexp '^pe\\.'" in text
        assert "`git config --global --add pe.personalRemotes git@github.com:<%s>/`" % account in text


def test_office_hours_guide_says_the_end_hour_is_outside_the_window():
    stated = ("`06-21` runs from 06:00 up to 20:59", "`06-21` va dalle 06:00 alle 20:59")
    assert [text for text, words in zip(pages("office-hours"), stated) if words not in text] == []


def test_autonomy_guide_sets_the_key_in_one_repository_only():
    """The model reads only the value local to the repository: a global one would open every repository."""
    for text in pages("autonomy"):
        assert "`git config --local --unset pe.autonomy`" in text
        assert "`git config --local --get pe.autonomy`" in text
    assert [text for text in pages() if "--global pe.autonomy" in text] == []


def test_autonomy_example_opens_no_api_contract():
    """A reader who copies the line must not open the API contract without having decided it."""
    for text in pages("autonomy"):
        lines = [line for line in text.splitlines() if line.startswith("git config --local pe.autonomy")]
        assert lines == ["git config --local pe.autonomy spec,schema"]
    for section in pages("configure"):
        row = next(line for line in section.splitlines() if line.startswith("| `pe.autonomy` |"))
        assert row.endswith("| `spec,schema` |")


# Whole sentences of the guided configuration: English, then Italian, in the section that holds them.
GUIDED_SENTENCES = {
    "tutorial": (
        ("Steps 1 and 3 run in a terminal, and from step 4 you type into the session. Do step 3 yourself: the rules "
         "are not loaded yet, so nothing makes the session back up the file first.",
         "I passi 1 e 3 si eseguono in un terminale, e dal passo 4 scrivi nella sessione. Il passo 3 fallo tu: le "
         "regole non sono ancora caricate, quindi nulla fa fare prima alla sessione una copia del file."),
        ("prints two notes, both in English.", "stampa due avvisi, entrambi in inglese."),
        ("and the safety line, a long line that starts with",
         "e la riga di rete di sicurezza, una riga lunga che comincia con"),
        ("Silence alone does not show that the hook ran; to check, run `ls -l` on the path that follows the `@` in "
         "your import line: it lists `rules.md`, which shows only that the hook copied it at least once (at step 2), "
         "not that it ran at this start, and an error that the file is missing means the hook has not run. Step 5 is "
         "the check that the rules arrive.",
         "Il solo silenzio non mostra che l'hook sia girato; per controllare, esegui `ls -l` sul percorso che segue "
         "la `@` nella tua riga di import: elenca `rules.md`, il che mostra solo che l'hook l'ha copiato almeno una "
         "volta (al passo 2), non che sia girato a questo avvio, e un errore di file mancante significa che l'hook "
         "non è girato. Il controllo che le regole arrivano è il passo 5."),
        ("(for the autonomy profile you choose the openings, and it proposes none)",
         "(per il profilo di autonomia scegli tu le aperture, e non ne propone nessuna)"),
        ("Before it changes anything it shows you the exact `git config` command and waits for your yes, then reads "
         "the value back, for the autonomy profile too.",
         "Prima di cambiare qualcosa ti mostra il comando `git config` esatto e aspetta il tuo sì, poi rilegge il "
         "valore, anche per il profilo di autonomia."),
        ('Ask: "Quote your rule `PE:lanes`." (you can also ask it in your own language).',
         'Chiedi: "Quote your rule `PE:lanes`." (puoi anche chiederlo in italiano).'),
        ("You should see an answer that says that the lane comes from `development-workflow` and that a feature "
         "uses one chain of tools, superpowers by default and spec-kit when you ask for it or the project adopted it.",
         "Dovresti vedere una risposta che dice che la corsia viene da `development-workflow` e che una "
         "funzionalità usa una sola catena di strumenti, superpowers per impostazione predefinita e spec-kit quando "
         "lo chiedi o il progetto l'ha adottato."),
        ("The label `PE:lanes` is in `rules.md` and in nothing else a session loads, not in the safety line and not "
         "in a skill, so a right answer shows that the import reached the session.",
         "L'etichetta `PE:lanes` sta in `rules.md` e in nient'altro che una sessione carichi, non nella riga di rete "
         "di sicurezza e non in una skill, quindi una risposta giusta mostra che l'import ha raggiunto la sessione."),
        ('ending with "is it clear?" in your language;', "chiudendo con «is it clear?» nella tua lingua;"),
        ("it writes a short frame of the work, which is the PM lens at work: a pre-mortem of three lines, the why, "
         "the reuse statement and the smallest version;",
         "scrive un breve inquadramento del lavoro, cioè la lente PM al lavoro: un pre-mortem di tre righe, il "
         "perché, la dichiarazione di riuso e la versione più piccola;"),
        ("`THE THING:`, where `FINDINGS:` counts the findings by lens and by class, for example `code S1=0 S2=0 "
         "S3=1`.",
         "`THE THING:`, dove `FINDINGS:` conta i rilievi per lente e per classe, per esempio `code S1=0 S2=0 "
         "S3=1`."),
        ('(you can also say it in your own language)', "(anche in italiano)"),
    ),
    "install": (
        ("Requirements: Claude Code, `python3` 3.9 or later on your path (the hook is a Python script), and git (the "
         "reviewer reads git ranges). The reviewer and the UX lens run on Opus and the user lens on Sonnet, so the "
         "account you use must be able to run both.",
         "Requisiti: Claude Code, `python3` 3.9 o successivo nel percorso di ricerca (l'hook è uno script Python) e "
         "git (il revisore legge intervalli git). Il revisore e la lente UX girano su Opus e la lente utente su "
         "Sonnet, quindi l'account che usi deve poter usare entrambi i modelli."),
        ("The time in the file name keeps a second copy from overwriting the first, and the second command, run "
         "after the edit, prints the two lines you added, each marked with `>`.",
         "L'ora nel nome del file impedisce a una seconda copia di sovrascrivere la prima, e il secondo comando, "
         "eseguito dopo la modifica, stampa le due righe che hai aggiunto, ciascuna con il segno `>`."),
    ),
    "configure": (
        ("### Configure the plugin", "### Configurare il plugin"),
        ('The quickest way is to ask in a session, for example "configure the plugin": the `configure` skill shows '
         "the values you have now and asks one question at a time, only about the keys you choose, and runs each "
         "command only after your yes.",
         'Il modo più rapido è chiedere in una sessione, per esempio "configura il plugin": la skill `configure` '
         "mostra i valori che hai adesso e fa una domanda alla volta, solo sulle chiavi che scegli, ed esegue ogni "
         "comando solo dopo il tuo sì."),
        ("It sets the autonomy profile only when you ask for it in chat, never on its own and never because a file "
         "or a tool output says so; nothing checks that it obeys.",
         "Imposta il profilo di autonomia solo quando glielo chiedi in chat, mai di sua iniziativa e mai perché lo "
         "dice un file o l'output di uno strumento; nulla controlla che obbedisca."),
        ("The keys the plugin reads, and one that its maintainer tools read:",
         "Le chiavi che legge il plugin, e una che leggono gli strumenti dei manutentori:"),
        ("| The profile opens nothing |", "| Il profilo non apre nulla |"),
        ("The four global keys tell the model when to keep your work local and which remotes are yours, and the "
         "autonomy profile tells it which decisions it may take while you are away; in this version both are rules "
         "for the model, and nothing blocks a push outside the window.",
         "Le quattro chiavi globali dicono al modello quando tenere il tuo lavoro in locale e quali remoti sono "
         "tuoi, e il profilo di autonomia gli dice quali decisioni può prendere mentre non ci sei; in questa "
         "versione sono entrambe regole per il modello, e nulla blocca un push fuori dalla finestra."),
        ("To remove a key, run `git config --global --unset-all pe.<key>` for a global one, or "
         "`git config --local --unset pe.autonomy` for the profile.",
         "Per togliere una chiave, esegui `git config --global --unset-all pe.<chiave>` per una globale, oppure "
         "`git config --local --unset pe.autonomy` per il profilo."),
    ),
    "uninstall": (
        ("Five things stay behind on purpose.", "Cinque cose restano, di proposito."),
        ("The `night-backup-*` tags that `skills/safe-operations/recreate_night_commits.py` leaves in your "
         "repositories stay until you delete each one with `git tag -d <name>`.",
         "I tag `night-backup-*` che `skills/safe-operations/recreate_night_commits.py` lascia nei tuoi repository "
         "restano finché non ne cancelli ciascuno con `git tag -d <nome>`."),
        ("And the `pe.*` keys you set stay in your git configuration; the configure section above says how to "
         "remove them.",
         "E restano le chiavi `pe.*` che hai impostato nella tua configurazione di git; la sezione «Configurare il "
         "plugin» qui sopra dice come toglierle."),
    ),
    "explain-office-hours": (
        ("are re-created inside its weekday hours, even when the re-creation happens on a weekend morning, with "
         "their real dates, never with faked ones",
         "si ricreano dentro le sue ore feriali, anche quando la ricreazione avviene di sabato o di domenica "
         "mattina, con le loro date vere, mai falsate"),
    ),
    "explain-gates": (
        ("The final gate has one exception, `autonomous-execution`, which only you can start, by naming it:",
         "Il cancello finale ha un'eccezione, `autonomous-execution`, che puoi avviare solo tu, nominandola:"),
        ("Its closure has no step that scores the lenses, and the description of its merge request holds the "
         "reviewer's lines and no scores; the skills do not say yet whether a lens under 8 makes the run NOT "
         "MERGEABLE.",
         "La sua chiusura non ha un passo che dia i voti alle lenti, e la descrizione della sua merge request "
         "contiene le righe del revisore e nessun voto; le skill non dicono ancora se una lente sotto 8 renda "
         "l'esecuzione NOT MERGEABLE."),
    ),
    "explain-lenses": (
        ("The first three, the PM, UX and review lenses, frame, propose and attack. The fourth, the user lens, only "
         "tries the work as a person would.",
         "Le prime tre, le lenti PM, UX e di revisione, inquadrano, propongono e attaccano. La quarta, la lente "
         "utente, si limita a provare il lavoro come lo proverebbe una persona."),
    ),
    "lenses-roles": (
        ("(the skills do not say where that file lives, what it holds or what happens when the project has none)",
         "(le skill non dicono dove stia quel file, che cosa contenga né che cosa succeda quando il progetto non ne "
         "ha uno)"),
        ('until the project has a script that makes them, its findings carry the label "from templates, not seen on '
         'screen".',
         "finché il progetto non ha uno script che li produca, i suoi rilievi portano l'etichetta «from templates, "
         "not seen on screen»."),
    ),
    "lenses-together": (
        ("No lens agrees by default: each re-checks the other's claims against the screenshots, the measurements and "
         "the code before accepting them,",
         "Nessuna lente è d'accordo per principio: ciascuna ricontrolla le affermazioni dell'altra su screenshot, "
         "misure e codice prima di accettarle,"),
        ("A disagreement that survives the round before the spec goes to you, or to the PM lens under an autonomy "
         "that opens `spec`, and to the project's designer where there is one, with both positions written down; the "
         "skills do not define yet when a disagreement survives. One that comes up later, inside an approved spec, "
         "goes to the PM lens whenever you are away, with no autonomy needed, as the next paragraph says.",
         "Un disaccordo che resiste al giro prima della spec va a te, o alla lente PM sotto un'autonomia che apre "
         "`spec`, e al designer del progetto dove c'è, con le due posizioni scritte; le skill non definiscono ancora "
         "quando un disaccordo resiste. Uno che nasce dopo, dentro una spec approvata, va alla lente PM ogni volta che "
         "non ci sei, senza bisogno di un'autonomia, come dice il paragrafo seguente."),
    ),
    "explain-working-rules": (
        ("A delivered API contract, one that is merged, running in an environment or documented to the developers of "
         "a client, never changes shape:",
         "Un contratto API consegnato, cioè già unito, in esecuzione in un ambiente o documentato agli sviluppatori "
         "di un client, non cambia mai forma:"),
    ),
    "explain-communication": (
        ("Your own ideas are proposals to validate, not instructions to record: the model tests each against "
         "feasibility, cost, sequence and risk and says first where it does not convince, then records it with "
         "those caveats.",
         "Le tue idee sono proposte da validare, non istruzioni da registrare: il modello mette alla prova ciascuna "
         "su fattibilità, costo, sequenza e rischio e dice per prima cosa dove non lo convince, poi la registra con "
         "quelle riserve."),
    ),
    "office-hours": (
        ("Set them once, from a terminal or by asking the model in a session (it shows you each command and runs it "
         "after your yes), with `pe.personalRemotes` in the same step as `pe.officeHours`:",
         "Impostale una volta, da un terminale o chiedendo al modello in una sessione (ti mostra ogni comando e lo "
         "esegue dopo il tuo sì), con `pe.personalRemotes` nello stesso passo di `pe.officeHours`:"),
        ("`pe.holidays` lists the days you do not work, separated by commas, each `MM-DD` with the month first, or",
         "`pe.holidays` elenca i giorni in cui non lavori, separati da virgole, ciascuno `MM-DD` con il mese per "
         "primo, oppure"),
        ("`pe.weekendFrom` and `pe.holidays` count only while `pe.officeHours` gives a window.",
         "`pe.weekendFrom` e `pe.holidays` contano solo finché `pe.officeHours` dà una finestra."),
        ("`git remote -v` lists those URLs; the closing slash keeps `<you>` from matching `<you>2`.",
         "`git remote -v` elenca quegli URL; la barra finale impedisce a `<tuo-account>` di corrispondere a "
         "`<tuo-account>2`."),
        ("To read back every key with the file it comes from, run `git config --show-origin --get-regexp '^pe\\.'`; "
         "git prints the key names in lowercase, and nothing checks the form of a value, so compare what it prints "
         "with the examples above.",
         "Per rileggere ogni chiave con il file da cui viene, esegui `git config --show-origin --get-regexp "
         "'^pe\\.'`; git stampa i nomi delle chiavi in minuscolo e nulla controlla la forma di un valore, quindi "
         "confronta ciò che stampa con gli esempi qui sopra."),
    ),
    "autonomy": (
        ("say it in chat with a hard stop, the hour at which the work must stop, for example "
         '"go on without me until 18:00, but leave the data model to me": it opens',
         "dillo in chat con un orario di fine, l'ora in cui il lavoro deve fermarsi, per esempio "
         "«vai avanti senza di me fino alle 18:00, ma il modello dei dati lo decido io»: apre"),
        ("set the profile inside that repository, naming only what you open, either from a terminal or by asking "
         "the model, which shows you the command and runs it after your yes;",
         "imposta il profilo dentro quel repository, nominando solo ciò che apri, da un terminale oppure "
         "chiedendolo al modello, che ti mostra il comando e lo esegue dopo il tuo sì;"),
        ("Read it back with `git config --local --get pe.autonomy`; no output means it is not set.",
         "Rileggila con `git config --local --get pe.autonomy`; se non stampa nulla, non è impostata."),
        ("and only through the profile: name it only for an API that has no client yet.",
         "e solo con il profilo: nominalo solo per un'API che non ha ancora un client."),
        ("You set it, or you ask the model in chat to set it, which it does only for the openings you name and never "
         "on its own or because a file or a tool output says so; nothing stops it in this version.",
         "La imposti tu, oppure chiedi in chat al modello di impostarla, e lui lo fa solo per le aperture che "
         "nomini e mai di sua iniziativa né perché lo dice un file o l'output di uno strumento; in questa versione "
         "nulla glielo impedisce."),
    ),
    "explain-review-cycle": (
        ("`<tip before the fixes>..<tip after the fixes>` (from the last commit before the fixes to the last one "
         "after them)",
         "`<tip before the fixes>..<tip after the fixes>` (dall'ultimo commit prima delle correzioni all'ultimo "
         "dopo)"),
    ),
    "explanation": (
        ("Ten of the parts below each end with a line that says what guarantees the part; two have none: the life "
         "cycle in three modes, because it only follows the others, and the note on languages and frameworks, "
         "which only says where good practices come from.",
         "Dieci delle parti qui sotto chiudono ciascuna con una riga che dice che cosa garantisce la parte; due non "
         "ce l'hanno: il ciclo di vita in tre modalità, perché non fa che seguire le altre, e la nota sui linguaggi "
         "e sui framework, che dice solo da dove vengono le buone pratiche."),
    ),
    "lifecycle": (
        ("Normal mode is the name for work without an autonomy: you supervise it, and you approve the spec at "
         "gate 2 and the final validation at gate 6.",
         "La modalità normale è il nome del lavoro senza un'autonomia: lo segui tu, e approvi tu la spec al "
         "cancello 2 e la validazione finale al cancello 6."),
        ("Each light gate is a quick coherence check, and after the last one the whole list is read once more with "
         "fresh eyes before any code (`development-workflow`).",
         "Ogni cancello leggero è un rapido controllo di coerenza, e dopo l'ultimo si rilegge l'intero elenco una "
         "volta ancora a mente fresca prima di qualunque codice (`development-workflow`)."),
        ("Each lens the job touches gets a score from `quality-scoring`: here the new code (`code`), the old report "
         "code it touches (`legacy`), the route of the export with its permission check (`api`) and the three "
         "interface lenses (`clarity`, `aspect`, `accessibility`), measured on the real page in both themes.",
         "Ogni lente che il lavoro tocca riceve un voto da `quality-scoring`: qui il codice nuovo (`code`), il "
         "vecchio codice del rapporto che tocca (`legacy`), la rotta dell'esportazione con il suo controllo dei "
         "permessi (`api`) e le tre lenti dell'interfaccia (`clarity`, `aspect`, `accessibility`), misurate sulla "
         "pagina vera in entrambi i temi."),
        ('You open it in chat, for this piece of work and with a hard stop: "go on without me until 18:00, but '
         'leave the data model to me."',
         "La apri in chat, per questo lavoro e con un orario di fine: «vai avanti senza di me fino alle 18:00, ma "
         "il modello dei dati lo decido io.»"),
        ("That opens the approval of the spec (`spec`) and design outside your office hours (`design`, which does "
         "nothing inside them), and your words keep the data model (`schema`) out.",
         "Questo apre l'approvazione della spec (`spec`) e la progettazione fuori dal tuo orario d'ufficio "
         "(`design`, che dentro l'orario non fa nulla), e le tue parole lasciano fuori il modello dei dati "
         "(`schema`)."),
        ("The steps are those of normal mode, and what changes is who decides; where the autonomy opens `spec`, a "
         "review cycle on the spec also comes before gate 2.",
         "I passi sono quelli della modalità normale, e cambia chi decide; dove l'autonomia apre `spec`, prima del "
         "cancello 2 viene anche un ciclo di revisione sulla spec."),
        ("The plugin defines no opening for publishing, so nothing is pushed without your go unless your own rules "
         "define one.",
         "Il plugin non definisce nessuna apertura per la pubblicazione, quindi senza il tuo via non si spinge "
         "nulla, salvo che le tue regole ne definiscano una."),
        ("An autonomy does not open gate 6: the work comes to it ready and waits for you there.",
         "Un'autonomia non apre il cancello 6: il lavoro ci arriva pronto e lì aspetta te."),
        ("With the spec approved and the tasks written, the model follows them to the letter, one task at a time and "
         "test first.",
         "Con la spec approvata e i compiti scritti, il modello li segue alla lettera, un compito alla volta e con "
         "il test prima."),
        ("| Only with your go, and nothing to a remote that is not personal outside your office hours; a merge is "
         "always yours | Nothing without your go; the plugin opens no push, only an opening your own rules define "
         "does | Nothing to a remote that is not personal: local commits only, re-created in the morning; to a "
         "personal remote, only with your go |",
         "| Solo con il tuo via, e niente verso un remoto che non sia personale fuori dal tuo orario d'ufficio; un "
         "merge è sempre tuo | Niente senza il tuo via; il plugin non apre nessun push, lo apre solo un'apertura che "
         "le tue regole definiscono | Niente verso un remoto che non sia personale: solo commit locali, ricreati al "
         "mattino; verso un remoto personale, solo con il tuo via |"),
        ("| Approved before the night starts; as by day only if the autonomy opens `design` |",
         "| Approvata prima che la notte cominci; come di giorno solo se l'autonomia apre `design` |"),
        ("| At the hard stop you gave, or at gate 6 |", "| All'orario di fine che hai dato, oppure al cancello 6 |"),
    ),
    "lenses-score": (
        ("Eight things can get a score (`quality-scoring` calls each of them a lens too, besides the four role "
         "lenses), each with a short id:",
         "Otto cose possono ricevere un voto (anche `quality-scoring` chiama lente ciascuna di esse, oltre alle "
         "quattro lenti di ruolo), ciascuna con una sigla breve:"),
        ("Before reviewing, whoever scores writes this perimeter:",
         "Prima di rivedere, chi assegna i voti scrive questo perimetro:"),
        ("S2, serious, means that it holds today and breaks with normal use or with growth: for example a missing or "
         "tautological test (a test that cannot fail) on a behaviour that changed, or a document contradicted by "
         "the code, such as an instruction that no longer works, which `quality-scoring` classes S2 and not S1.",
         "S2, seria, significa che oggi regge e si rompe con l'uso normale o con la crescita: per esempio un test "
         "mancante o tautologico (un test che non può fallire) su un comportamento cambiato, o un documento "
         "contraddetto dal codice, come un'istruzione che non funziona più, che `quality-scoring` classifica S2 e "
         "non S1."),
        ("Each lens starts from 10: each S1 takes away 4 points and caps the lens at 4, each S2 takes away 1.5 "
         "points and caps it at 7, each S3 takes away 0.5 points, the lowest score is 1 and the result is rounded "
         "down to the half point, so 8 means no S1, no S2 and at most four S3.",
         "Ogni lente parte da 10: ogni S1 toglie 4 punti e limita la lente a 4, ogni S2 toglie 1,5 punti e la "
         "limita a 7, ogni S3 toglie 0,5 punti, il voto minimo è 1 e il risultato si arrotonda per difetto al "
         "mezzo punto, quindi 8 significa nessun S1, nessun S2 e al più quattro S3."),
        ("The steps apply in the order written, S1 first, then S2, then S3, whatever the order of the report. For "
         "example, a lens with one S2 and one S3 scores 6.5, because the S2 takes 10 down to 8.5, its cap brings "
         "that to 7, and then the S3 takes 0.5 away; with the S3 first the same two findings would give 7, which is "
         "why the order is fixed. `quality-scoring` does not say yet what the cap does with two findings of the "
         "same class (two S2 give 7 if the cap comes after both and 5.5 if it comes after each), so the example "
         "above keeps one of each. One serious finding takes a lens below 8 by itself.",
         "I passi si applicano nell'ordine scritto, prima gli S1, poi gli S2, poi gli S3, qualunque sia l'ordine "
         "del rapporto. Per esempio, una lente con un S2 e un S3 prende 6,5, perché l'S2 porta 10 a 8,5, il suo "
         "limite lo riporta a 7, e poi l'S3 toglie 0,5; con l'S3 per primo gli stessi due rilievi darebbero 7, ed è "
         "per questo che l'ordine è fisso. `quality-scoring` non dice ancora che cosa faccia il limite con due "
         "rilievi della stessa classe (due S2 danno 7 se il limite viene dopo entrambi e 5,5 se viene dopo "
         "ciascuno), quindi l'esempio qui sopra ne usa uno per classe. Un solo rilievo serio porta da solo una "
         "lente sotto 8."),
    ),
    "lenses-gate": (
        ("`quality-scoring` does not say yet whether a finding that a later round saw fixed still counts in the "
         "score, nor which round's `FINDINGS:` line the gate reads.",
         "`quality-scoring` non dice ancora se un rilievo che un giro successivo ha visto corretto conti ancora nel "
         "voto, né quale riga `FINDINGS:` di quale giro legga il cancello."),
        ("Choosing the deferral is the go to ship the work with a deferred defect, and that go stays with you: "
         "during an autonomy the PM lens may only park an open blocking finding or propose a deferral to you.",
         "Scegliere il rinvio è il via a consegnare il lavoro con un difetto rinviato, e quel via resta a te: "
         "durante un'autonomia la lente PM può solo mettere da parte un rilievo bloccante ancora aperto o "
         "proporti un rinvio."),
    ),
    "limits": (
        ("the autonomy (including the rule that the model sets its profile only when you ask)",
         "l'autonomia (compresa la regola per cui il modello ne imposta il profilo solo quando glielo chiedi)"),
    ),
    "reference": (
        ("There are no commands in this version and, besides the `SessionStart` hook described below, only one script, "
         "`skills/safe-operations/recreate_night_commits.py`, which `safe-operations` tells the model to run.",
         "In questa versione non ci sono comandi e, oltre all'hook `SessionStart` descritto sotto, c'è un solo "
         "script, `skills/safe-operations/recreate_night_commits.py`, che `safe-operations` dice al modello di "
         "eseguire."),
        ("`skills/safe-operations/recreate_night_commits.py` re-creates, inside the office hours, the commits made "
         "outside them and never pushed, and leaves a `night-backup-<YYYYMMDD-HHMMSS>` tag in the repository.",
         "`skills/safe-operations/recreate_night_commits.py` ricrea, dentro l'orario d'ufficio, i commit fatti fuori "
         "da esso e mai pubblicati, e lascia nel repository un tag `night-backup-<YYYYMMDD-HHMMSS>`."),
        ("runs each `git config` command only after your yes, the autonomy profile included.",
         "esegue ogni comando `git config` solo dopo il tuo sì, profilo di autonomia compreso."),
        ("To run it by hand: `python3 <the folder of safe-operations>/recreate_night_commits.py <base>`, from any "
         "directory of the repository.",
         "Per eseguirlo a mano: `python3 <la cartella di safe-operations>/recreate_night_commits.py <base>`, da una "
         "cartella qualsiasi del repository."),
    ),
}


@pytest.mark.parametrize("section", sorted(GUIDED_SENTENCES))
def test_readmes_state_the_guided_configuration_in_both_languages(section):
    for text, language in zip(pages(section), (0, 1)):
        assert [pair[language] for pair in GUIDED_SENTENCES[section] if pair[language] not in text] == []


def test_the_italian_readme_names_the_end_time_of_an_autonomy_in_plain_words():
    assert "arresto netto" not in pages()[1]


def test_install_dates_the_backup_to_the_second_so_a_retry_keeps_the_first():
    for text in pages("install"):
        lines = text.splitlines()
        assert "cp ~/.claude/CLAUDE.md ~/.claude/CLAUDE.md.$(date +%Y%m%d-%H%M%S).bak" in lines
        assert 'diff "$(ls -t ~/.claude/CLAUDE.md.*.bak | head -1)" ~/.claude/CLAUDE.md' in lines
        assert "date +%F" not in text


PE_KEY = re.compile(r"\bpe\.[A-Za-z]+\b")
TABLE_KEY = re.compile(r"^\| `(pe\.[A-Za-z]+)` \|", re.MULTILINE)
KEY_READER_FOLDERS = ("agents", "hooks", "lib", "tools")
CONFIGURE_SKILL = Path("skills/configure/SKILL.md")


def reads_keys(path: Path) -> bool:
    """Whether the file at ``path`` is one that reads a ``pe.<key>``: the rules, the skills and the code.

    ``configure`` is not one: it names every key to explain it, so counting it would let a key that nothing reads
    stay in the tables.
    """
    return (
        path.parts[0] in KEY_READER_FOLDERS
        or path == Path("rules.md")
        or (path.parts[0] == "skills" and path.name == "SKILL.md" and path != CONFIGURE_SKILL)
    )


def keys_the_plugin_uses(texts: List[Tuple[Path, str]]) -> Set[str]:
    """The ``pe.<key>`` names that the files of ``texts`` which read keys name: the keys a reader can set."""
    return {key for path, text in texts if reads_keys(path) for key in PE_KEY.findall(text)}


def test_the_configure_tables_list_exactly_the_keys_the_plugin_uses():
    """A seventh key read anywhere, or a row left out of one language, turns this red."""
    used = keys_the_plugin_uses(repository_texts())
    assert used, "no key found: the scan reads nothing"
    for name, section in zip(("README.md", "README.it.md"), pages("configure")):
        assert set(TABLE_KEY.findall(section)) == used, name
    assert [key for key in sorted(used) if key not in skill_text("configure")] == []


def test_the_key_check_sees_a_row_removed_from_a_table():
    section = pages("configure")[1]
    row = next(line for line in section.splitlines() if line.startswith("| `pe.holidays` |"))
    used = keys_the_plugin_uses(repository_texts())
    assert set(TABLE_KEY.findall(section.replace(row + "\n", ""))) == used - {"pe.holidays"}


def test_the_key_check_sees_a_key_that_only_the_documents_still_name():
    """`configure` and the READMEs name every key: a key no reader uses any more must still turn the check red."""
    texts = [(path, text if path == CONFIGURE_SKILL else text.replace("pe.weekendFrom", "pe.dropped"))
             for path, text in repository_texts()]
    used = keys_the_plugin_uses(texts)
    assert "pe.weekendFrom" in skill_text("configure") and "pe.weekendFrom" not in used
    for section in pages("configure"):
        assert set(TABLE_KEY.findall(section)) != used


def test_the_key_scan_reads_agents_and_skips_the_skill_that_explains_the_keys():
    assert reads_keys(Path("agents/blunt-reviewer.md"))
    assert reads_keys(Path("skills/safe-operations/SKILL.md"))
    assert not reads_keys(CONFIGURE_SKILL)
    assert not reads_keys(Path("README.md"))


def test_readmes_place_the_configure_section_the_tutorial_step_and_the_skill_row():
    asks = ('"Configure the plugin."', '"Configura il plugin."')
    for text, ask in zip(pages(), asks):
        ids = list(marked_blocks(text))
        assert ids[ids.index("install") + 1] == "configure"
        assert ask in marked_blocks(text)["tutorial"]
        assert "| `configure` |" in marked_blocks(text)["reference"]


def test_uninstall_says_the_calibration_log_goes_with_the_data_folder():
    assert [text for text in pages("uninstall") if "`calibration.md`" not in text or "`--keep-data`" not in text] == []


CI_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "ci.yml"
# The complexity check of the CI, with the four ruff rules that blunt-review names and nesting at most 3.
COMPLEXITY_CHECK = (
    "xargs -0 -r ruff check --preview --no-cache --select C901,PLR0912,PLR0915,PLR1702 "
    "--config 'lint.pylint.max-nested-blocks = 3'"
)


# A failure turned into a success: the forms that keep a red command from failing its job.
SWALLOWED_FAILURE = re.compile(r"\|\|\s*(?:true|exit 0|:)(?![\w-])|;\s*true(?![\w-])|set \+e")


def test_ci_runs_the_suite_on_the_oldest_and_the_latest_python():
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    assert 'python: ["3.9", "3.x"]' in text and "python -m pytest -q" in text
    assert 'python -m pip install "pytest>=7"' in text  # no cap: pip already picks the pytest that 3.9 supports
    assert "e2e" in text and "superpowers" in text  # the comment that says what does not run there


def test_ci_checks_the_complexity_of_the_changed_python_files():
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    assert '"ruff==0.12.8"' in text and COMPLEXITY_CHECK in text
    assert "fetch-depth: 0" in text and "shell: bash" in text  # the base needs the history, the pipe needs pipefail
    assert "--diff-filter=d" in text and "-- '*.py'" in text
    assert "git hash-object -t tree /dev/null" in text  # a root commit has no parent to compare with


def test_ci_pins_one_runner_image_and_the_node24_actions_without_a_stored_token():
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    assert re.findall(r"runs-on: (\S+)", text) == ["ubuntu-24.04", "ubuntu-24.04"]  # CPython 3.9 has no 26.04 build
    assert re.findall(r"uses: (\S+)", text) == [
        "actions/checkout@v7", "actions/setup-python@v7", "actions/checkout@v7", "actions/setup-python@v7",
    ]
    assert text.count("persist-credentials: false") == 2  # one per checkout; no step pushes


def test_ci_lets_a_red_command_fail_its_job_with_the_rights_it_has_today():
    text = CI_WORKFLOW.read_text(encoding="utf-8")
    assert SWALLOWED_FAILURE.search(text) is None and "continue-on-error" not in text
    assert text.count("permissions:") == 1 and "\npermissions:\n  contents: read\n\n" in text


def test_swallowed_failure_catches_the_forms_it_must():
    for swallowed in ("pytest -q || true", "ruff check . || :", "ruff check .; true", "set +e", "run || exit 0"):
        assert SWALLOWED_FAILURE.search(swallowed), swallowed
    assert SWALLOWED_FAILURE.search("git rev-parse -q --verify HEAD~1 || git hash-object -t tree /dev/null") is None


def test_readmes_name_the_ci_workflow():
    for path in (README, README_IT):
        assert "`.github/workflows/ci.yml`" in path.read_text(encoding="utf-8"), path.name
