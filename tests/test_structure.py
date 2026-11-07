"""Structure checks on the repository itself."""
import ast
import hashlib
import importlib.util
import json
import re
import subprocess
import unicodedata
from pathlib import Path
from typing import List, Set, Tuple

import pytest

import pre_tool_use
import privacy_check
import session_start
from support import (
    SKILLS,
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
RULES_SHA256 = "4a89e3c940d0fc1a014f22ec930b900677b4e631666fd5d780687e7baa561258"
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
    # the profile exception is no longer pointed at user-away, which ties it to the user's absence
    "heavy-gates": (
        "Main session",
        "explicit written approval, never the request that asked for the work",
        "an autonomy opening spec approval, the first",
    ),
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
    "evidence": ("Every agent", "a claim of another agent or lens is re-checked, never taken as evidence"),
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
    # the semicolon right after the exception: no pointer to user-away ties the profile to the user's absence
    "api-contract": ("Every agent", "never changes shape", "or by a profile while unreleased and unused;"),
    "isolated-sessions": ("Every agent", "stops only what it started"),
    "office-hours": (
        "Every agent", "git config --get pe.officeHours", "explicit authorisation in chat", "and never pushed",
        "re-created inside its weekday hours with their real dates",
    ),
    "lenses": (
        "Main session", "never traded", "known defects", "as a proposal to the user",
        "a change to an interface or to API responses, other than a trivial text fix, gets one round of the UX, user "
        "and review lenses before the spec; an agreement of lenses without an independent check is a finding",
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
        # the openings the user's own rules define count too, and the autonomy holds with the user present
        "an autonomy the user opens in chat with a hard stop, or the profile `git config --local --get pe.autonomy` "
        "gives, holds with the user present too, asks nothing it opens, and opens spec approval, data model, design "
        "outside the window and any opening the user's own rules define, unless the user's words or the profile "
        "narrow them, and, by profile only, an unreleased contract no client uses",
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
    known = set(SKILLS) | set(AGENTS) | {"superpowers:%s" % name for name in SUPERPOWERS_SKILLS}
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
        "use `superpowers:writing-plan`, `writing-plans`, `blunt-reviews`, `speckit-foo` and `memory-hygiene`"
    )
    assert problems == [
        "superpowers:writing-plan does not exist",
        "speckit-foo is not a spec-kit %s command" % SPECKIT_TESTED_VERSION,
        "`writing-plans` must be written superpowers:writing-plans",
        "`blunt-reviews` looks like a misspelt blunt-review",
        "memory-hygiene does not exist in this version",
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
    assert list(config["hooks"]) == ["SessionStart", "PreToolUse"]
    entries = config["hooks"]["SessionStart"]
    assert len(entries) == 1 and "matcher" not in entries[0]
    (hook,) = entries[0]["hooks"]
    assert hook == {
        "type": "command",
        "command": 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/session_start.py"',
        "timeout": 10,
    }
    assert (REPO_ROOT / "hooks" / "session_start.py").is_file()


def test_hooks_json_runs_the_hook_on_its_five_tools_and_lets_a_failed_hook_through():
    entries = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert entries == [{"matcher": "Agent|Bash|Write|Edit|NotebookEdit", "hooks": [{
        "type": "command",
        "command": 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/pre_tool_use.py"',
        "timeout": 10,
        # a crash, a timeout or no python3 must never block a call of any user: the limits fall back to declared
        "onFailure": "continue",
    }]}]
    # The hook's one git call must end before Claude Code gives up on the hook.
    assert pre_tool_use.GIT_TIMEOUT < entries[0]["hooks"][0]["timeout"]


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


RUNTIME_FOLDERS = ("hooks", "lib")  # what the plugin ships and runs; tools/ is the maintainer's
TOOL_MODULES = frozenset(path.stem for path in (REPO_ROOT / "tools").glob("*.py"))


def tool_dependencies(source: str) -> List[str]:
    """The tools/ modules a source imports, and every string literal "tools" (a sys.path entry towards it)."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            found += [alias.name for alias in node.names if alias.name.split(".")[0] in TOOL_MODULES]
        elif isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in TOOL_MODULES:
            found.append(node.module)
        elif isinstance(node, ast.Constant) and node.value == "tools":
            found.append("the path tools")
    return found


def test_the_shipped_runtime_imports_nothing_from_tools():
    runtime = [path for folder in RUNTIME_FOLDERS for path in sorted((REPO_ROOT / folder).rglob("*.py"))]
    assert len(runtime) >= 3 and {"dev_guard", "privacy_check"} <= TOOL_MODULES
    assert [(path.name, tool_dependencies(path.read_text(encoding="utf-8"))) for path in runtime
            if tool_dependencies(path.read_text(encoding="utf-8"))] == []


@pytest.mark.parametrize("source", [
    "import privacy_check", "from dev_guard import shell_text", "import os, install_dev_hooks.x",
    'sys.path.insert(0, str(ROOT / "tools"))',
])
def test_the_runtime_import_check_sees_each_way_into_tools(source):
    assert tool_dependencies(source) != []


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
        # --remerge-diff redoes each merge, and no option turns off a merge driver of the user's git configuration
        "There are two exceptions. The first is the merge read of step 2, which redoes each merge: a merge driver "
        "that a git configuration defines (`merge.<name>.driver`) runs during it and can hide a resolution. The "
        "second is `log.showSignature`: when it is set, git runs the program that `gpg.program` names during any "
        "show or log.",
        "When the write of the report under `.pe/reviews/` is refused, put the whole report in your final message, "
        "before the five lines, and write `REPORT: inline`; `REPORT: none` keeps its one meaning, that nothing "
        "was reviewed.",
        # the agent has no Skill tool, so the user's rubric reaches the findings only through the main session
        "The rule in the skills loaded with you about a skill of the same name in the user's configuration is not for "
        "you: class with the table loaded with you; the main session re-classes.",
        "Then comes one group for every lens of the perimeter that you score (`code`, `legacy`, `architecture`, "
        "`api`, `docs`), zeros included, with its counts of S1, S2 and S3: the main session computes the scores from "
        "this line with `quality-scoring`, without a judgment of its own; when the user's own rubric governs, it "
        "first re-classes the findings of the report with that rubric.",
    ):
        assert needed in body, needed
    # Bash runs only the read forms that hooks/pre_tool_use.py lets through: no redirect into .pe/reviews/, and a
    # path whose output is still too long is read in part and reported as partial coverage.
    (bash_rule,) = [line for line in body.splitlines() if line.startswith("Use Bash only")]
    assert "no pipe, redirect or other shell syntax" in bash_rule and ".pe/reviews/" not in bash_rule
    (step_3,) = [line for line in body.splitlines() if line.startswith("3. ")]
    assert "redirect" not in step_3 and "coverage is `partial`" in step_3
    assert "PreToolUse hook" in sections(body)["What you write"]
    for retired in (
        "origin/main..HEAD", "the grammar is the whole interface", "cannot change what you read",
        "with `quality-scoring`, without a judgment of its own.",  # the user's rubric now comes first, when it governs
        "The twin line",  # a term the agent finds defined nowhere it reads
        "This is declared, not enforced.",  # hooks/pre_tool_use.py enforces it when it runs
    ):
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


MERGES_READ = "`git log --no-color --oneline --merges <base>..<tip>`"
REMERGE_READ = "`git show --no-color %s --remerge-diff <sha>`" % PATCH_FLAGS


def test_blunt_reviewer_reads_every_merge_with_remerge_diff():
    """The combined diff of step 2 shows nothing for a merge that keeps one side of a conflict; this read shows it.

    Step 1 lists the merges with --oneline, because the Merge: line of a show depends on the user's format.pretty.
    """
    _, body = parse_frontmatter(AGENT.read_text(encoding="utf-8"))
    (step_1,) = [line for line in body.splitlines() if line.startswith("1. ")]
    (step_2,) = [line for line in body.splitlines() if line.startswith("2. ")]
    assert MERGES_READ in step_1
    assert REMERGE_READ in step_2 and "git 2.36" in step_2 and "`Merge:`" not in step_2
    assert "when this read fails, name the merge in the report, and the coverage is `partial`" in step_2


def test_prints_a_patch_knows_the_verbs_and_the_patch_option():
    assert prints_a_patch("show", "`git show x`") and prints_a_patch("diff", "`git diff a..b`")
    assert prints_a_patch("log", "`git log -p --stat x`") and prints_a_patch("log", "`git log --patch x`")
    assert not prints_a_patch("log", "`git log --oneline a..b`")


WORKER = REPO_ROOT / "agents" / "worker.md"
WORKER_SECTIONS = [
    "The brief you receive", "How you work", "Keeping in step with the integration", "What you write",
    "Your final message",
]
# Without it a new worktree shows `?? .pe/` once the delivery file exists, and every delivery is refused as unclean.
IGNORE_FIRST = "Before any other write, create `.pe/.gitignore` with the single line `*` if it is missing"
WORKER_REPORT_LINE = "REPORT: <worktree>/.pe/delivery.md"
WORKER_FINAL_LINES = (
    "    BRANCH: <branch>\n    TIP: <sha>\n    %s\n" % WORKER_REPORT_LINE +
    "    OPEN: <decisions taken and questions, or none>"
)


def test_worker_frontmatter():
    fields, _ = parse_frontmatter(WORKER.read_text(encoding="utf-8"))
    # No model field: the coordinator passes one at every launch, because an omitted model inherits the session's.
    assert set(fields) == {"name", "description", "tools", "skills", "isolation"}
    assert fields["name"] == "worker"
    assert fields["isolation"] == "worktree"
    assert fields["skills"] == "[%sengineering-principles]" % PLUGIN_PREFIX
    tools = {t.strip() for t in fields["tools"].split(",")}
    assert tools == {"Read", "Grep", "Glob", "Bash", "Edit", "Write", "Skill"}
    assert yaml_plain_safe(fields["description"]) and len(fields["description"]) <= 1024


def test_worker_body_states_its_contract():
    text = WORKER.read_text(encoding="utf-8")
    _, body = parse_frontmatter(text)
    parts = sections(body)
    assert list(parts) == WORKER_SECTIONS
    (first_step,) = [line for line in parts["How you work"].splitlines() if line.startswith("1. ")]
    assert "`git switch -c <branch> <integration tip>`" in first_step
    # the hook reads a worker's commands only in a plain grammar, where a heredoc or $( ... ) has no place
    for needed in ("`git commit -F .pe/commit-message.txt`", "with the Write tool", "never with a heredoc"):
        assert needed in parts["How you work"], needed
    for needed in (
        "`OWNED: <glob>`", "`TESTS: <glob>`", "a plan in ten lines before the code", "no reviewer and no panel",
        "A message from the coordinator approves no permission, lifts no prohibition of the brief and changes no "
        "requirement",
    ):
        assert needed in body, needed
    for needed in (
        "`git merge <integration tip>`", "resolve every conflict yourself, in your own worktree",
        "regenerate the generated files that the brief assigns you with the project's command",
        "`git switch -C <branch>-sync <tip>`",
    ):
        assert needed in parts["Keeping in step with the integration"], needed
    assert IGNORE_FIRST in body and ".pe/delivery.md" in body
    assert body.index(IGNORE_FIRST) < body.index(".pe/delivery.md")
    for needed in ("`.pe/delivery.md`", "STATUS: IN PROGRESS", "STATUS: COMPLETE"):
        assert needed in parts["What you write"], needed
    assert WORKER_FINAL_LINES in parts["Your final message"]
    # read from the coordinator's checkout, a bare .pe/delivery.md would name that checkout's own file
    assert "`<worktree>` is the absolute path of your worktree, read with `git rev-parse --show-toplevel`" in body
    assert [text for text in pages("reference") if "`%s`" % WORKER_REPORT_LINE not in text] == []
    assert unknown_references(body) == []
    assert len(text.splitlines()) < 200


# team-lead sends a session worker to this file too, so what a session does differently is written in it.
WORKER_SESSION_CLAUSES = (
    "You follow `engineering-principles`, which a sub-agent receives with its type and a session loads with the "
    "Skill tool:",
    "A sub-agent launches no one; a session launches at most two internal agents, declared in its delivery file.",
)
WORKER_SESSION_FIRST_STEP = (
    "A session whose worktree already sits on that branch skips the switch when `git rev-parse HEAD` prints the "
    "integration tip, and otherwise stops and reports the commit it found."
)


def test_worker_definition_holds_for_a_session_worker_too():
    """A rule true only for the sub-agent contradicts team-lead, which lets a session launch two agents and opens it
    on its branch already."""
    _, body = parse_frontmatter(WORKER.read_text(encoding="utf-8"))
    (first_step,) = [line for line in sections(body)["How you work"].splitlines() if line.startswith("1. ")]
    assert [clause for clause in WORKER_SESSION_CLAUSES if clause not in body] == []
    assert WORKER_SESSION_FIRST_STEP in first_step
    assert "You launch no one" not in body and "loaded with you" not in body


WORKER_STEP_FOUR_IN_ORDER = (
    "then the tests of the touched area, green;",
    "then the project's own lint and format checks on your changed files, the ones its CI and pre-commit "
    "configuration run, clean;",
    "then your review of the diff.",
    "Commit each task, with its box ticked, on your branch when its tests are green",
)


def test_worker_runs_the_project_checks_before_its_review_and_ticks_its_own_task():
    """In a live trial no worker ran the formatter of the project's pre-commit, and the coordinator ticked the tasks
    in commits outside every reviewed range: both are steps of the worker, in this order."""
    _, body = parse_frontmatter(WORKER.read_text(encoding="utf-8"))
    (fourth_step,) = [line for line in sections(body)["How you work"].splitlines() if line.startswith("4. ")]
    positions = [fourth_step.find(phrase) for phrase in WORKER_STEP_FOUR_IN_ORDER]
    assert -1 not in positions and positions == sorted(positions), positions


def test_no_agent_file_outside_the_list():
    """The checks below run on every agent of AGENTS, so an agent missing from it would skip them."""
    assert {path.stem for path in (REPO_ROOT / "agents").glob("*.md")} == set(AGENTS)


def preloaded_skills(agent: str) -> List[str]:
    """The names in the `skills` field of an agent, as written there."""
    fields, _ = parse_frontmatter((REPO_ROOT / "agents" / ("%s.md" % agent)).read_text(encoding="utf-8"))
    return [n.strip() for n in fields["skills"].strip("[]").split(",") if n.strip()]


@pytest.mark.parametrize("agent", AGENTS)
def test_agent_preloads_existing_skills(agent):
    names = preloaded_skills(agent)
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
    "explain-rules-import", "explain-working-rules", "explain-continuity", "explain-parallel",
    "explain-office-hours",
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


# The sentence of each opening that lists the parts of the plugin: English, then Italian.
OPENING_PARTS = (
    "Version 0.1.0 is the core of the method: the rules, the skills, the two agents, a `SessionStart` hook that keeps "
    "the rules in place and a `PreToolUse` hook that holds the reviewer to its interface and a worker to its worktree.",
    "La versione 0.1.0 è il nucleo del metodo: le regole, le skill, i due agenti, un hook `SessionStart` che tiene le "
    "regole al loro posto e un hook `PreToolUse` che tiene il revisore alla sua interfaccia e un worker al suo "
    "worktree.",
)


def test_readmes_list_every_part_of_the_plugin_in_the_opening():
    for text, sentence in zip(pages(), OPENING_PARTS):
        assert sentence in text.split("<!-- section:")[0]


def test_readmes_link_each_other_at_the_top():
    assert "(README.it.md)" in "\n".join(README.read_text(encoding="utf-8").splitlines()[:5])
    assert "(README.md)" in "\n".join(README_IT.read_text(encoding="utf-8").splitlines()[:5])


def test_readmes_name_every_component_and_only_existing_ones():
    names = list(SKILLS) + list(AGENTS) + ["SessionStart"]
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


def test_readmes_list_disable_model_invocation_as_a_mechanism():
    """Claude Code, not the model's discipline, keeps the model from starting autonomous-execution."""
    fields, _ = parse_frontmatter(skill_text("autonomous-execution"))
    assert fields["disable-model-invocation"] == "true"
    field = "`disable-model-invocation`"
    for intro, gates, label in zip(pages("explanation"), pages("explain-gates"), GUARANTEE_LABELS):
        assert field in intro
        assert field in guarantee_line(gates, label)


# The sentence of the explanation that counts the mechanisms, and the number words it may use: English, then Italian.
MECHANISM_SENTENCES = (
    re.compile(r"In this version (\w+) things are mechanical: (.*?)\. Everything else is a rule for the model\."),
    re.compile(r"In questa versione (\w+) cose sono meccaniche: (.*?)\. Tutto il resto è una regola per il modello\."),
)
NUMBER_WORDS = (
    {4: "four", 5: "five", 6: "six", 7: "seven"}, {4: "quattro", 5: "cinque", 6: "sei", 7: "sette"},
)
# The mechanisms that are not a hook: Claude Code's import, the agents' skills field and the field of a skill.
OTHER_MECHANISMS = ("`@`", "`skills`", "`disable-model-invocation`")


def test_readmes_count_every_mechanism_of_the_plugin():
    """A hook event added to hooks/hooks.json, or a skill preloaded by an agent, turns this red until the sentence
    that counts the mechanisms names it with the right count."""
    events = list(json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"])
    named = ["`%s`" % event for event in events] + list(OTHER_MECHANISMS)
    preloaded = ["`%s`" % name[len(PLUGIN_PREFIX):] for agent in AGENTS for name in preloaded_skills(agent)]
    for intro, pattern, words in zip(pages("explanation"), MECHANISM_SENTENCES, NUMBER_WORDS):
        found = pattern.search(intro)
        assert found, pattern.pattern
        count, listed = found.groups()
        assert count == words[len(named)]
        assert [name for name in named + preloaded if name not in listed] == []


def test_readmes_define_a_blocking_test_finding_as_blunt_review_does():
    english = "a missing or tautological test on a behaviour that changed"
    italian = "un test mancante o tautologico su un comportamento cambiato"
    assert english in skill_text("blunt-review")
    for text, phrase in zip(pages("explain-review"), (english, italian)):
        assert phrase in text
    assert "una prova mancante" not in "".join(pages())  # "prova" means evidence; a test is a "test" (class S2)


def test_readmes_say_the_reviewer_reads_each_merge_with_remerge_diff():
    """The read needs git 2.36 and runs the merge drivers of git's configuration; the limits say what each costs."""
    for explanation, limits in zip(pages("explain-review"), pages("limits")):
        assert "git log --merges" in explanation and "--remerge-diff" in explanation and "2.36" in explanation
        (old_git,) = [line for line in limits.splitlines() if "--remerge-diff" in line and "2.36" in line]
        assert "`partial`" in old_git
        assert [line for line in limits.splitlines() if "`merge.<name>.driver`" in line] != []


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
    for needed in ("superpowers", "Jesse Vincent", "MIT", "continuity-note", "Matt Pocock", "diataxis.fr",
                   "knowledge-work-plugins", "Apache License 2.0"):
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


# The round of the lenses in interface-quality, in its order: the live runs of 4 November 2026 failed where the UX
# lens proposed before measuring and the user lens was not heard before the answer.
ROUND_STEPS = (
    "1. Before proposing, the UX lens measures what the change touches as it is: every touched state and its "
    "contrast in both themes, and the widths and the zoom of rule 12; for an API, the routes as they answer today. "
    "The step ends with the `Not verified:` line of `quality-scoring`, naming each touched state, each width, the 200% "
    "zoom or a theme it did not measure, with the reason, and it says which themes the page has, with the evidence.",
    "2. The UX lens proposes from the need of the person who uses the product.",
    "3. The review lens (`blunt-review`) attacks on evidence, cost, the simpler alternative and the impact on code "
    "and architecture.",
    "4. The user lens walks the main task of the touched pages, or the client's flow for an API, and its findings "
    "reach the UX lens with the attack.",
    "5. The UX lens answers or changes the proposal.",
    "6. Then the decision: on the person's need the UX lens prevails, on correctness, evidence and the quality of "
    "the code the review lens prevails.",
)


def steps_out_of_order(steps: Tuple[str, ...], text: str) -> List[str]:
    """The ``steps`` missing from ``text``, or all of them when they are there but out of order."""
    missing = [step for step in steps if step not in text]
    places = [text.find(step) for step in steps]
    return missing or ([] if places == sorted(places) else list(steps))


def test_readmes_give_the_score_formula_that_quality_scoring_defines():
    """The pinned sentences of the READMEs state these figures and their order, so a change of the skill turns this red."""
    assert steps_out_of_order(SCORING_RULES, skill_text("quality-scoring")) == []


def test_the_score_formula_check_sees_a_step_removed_or_moved():
    """The example of the READMEs holds only if the cap of the S2 comes before the S3 is taken off."""
    skill = skill_text("quality-scoring")
    s2, s3 = SCORING_RULES[2], SCORING_RULES[3]
    assert steps_out_of_order(SCORING_RULES, skill.replace(s2, "")) == [s2]
    moved = skill.replace(s2, "@").replace(s3, s2).replace("@", s3)
    assert steps_out_of_order(SCORING_RULES, moved) == list(SCORING_RULES)


def test_the_round_of_the_lenses_keeps_its_six_steps_in_order():
    """A step moved, even with its old number kept, or a step missing turns this red."""
    assert steps_out_of_order(ROUND_STEPS, skill_text("interface-quality")) == []


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


def test_readmes_put_the_round_of_the_lenses_in_phase_2_as_development_workflow_does():
    assert "one round of the UX, user and review lenses first" in skill_text("development-workflow")
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
        assert steps_out_of_order(phrases, text) == []


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


EXCLUDE_SENTENCES = (
    "`team-lead` adds `.claude/worktrees/`, where Claude Code puts the worktrees of sub-agents, to the repository's "
    "`info/exclude` before the first sub-agent launch, a local line never committed, and removes a sub-agent's "
    "worktree with `git worktree remove` once its branch is integrated and its report recorded.",
    "`team-lead` aggiunge `.claude/worktrees/`, dove Claude Code mette i worktree dei sotto-agenti, "
    "all'`info/exclude` del repository prima del primo lancio di un sotto-agente, una riga locale mai inclusa in un "
    "commit, e toglie il worktree di un sotto-agente con `git worktree remove` quando il suo ramo è integrato e il "
    "suo rapporto registrato.",
)


# Whole sentences the two pages must carry: English, then Italian, in the section that holds them.
GUIDED_SENTENCES = {
    "explain-lanes": (
        ("When users are hurt right now and the signal of a recent change's way back has fired, the first proposal "
         "is that way back, and the diagnosis follows.",
         "Quando le persone sono colpite adesso ed è scattato il segnale della via del ritorno di un cambio recente, "
         "la prima proposta è quella via del ritorno, e la diagnosi viene dopo."),
        ("the blast radius and the way back, with the signal that triggers it, are said first",
         "si dicono prima il raggio d'azione e la via del ritorno, con il segnale che la fa scattare"),
    ),
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
        # an autonomy holds whether or not the user is present, so the profile is not described by absence
        ("| What the lenses may decide in your place, from `spec`, `schema`, `design` and `contract` |",
         "| Che cosa le lenti possono decidere al posto tuo, fra `spec`, `schema`, `design` e `contract` |"),
        ("The four global keys tell the model when to keep your work local and which remotes are yours, and the "
         "autonomy profile tells it which decisions it may take in your place; in this version both are rules for "
         "the model, and nothing blocks a push outside the window.",
         "Le quattro chiavi globali dicono al modello quando tenere il tuo lavoro in locale e quali remoti sono "
         "tuoi, e il profilo di autonomia gli dice quali decisioni può prendere al posto tuo; in questa versione "
         "sono entrambe regole per il modello, e nulla blocca un push fuori dalla finestra."),
        ("To remove a key, run `git config --global --unset-all pe.<key>` for a global one, or "
         "`git config --local --unset pe.autonomy` for the profile.",
         "Per togliere una chiave, esegui `git config --global --unset-all pe.<chiave>` per una globale, oppure "
         "`git config --local --unset pe.autonomy` per il profilo."),
    ),
    "uninstall": (
        ("Six things stay behind on purpose.", "Sei cose restano, di proposito."),
        ("The `.claude/worktrees/` line that `team-lead` added to `info/exclude` stays until you delete it from the "
         "file that `git rev-parse --git-path info/exclude` names.",
         "La riga `.claude/worktrees/` che `team-lead` ha aggiunto a `info/exclude` resta finché non la cancelli dal "
         "file che `git rev-parse --git-path info/exclude` nomina."),
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
        ('a bare "ok" to a spec nobody read is not approval, and neither is the request that asked for the work.',
         'un semplice "ok" a una spec che nessuno ha letto non è un\'approvazione, e non lo è neppure la richiesta '
         "che ha avviato il lavoro."),
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
        # the name the user looks for: the three lenses that frame, propose and attack are the Trinity
        ("The first three, the PM, UX and review lenses, frame, propose and attack. Together these three are called "
         "the Trinity. The fourth, the user lens, only tries the work as a person would.",
         "Le prime tre, le lenti PM, UX e di revisione, inquadrano, propongono e attaccano. Insieme queste tre si "
         "chiamano la Trinità. La quarta, la lente utente, si limita a provare il lavoro come lo proverebbe una "
         "persona."),
    ),
    "lenses-roles": (
        ("(the skills do not say where that file lives, what it holds or what happens when the project has none)",
         "(le skill non dicono dove stia quel file, che cosa contenga né che cosa succeda quando il progetto non ne "
         "ha uno)"),
        ('until the project has a script that makes them, its findings carry the label "from templates, not seen on '
         'screen".',
         "finché il progetto non ha uno script che li produca, i suoi rilievi portano l'etichetta «from templates, "
         "not seen on screen»."),
        ("and twenty-two iron rules, added on 3 November 2026, that every proposal, review and score of an interface "
         "holds, each breach a finding that `quality-scoring` classes.",
         "e ventidue regole di ferro, aggiunte il 3 novembre 2026, che ogni proposta, revisione e voto di "
         "un'interfaccia rispetta, dove ogni violazione è un rilievo che `quality-scoring` classifica."),
        ("Rules 1 to 12 and 22 are on fidelity, measurement and accessibility: the designer's document and the "
         "approved mockups decide, and each block of work closes with a fidelity review by someone who did not build "
         "it; where the interface has to be invented, mockups built from the real page come before the real pages are "
         "built; every visible change is shown to you before and after, in a browser the session drives; demo data is "
         "invented; components never touch; one shared component serves each need, with no hidden duplicate of a "
         "field; nothing the person typed is rewritten in silence; each component is also tried step by step, as a "
         "person would; `id`s are unique and each thing has one name; every state is measured in both themes, light "
         "and dark, against WCAG 2.2 AA (4.5:1 for text, 3:1 for large text, focus rings and state indicators) and "
         "never by eye; touch targets are 44 px on touch devices, beyond the 24 px that AA asks, and 24 px with a "
         "mouse; each touched page is checked at widths of 320, 375, 768, 1024, 1280 and 1440 px and at 200% zoom, "
         "with the keyboard, axe (an accessibility checker) and a spot check by a screen reader on the main path; and "
         "the proof travels with the change: screenshots made by a script, the result of axe and browser tests that "
         "can fail.",
         "Le regole da 1 a 12 e la 22 riguardano fedeltà, misura e accessibilità: decidono il documento del designer "
         "e i mockup approvati, e ogni blocco di lavoro si chiude con una revisione di fedeltà fatta da chi non l'ha "
         "costruito; dove l'interfaccia va inventata, i mockup costruiti dalla pagina reale vengono prima che le "
         "pagine reali siano costruite; ogni cambio visibile ti viene mostrato prima e dopo, in un browser che la "
         "sessione guida; i dati dimostrativi sono inventati; i componenti non si toccano mai; un solo componente "
         "condiviso serve ogni bisogno, senza un duplicato nascosto di un campo; nulla di ciò che la persona ha "
         "digitato viene riscritto in silenzio; ogni componente si prova anche passo per passo, come farebbe una "
         "persona; gli `id` sono unici e ogni cosa ha un solo nome; ogni stato si misura in entrambi i temi, chiaro e "
         "scuro, rispetto a WCAG 2.2 AA (4,5:1 per il testo, 3:1 per il testo grande, gli anelli di focus e gli "
         "indicatori di stato) e mai a occhio; le aree di tocco sono di 44 px sui dispositivi touch, oltre i 24 px "
         "che chiede AA, e di 24 px con il mouse; ogni pagina toccata si controlla a larghezze di 320, 375, 768, "
         "1024, 1280 e 1440 px e allo zoom del 200%, con la tastiera, axe (un verificatore di accessibilità) e una "
         "prova a campione con un lettore di schermo sul percorso principale; e la prova viaggia con il cambio: "
         "screenshot generati da uno script, il risultato di axe e test nel browser che possono fallire."),
        ("Rules 13 to 21 are on taste and restraint: each element earns its place, colour marks only meaning, spacing "
         "and text sizes follow fixed scales, each view has one primary button and destructive actions stay "
         "secondary, words say the outcome, every action answers at once and its message stays until it can be read, "
         "language is plain and help stays in the same place, the dark theme is designed and not inverted, and taste "
         "is counted on each page instead of judged.",
         "Le regole da 13 a 21 riguardano gusto e sobrietà: ogni elemento si guadagna il suo posto, il colore segna "
         "solo un significato, spaziature e dimensioni del testo seguono scale fisse, ogni vista ha un solo pulsante "
         "principale e le azioni distruttive restano secondarie, le parole dicono l'esito, ogni azione ha un "
         "riscontro immediato e il suo messaggio resta finché si può leggere, il linguaggio è semplice e l'aiuto "
         "resta nello stesso posto, il tema scuro è progettato e non invertito, e il gusto si conta su ogni pagina "
         "invece di giudicarlo."),
        ("This paragraph names the main point of each rule; the numbered rules, with what each one measures, are in "
         "`interface-quality`.",
         "Questo paragrafo nomina il punto principale di ogni regola; le regole numerate, con ciò che ciascuna "
         "misura, stanno in `interface-quality`."),
        ("The plugin ships none of the tools these rules use: the browser, the script that makes the screenshots, axe "
         "and the browser tests come from the project.",
         "Il plugin non contiene nessuno degli strumenti che queste regole usano: il browser, lo script che produce "
         "gli screenshot, axe e i test nel browser vengono dal progetto."),
        ("The skills do not say yet where the before/after record lives when the project names none.",
         "Le skill non dicono ancora dove stia il registro del prima e dopo quando il progetto non ne nomina uno."),
        # the four questions of the user lens, answered
        ("The skills say that the project's configuration names its template, in no fixed file, and that with no "
         "template each new component carries its reason in writing.",
         "Le skill dicono che la configurazione del progetto nomina il suo template, senza un file fisso, e che senza "
         "un template ogni componente nuovo porta per iscritto la sua ragione."),
        ("A project with one theme measures the theme it has, and rule 20 on the dark theme applies once it has one.",
         "Un progetto con un solo tema misura il tema che ha, e la regola 20 sul tema scuro vale da quando ne ha uno."),
        ("A change of style, such as one colour in one file, is not a trivial text fix: it takes the round of the UX, "
         "user and review lenses, the measures on the pages it reaches, a score sheet for each interface lens it "
         "touches and a UX study.",
         "Un cambio di stile, come un colore in un file, non è una correzione banale di testo: prende il giro delle "
         "lenti UX, utente e di revisione, le misure sulle pagine che raggiunge, un foglio dei voti per ogni lente "
         "d'interfaccia che tocca e uno studio UX."),
        ("When your configuration names its own agents for these lenses, those agents run them. A skill of your "
         "configuration that covers these lenses is loaded first.",
         "Quando la tua configurazione nomina propri agenti per queste lenti, sono quegli agenti a eseguirle. Una "
         "skill della tua configurazione che copre queste lenti si carica per prima."),
    ),
    "lenses-together": (
        # the name the user looks for, as the first sentence of the paragraph on the round
        ("The round is an adversarial verification: the review lens attacks the proposal on evidence. On a change "
         "to an interface or to the responses of an API,",
         "Il giro è una verifica avversariale: la lente di revisione attacca la proposta sulle prove. Su un cambio "
         "di un'interfaccia o delle risposte di un'API,"),
        # the round measures before it proposes, and the user lens is heard before the UX lens answers
        ("in this order: the PM lens has already framed the work; the UX lens measures what the change touches as it "
         "is (every touched state and its contrast in both themes, at the widths and the zoom of the iron rules, or, "
         "for an API, the routes as they answer today) and then proposes; the review lens attacks; the user lens "
         "walks the main task of the touched pages, or the client's flow for an API, and its findings reach the UX "
         "lens with the attack; the UX lens answers or changes the proposal; and then comes the decision.",
         "in quest'ordine: la lente PM ha già inquadrato il lavoro; la lente UX misura ciò che il cambio tocca così "
         "com'è (ogni stato toccato e il suo contrasto in entrambi i temi, alle larghezze e allo zoom delle regole di "
         "ferro, oppure, per un'API, le rotte come rispondono oggi) e poi propone; la lente di revisione attacca; la "
         "lente utente percorre il compito principale delle pagine toccate, o il flusso del client per un'API, e i "
         "suoi rilievi arrivano alla lente UX insieme all'attacco; la lente UX risponde o cambia la proposta; e poi "
         "viene la decisione."),
        ("An autonomy holds with you present too: the lenses decide what it opens, and nothing it opens is asked of "
         "you.",
         "Un'autonomia vale anche quando ci sei: le lenti decidono ciò che apre, e nulla di ciò che apre ti viene "
         "chiesto."),
        ("in `interface-quality` for the round of the UX, user and review lenses.",
         "in `interface-quality` per il giro delle lenti UX, utente e di revisione."),
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
        ("An autonomy lets the lenses take the decisions it opens, whether you are there or not; each one is "
         "provisional, logged and reported to you first.",
         "Un'autonomia lascia alle lenti le decisioni che apre, che tu ci sia o no; ciascuna è provvisoria, "
         "registrata e riportata a te per prima."),
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
        # the stop of blunt-review: its two exceptions in one sentence, and an order to fix more opens no more
        # rounds than it names
        ("or an answer orders more fixing, which opens only the rounds it names, each run with `round=2`.",
         "o che una risposta ordini altre correzioni, che apre solo i giri che nomina, ciascuno con `round=2`."),
        ("what is still open after the rounds an answer opened goes up again.",
         "ciò che resta aperto dopo i giri aperti da una risposta sale di nuovo."),
    ),
    "explanation": (
        (" of the parts below each end with a line that says what guarantees the part; two have none: the life "
         "cycle in three modes, because it only follows the others, and the note on languages and frameworks, "
         "which only says where good practices come from.",
         " delle parti qui sotto chiudono ciascuna con una riga che dice che cosa garantisce la parte; due non "
         "ce l'hanno: il ciclo di vita in tre modalità, perché non fa che seguire le altre, e la nota sui linguaggi "
         "e sui framework, che dice solo da dove vengono le buone pratiche."),
    ),
    "lifecycle": (
        ("Because the job changes an interface, the UX lens first measures the report page as it is, its states and "
         "their contrast in both themes, at the widths and the zoom of the iron rules; then the UX lens proposes "
         "where the button goes and what its label says, the review lens attacks the proposal on evidence and cost, "
         "the user lens walks the download as a person would and its findings reach the UX lens with the attack, the "
         "UX lens answers, and then the decision is taken, before the spec is written (`interface-quality`).",
         "Poiché il lavoro cambia un'interfaccia, la lente UX misura prima la pagina del rapporto così com'è, i suoi "
         "stati e il loro contrasto in entrambi i temi, alle larghezze e allo zoom delle regole di ferro; poi la lente "
         "UX propone dove va il pulsante e che cosa dice la sua etichetta, la lente di revisione attacca la proposta "
         "su prove e costo, la lente utente percorre lo scaricamento come farebbe una persona e i suoi rilievi "
         "arrivano alla lente UX insieme all'attacco, la lente UX risponde, e poi la decisione si prende, prima che "
         "la spec sia scritta (`interface-quality`)."),
        ("Normal mode is the name for work without an autonomy: you supervise it, and you approve the spec at "
         "gate 2 and the final validation at gate 6.",
         "La modalità normale è il nome del lavoro senza un'autonomia: lo segui tu, e approvi tu la spec al "
         "cancello 2 e la validazione finale al cancello 6."),
        ('You approve in writing; a bare "ok" to a spec nobody read is not approval, and neither is the request you '
         "started with.",
         'Approvi per iscritto; un semplice "ok" a una spec che nessuno ha letto non è un\'approvazione, e non lo è '
         "neppure la richiesta iniziale."),
        ("Each light gate is a quick coherence check, and after the last one the whole list is read once more with "
         "fresh eyes before any code (`development-workflow`).",
         "Ogni cancello leggero è un rapido controllo di coerenza, e dopo l'ultimo si rilegge l'intero elenco una "
         "volta ancora a mente fresca prima di qualunque codice (`development-workflow`)."),
        ("and only then is the box ticked; the message of the task's commit names the failure seen before the code "
         "(`superpowers:test-driven-development`, `engineering-principles`).",
         "e solo allora si spunta la casella; il messaggio del commit del compito nomina il fallimento visto prima "
         "del codice (`superpowers:test-driven-development`, `engineering-principles`)."),
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
        # the user's own scoring skill writes its own log, so the plugin's log is not the only one
        ("When your configuration has its own `quality-scoring`, its log is the one written instead.",
         "Quando la tua configurazione ha un suo `quality-scoring`, si scrive invece il suo registro."),
        ("On a touched page the perimeter is what the change touches and the states it reaches: an old breach elsewhere "
         "on the page is listed as a note and does not count, as for old code.",
         "Su una pagina toccata il perimetro è ciò che il cambio tocca e gli stati che raggiunge: una violazione vecchia "
         "altrove nella pagina si elenca come nota e non conta, come per il codice vecchio."),
        ("which the UX lens scores on the real pages, with screenshots in both themes at the widths and the zoom of the "
         "iron rules, measured contrast and touch targets, and the result of axe.",
         "il cui voto assegna la lente UX sulle pagine reali, con screenshot in entrambi i temi alle larghezze e allo "
         "zoom delle regole di ferro, contrasto e aree di tocco misurati, e il risultato di axe."),
        ("`quality-scoring` names the class of the common breaches of the iron rules: for example a primary action "
         "whose text is below WCAG AA is S1, a widget that silently rewrites what the person typed is S2, and two "
         "components less than 8 px apart are S3; axe violations count by the impact axe gives them, and any failure "
         "of a WCAG criterion of level A or AA is at least S2. Any other breach "
         "takes the class that its meaning gives, by the definitions above, on the lens that `quality-scoring` assigns to it. A breach "
         "found in many places is one finding with every place listed, and when it comes from a shared component "
         "that repeats it across pages, an S3 rises to S2.",
         "`quality-scoring` nomina la classe delle violazioni più comuni delle regole di ferro: per esempio un'azione "
         "principale il cui testo è sotto WCAG AA è S1, un widget che riscrive in silenzio ciò che la persona ha "
         "digitato è S2, e due componenti a meno di 8 px l'uno dall'altro sono S3; le violazioni di axe contano "
         "secondo l'impatto che axe dà loro, e ogni criterio WCAG di livello A o AA non rispettato vale almeno S2. "
         "Ogni altra violazione prende la classe che le dà il suo significato, "
         "secondo le definizioni qui sopra, sulla lente che `quality-scoring` le assegna. Una violazione trovata in molti "
         "posti è un solo rilievo con tutti i posti elencati, e quando viene da un componente condiviso che la ripete "
         "su più pagine, un S3 sale a S2."),
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
        ("When your configuration has its own `quality-scoring`, the main session first re-classes the findings of "
         "the reviewer's report with that rubric, because the reviewer can class only with the table of the plugin.",
         "Quando la tua configurazione ha un suo `quality-scoring`, la sessione principale riclassifica prima i "
         "rilievi del rapporto del revisore con quella rubrica, perché il revisore può classificare solo con la "
         "tabella del plugin."),
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
    "maintainers": (
        ("A second job runs the tests of the parts that run on your machine (the `SessionStart` hook, the "
         "`PreToolUse` hook and the night re-creation script) on macOS and Windows; the Windows runner has Git Bash, "
         "so a Windows machine without it is not exercised. A third job runs ruff 0.12.8",
         "Un secondo job esegue le prove delle parti che girano sulla tua macchina (l'hook `SessionStart`, l'hook "
         "`PreToolUse` e lo script di ricreazione notturna) su macOS e Windows; il runner Windows ha Git Bash, quindi "
         "una macchina Windows senza Git Bash non è esercitata. Un terzo job esegue ruff 0.12.8"),
    ),
    "explain-review": (
        ("the `PreToolUse` hook `hooks/pre_tool_use.py` enforces the rest of the interface where it runs: it denies "
         "any Agent call that launches `pragmatic-engineering:blunt-reviewer` with a prompt outside the grammar, "
         "quoting the grammar in its reason; only inside the reviewer it denies any Bash command other than the "
         "exact git read forms of its definition and any Write outside `.pe/` at the repository root, the Write "
         "path and the repository root compared after resolving symlinks; besides these, it decides only the "
         "file writes (Write, Edit and NotebookEdit) and the Bash commands of a worker, which \"Known limits\" "
         "describes; every other call gets no decision from it.",
         "l'hook `PreToolUse` `hooks/pre_tool_use.py` impone il resto dell'interfaccia dove gira: nega "
         "ogni chiamata Agent che avvia `pragmatic-engineering:blunt-reviewer` con un prompt fuori dalla grammatica, "
         "citando la grammatica nel motivo; solo dentro il revisore nega ogni comando Bash diverso dalle forme "
         "esatte di lettura git della sua definizione e ogni Write fuori da `.pe/` alla radice del repository, con "
         "il percorso del Write e la radice del repository confrontati dopo aver risolto i collegamenti simbolici; "
         "oltre a questi, decide solo le scritture di file (Write, Edit e NotebookEdit) e i comandi Bash di un "
         "worker, che «Limiti noti» descrive; ogni altra chiamata non riceve da lui nessuna decisione."),
        ("A rule for the rest: that a review is made before a merge request is declared, not enforced.",
         "Una regola per il resto: che una revisione si faccia prima di una merge request è dichiarato, non imposto."),
    ),
    "language-neutral": (
        ("and in a live matrix of ten languages (4 November 2026): in it the plugin imposed no Python habit and "
         "installed nothing. Real work in other languages over several days has not been tried yet.",
         "e in una matrice dal vivo di dieci linguaggi (4 novembre 2026): lì il plugin non ha imposto nessuna "
         "abitudine di Python e non ha installato nulla. Il lavoro vero in altri linguaggi su più giorni non è "
         "ancora stato provato."),
    ),
    "limits": (
        ("With `--red`, `verify_delivery.py` runs the command of the project, and so the code of the delivery, in two "
         "temporary worktrees, one of the integration tip and one of the delivery tip, which it removes afterwards, "
         "and it runs `git worktree prune`, which drops the records of every worktree of the repository whose folder "
         "is gone. The command inherits the environment of the session that runs the script, and the script enforces "
         "none of the resources of the brief: the coordinator sets them in the command, through "
         "`env NAME=value <command>` because no shell reads the command, or in the environment. The command is split "
         "with `shlex.split`, so a path in it is written with `/`: a backslash is an escape, and on Windows a path "
         "with backslashes is read wrongly.",
         "Con `--red`, `verify_delivery.py` esegue il comando del progetto, e quindi il codice della consegna, in due "
         "worktree temporanei, uno della punta d'integrazione e uno della punta della consegna, che poi rimuove, ed "
         "esegue `git worktree prune`, che cancella le registrazioni di ogni worktree del repository la cui "
         "cartella non c'è più. Il comando eredita l'ambiente della sessione che esegue lo script, e lo script non "
         "impone nessuna delle risorse del brief: le imposta il coordinatore nel comando, con "
         "`env NOME=valore <comando>` perché nessuna shell legge il comando, o nell'ambiente. Il comando è diviso con "
         "`shlex.split`, quindi un percorso al suo interno si scrive con `/`: la barra rovesciata è un carattere di "
         "escape, e su Windows un percorso con barre rovesciate viene letto male."),
        ("the autonomy (including the rule that the model sets its profile only when you ask)",
         "l'autonomia (compresa la regola per cui il modello ne imposta il profilo solo quando glielo chiedi)"),
        ("does not run when `python3` is missing, when it crashes before reading its input or when it passes its "
         "10-second timeout: the call then goes through, because the hook is registered with "
         "`\"onFailure\": \"continue\"`, and the reviewer and the worker are back to what their definitions "
         "declare. Claude Code reads "
         "`onFailure` from version 2.1.295; on earlier versions a failed hook lets the call through anyway.",
         "non gira quando manca `python3`, quando si interrompe prima di leggere il suo input o quando supera il "
         "timeout di 10 secondi: la chiamata allora passa, perché l'hook è registrato con "
         "`\"onFailure\": \"continue\"`, e il revisore e il worker tornano a ciò che le loro definizioni "
         "dichiarano. Claude Code "
         "legge `onFailure` dalla versione 2.1.295; nelle versioni precedenti un hook fallito lascia comunque "
         "passare la chiamata."),
        ("The check covers the plugin-scoped name `pragmatic-engineering:blunt-reviewer`. Three live runs with Claude "
         "Code 2.1.318 showed the launch denial, the reviewer's own reads and writes left alone, and that Claude Code "
         "does not resolve the bare name `blunt-reviewer` to the plugin agent; in a later live run the hook denied, "
         "inside the reviewer, a `git diff --stat` that its definition does not list, and the review went on with "
         "the forms it lists. It costs about 30 to 33 ms on every Agent call, for every user, and about 45 to 46 ms "
         "on a Write inside the reviewer, which pays one git subprocess. Since the worker boundary the hook also "
         "starts on every Edit and NotebookEdit of every user, and these calls pay that start, about as much as a "
         "Write: the median of 50 runs of the hook on a Write of the main session was about 29 to 31 ms before the "
         "worker boundary and is about 31 to 34 ms with it, and on a Bash call of the main session it was about 30 "
         "to 31 ms before the hook read a worker's commands and is about 29 to 34 ms after, because a session "
         "without workers asks git nothing. The worker agent pays one git subprocess more, to find its root: a "
         "Write of it measured about 45 to 48 ms, and a Bash call about 45 to 48 ms, which includes loading the "
         "shell reader of `lib/pe_guard`; a call that finds `.pe/worker` in its working directory or in a folder "
         "above it pays two, the root and whether git tracks anything under `.pe`, and in a worker session a Write "
         "measured about 57 to 65 ms and a Bash call about 56 to 58 ms. All these costs come from one measurement "
         "session, three rounds of 50 runs each with the versions interleaved, on the maintainer's macOS machine "
         "with a load average of about 7 to 8 from other work.",
         "Il controllo copre il nome con il prefisso del plugin `pragmatic-engineering:blunt-reviewer`. Tre "
         "esecuzioni dal vivo con Claude Code 2.1.318 hanno mostrato il rifiuto al lancio, le letture e scritture "
         "del revisore stesso lasciate passare, e che Claude Code non risolve il nome senza prefisso `blunt-reviewer` "
         "nell'agente del plugin; in un'esecuzione dal vivo successiva l'hook ha rifiutato, dentro il revisore, un "
         "`git diff --stat` che la sua definizione non elenca, e la revisione è andata avanti con le forme che "
         "elenca. Costa circa da 30 a 33 ms a ogni chiamata Agent, per ogni utente, e circa da 45 a 46 ms a un Write "
         "dentro il revisore, che paga un sottoprocesso git. Dal confine del worker l'hook parte anche a ogni Edit e "
         "NotebookEdit di ogni utente, e queste chiamate pagano quella partenza, circa quanto un Write: la mediana "
         "di 50 esecuzioni dell'hook su un Write della sessione principale era di circa 29-31 ms prima del confine "
         "del worker ed è di circa 31-34 ms con esso, e su una chiamata Bash della sessione principale era di circa "
         "30-31 ms prima che l'hook leggesse i comandi di un worker ed è di circa 29-34 ms dopo, perché una "
         "sessione senza worker non chiede nulla a git. L'agente worker paga un sottoprocesso git in più, per "
         "trovare la sua radice: un suo Write ha misurato circa 45-48 ms, e una sua chiamata Bash circa 45-48 ms, "
         "compreso il caricamento del lettore della shell di `lib/pe_guard`; una chiamata che trova `.pe/worker` "
         "nella sua cartella di lavoro o in una cartella sopra di essa ne paga due, la radice e se git traccia "
         "qualcosa sotto `.pe`, e in una sessione worker un Write ha misurato circa 57-65 ms e una chiamata Bash "
         "circa 56-58 ms. Tutti questi costi vengono da una sola sessione di misura, tre giri da 50 esecuzioni "
         "ciascuno con le versioni alternate, sulla macchina macOS del manutentore, con un carico medio di circa 7-8 "
         "dovuto ad altro lavoro."),
        # the worker boundary: what it holds and what is not proven
        ("The worker boundary of the `PreToolUse` hook is proven live only in part. In the live run of 6 November "
         "2026, launched with `claude -p`, with two `worker` sub-agents started with `isolation: worktree`, Claude "
         "Code refused a sub-agent a Write into the checkout of the session that launched it, before the hook; one "
         "path was tried, and why it refused, whether it refuses other paths and whether it does so in an interactive "
         "run were not tried. The Bash part of the boundary ran inside the sub-agents: it denied four times a command "
         "outside its grammar, `env NAME=value <command>`, which it now reads, and its checks of `rm`, `cd` and git "
         "were not reached. For a worker session the boundary is not proven live.",
         "Il confine del worker nell'hook `PreToolUse` è provato dal vivo solo in parte. Nella prova dal vivo del 6 "
         "novembre 2026, lanciata con `claude -p`, con due sotto-agenti `worker` avviati con `isolation: worktree`, "
         "Claude Code ha rifiutato a un sotto-agente un Write nel checkout della sessione che lo aveva lanciato, "
         "prima dell'hook; è stato provato un solo percorso, e non è stato provato perché l'abbia rifiutato, se "
         "rifiuti altri percorsi né se lo faccia in un'esecuzione interattiva. La parte Bash del confine ha girato "
         "dentro i sotto-agenti: ha negato quattro volte un comando fuori dalla sua grammatica, `env NOME=valore "
         "<comando>`, che ora legge, e i suoi controlli su `rm`, `cd` e git non sono stati raggiunti. Per una "
         "sessione worker il confine non è provato dal vivo."),
        ("It denies the agent `pragmatic-engineering:worker` a Write, Edit or NotebookEdit outside the repository root "
         "of the call's working directory, and does the same to a session whose root carries the signal `.pe/worker`, "
         "an empty file that the coordinating session writes into the worktree of a worker session before it sends the brief; the agents that "
         "such a session launches in its worktree are held too.",
         "Nega all'agente `pragmatic-engineering:worker` un Write, un Edit o un NotebookEdit fuori dalla radice del "
         "repository della cartella di lavoro della chiamata, e fa lo stesso con una sessione la cui radice porta il "
         "segnale `.pe/worker`, un file vuoto che la sessione che coordina scrive nel worktree di una sessione worker prima di mandare il brief; "
         "anche gli agenti che una tale sessione lancia nel suo worktree sono vincolati."),
        ("The first turn of a worker session, which only reports that it is online, runs before the signal is written.",
         "Il primo turno di una sessione worker, che si limita a segnalare di essere online, gira prima che il "
         "segnale sia scritto."),
        ("The signal holds only when `.pe` is a real folder, not a symlink, and git tracks nothing under `.pe` in "
         "any letter case, so a repository that commits any file there, or a `.pe` symlink, never holds a session; "
         "an untracked `.pe/worker` that something else writes holds the sessions opened in that repository just "
         "the same.",
         "Il segnale vincola solo quando `.pe` è una cartella vera, non un collegamento simbolico, e git non traccia "
         "nulla sotto `.pe` in nessuna combinazione di maiuscole e minuscole, quindi un repository che fa il commit "
         "di un file qualsiasi lì dentro, o di un collegamento simbolico `.pe`, non vincola mai una sessione; un "
         "`.pe/worker` non tracciato scritto da qualcos'altro vincola allo stesso modo le sessioni aperte in quel "
         "repository."),
        ("For a subagent started with `isolation: worktree`, which `cwd` Claude Code puts in the hook's input is not "
         "verified: if it is the checkout of the session that launched the worker, the hook holds the worker to that "
         "checkout and not to its own worktree.",
         "Per un sotto-agente avviato con `isolation: worktree` non è verificato quale `cwd` Claude Code metta "
         "nell'input dell'hook: se è il checkout della sessione che ha lanciato il worker, l'hook vincola il worker a "
         "quel checkout e non al suo worktree."),
        ("When the coordinating session cannot write the signal, for example because the classifier of auto mode "
         "refuses a write outside its own worktree, that worker session is not held.",
         "Quando la sessione che coordina non riesce a scrivere il segnale, per esempio perché il classificatore della "
         "modalità auto rifiuta una scrittura fuori dal suo worktree, quella sessione worker non è vincolata."),
        ("A session whose repository root is neither its working directory nor a folder above it, as with "
         "`core.worktree` or `GIT_WORK_TREE`, is never held, even with the signal, because the hook looks for "
         "`.pe/worker` only in those folders before it asks git.",
         "Una sessione la cui radice del repository non è né la sua cartella di lavoro né una cartella sopra di essa, "
         "come con `core.worktree` o `GIT_WORK_TREE`, non è mai vincolata, nemmeno con il segnale, perché l'hook "
         "cerca `.pe/worker` solo in quelle cartelle prima di chiedere a git."),
        ("A failure of the hook denies a call of the worker agent, but lets a call of a worker session through, "
         "because such a session is known only from its signal.",
         "Un guasto dell'hook nega una chiamata dell'agente worker, ma lascia passare una chiamata di una sessione "
         "worker, perché una tale sessione si riconosce solo dal suo segnale."),
        # the Bash part of the worker boundary: the grammar it accepts, what it denies, what stays open
        ("The Bash part of the worker boundary reads the text of a command, not what the shell runs.",
         "La parte Bash del confine del worker legge il testo di un comando, non ciò che la shell esegue."),
        ("For the same calls as the file writes, the hook accepts a command only in a plain grammar: words of plain "
         "characters, text in single quotes, and text in double quotes without `$`, backtick or backslash; the "
         "operators `&&`, `||`, `;`, `|` and newlines; and the redirections `>`, `>>`, `<` and `2>`, each with one "
         "target written out, and `2>&1`.",
         "Per le stesse chiamate delle scritture di file, l'hook accetta un comando solo in una grammatica semplice: "
         "parole di caratteri semplici, testo fra apici singoli e testo fra apici doppi senza `$`, apice inverso o "
         "barra rovesciata; gli operatori `&&`, `||`, `;`, `|` e gli a capo; e le redirezioni `>`, `>>`, `<` e `2>`, "
         "ciascuna con un bersaglio scritto per esteso, e `2>&1`."),
        ("It denies any other command as a whole, and its reason says what to write instead: a heredoc, a comment, "
         "`$`, a backtick, `$( ... )`, `<( ... )`, `>|`, an `&` that is not part of `2>&1`, a backslash, a number "
         "glued to `<` or `>` (`1>`), a word that starts with `=`, which zsh turns into the path of a command, a "
         "command word that is not a plain name with a plain path before it (a NAME=value or NAME+=value, a glob, a "
         "`~`, zsh's `-`), `export`, `declare`, `typeset`, `readonly`, `local`, `alias`, `hash`, `enable`, `float`, "
         "`integer`, `set`, `shopt`, `setopt`, `unsetopt`, `emulate`, `disable`, `zmodload`, `eval` and `trap`, which "
         "run their words as shell text, a reserved word of bash or zsh such as `if`, `for`, `time` or `repeat` (`[` "
         "and `[[` pass, because they run no command of their own), zsh's `noglob` and `nocorrect`, and an option of a "
         "wrapper that it does not know, such as `-iu`, `env -C`, `env -S`, `sudo -D` or `sudo -e`; for this reason "
         "the worker commits with `git commit -F` and a message file.",
         "Nega per intero ogni altro comando, e il suo motivo dice che cosa scrivere al suo posto: un heredoc, un "
         "commento, `$`, un apice inverso, `$( ... )`, `<( ... )`, `>|`, una `&` che non fa parte di `2>&1`, una barra "
         "rovesciata, un numero attaccato a `<` o a `>` (`1>`), una parola che comincia con `=`, che zsh trasforma nel "
         "percorso di un comando, una parola di comando che non è un nome semplice con davanti un percorso semplice "
         "(un NAME=value o un NAME+=value, un carattere jolly, una `~`, il `-` di zsh), `export`, `declare`, "
         "`typeset`, `readonly`, `local`, `alias`, `hash`, `enable`, `float`, `integer`, `set`, `shopt`, `setopt`, "
         "`unsetopt`, `emulate`, `disable`, `zmodload`, `eval` e `trap`, che eseguono le loro parole come testo di "
         "shell, una parola riservata di bash o di zsh come `if`, `for`, `time` o `repeat` (`[` e `[[` passano, perché "
         "non eseguono un comando proprio), `noglob` e `nocorrect` di zsh, e un'opzione di un involucro che non "
         "conosce, come `-iu`, `env -C`, `env -S`, `sudo -D` o `sudo -e`; per questo il worker fa i commit con `git "
         "commit -F` e un file del messaggio."),
        ("In that grammar it reads each statement by its command word, by the name after its last `/` in lower case, "
         "because a case-insensitive file system runs `RM` as `rm`, and through `env`, `command`, `sudo`, `builtin`, "
         "`exec` and `nohup`, leaving out the redirections and their targets.",
         "In quella grammatica legge ciascuna istruzione dalla sua parola di comando, dal nome dopo la sua ultima "
         "`/` in minuscolo, perché un file system che non distingue maiuscole e minuscole esegue `RM` come `rm`, e "
         "attraverso `env`, `command`, `sudo`, `builtin`, `exec` e `nohup`, lasciando fuori le redirezioni e i loro "
         "bersagli."),
        ("Right after `env`, before any option of it, it reads `NAME=value` words, each NAME a plain name and each "
         "value made of letters, digits and `. _ / : @ , + % -`, or text in single quotes, as the variables that "
         "`env` sets for the command after "
         "them, which it reads as any other; this is the form for the resources of a brief, `env NAME=value "
         "<command>`.",
         "Subito dopo `env`, prima di ogni sua opzione, legge le parole `NOME=valore`, ciascun NOME un nome semplice "
         "e ciascun valore fatto di lettere, cifre e `. _ / : @ , + % -`, o testo fra apici singoli, come le "
         "variabili che `env` imposta per il "
         "comando che le segue, che legge come ogni altro; è la forma per le risorse di un brief, `env NOME=valore "
         "<comando>`."),
        ("`env -i <command>` and `env -u NAME <command>` pass too, but after an option of `env` a `NAME=value` word "
         "is denied.",
         "Passano anche `env -i <comando>` e `env -u NOME <comando>`, ma dopo un'opzione di `env` una parola "
         "`NOME=valore` è negata."),
        ("It denies `rm`, `rmdir`, `unlink` and `find ... -delete` on a path that does not lie below the worktree "
         "root, so the root itself is denied too, or that the shell would still expand, because it starts with `~` or "
         "holds a glob (`*`, `?`, `[`), and a `find ... -delete` with `-files0-from`, which reads its start paths from "
         "a file; a `cd`, zsh's `chdir` or a `pushd` to anything but one folder inside the worktree, spelled out in "
         "the same way, not `-`, `+N` or `-N`, and of the worktree's own repository, not of a submodule or a nested "
         "worktree, because the shell keeps that folder for the next call and from there the hook would no longer find "
         "the worktree, and a `popd` with any word; a git command with a glob in any of its words, which the shell "
         "could turn into another subcommand or option, a git command that `-C`, `--git-dir` or `--work-tree` points "
         "outside the worktree, or that carries a configuration of its own (`-c`, `--config-env`, or a variable that "
         "`env` sets for it); and, because all "
         "the worktrees share what they change, `git stash`, `git worktree remove` and `prune`, `git push`, `git "
         "update-ref`, a `git config` that does more than read, a `git branch` or `git tag` that deletes, moves or "
         "forces one, and a `git fetch` or `git pull` with a `:` in any of its words, operand or option value "
         "(`--refmap=a:b`), which is how a refspec names a destination, so a remote written as a URL is denied too.",
         "Nega `rm`, `rmdir`, `unlink` e `find ... -delete` su un percorso che non sta sotto la radice del worktree, "
         "quindi anche sulla radice stessa, o che la shell espanderebbe ancora, perché comincia con `~` o contiene un "
         "carattere jolly (`*`, `?`, `[`), e un `find ... -delete` con `-files0-from`, che legge da un file i suoi "
         "percorsi di partenza; un `cd`, il `chdir` di zsh o un `pushd` verso qualunque cosa che non sia una sola "
         "cartella dentro il worktree, scritta per esteso allo stesso modo, che non sia `-`, `+N` o `-N` e che sia del "
         "repository stesso del worktree, non di un submodule o di un worktree annidato, perché la shell tiene quella "
         "cartella per la chiamata dopo e da lì l'hook non troverebbe più il worktree, e un `popd` con una parola "
         "qualsiasi; un comando git con un carattere jolly in una qualsiasi delle sue parole, che la shell potrebbe "
         "trasformare in un altro sottocomando o in un'altra opzione, un comando git che `-C`, `--git-dir` o "
         "`--work-tree` puntano fuori dal worktree, o che porta una configurazione propria (`-c`, `--config-env`, o "
         "una variabile che `env` gli imposta); e, "
         "perché tutti i worktree condividono ciò che cambiano, `git stash`, `git worktree remove` e `prune`, `git "
         "push`, `git update-ref`, un `git config` che non si limita a leggere, un `git branch` o un `git tag` che "
         "cancella, sposta o forza un ramo o un tag, e un `git fetch` o un `git pull` con un `:` in una qualsiasi "
         "delle sue parole, operando o valore di un'opzione (`--refmap=a:b`), che è il modo in cui un refspec nomina "
         "una destinazione, quindi è negato anche un remoto scritto come URL."),
        ("Every path is read from the call's working directory, which is why a `cd`, `chdir`, `pushd` or `popd` passes "
         "only alone, as the whole command (a statement made only of redirections does not count), and `cd docs; cd "
         "..` is denied too. The options of a command are read as getopt reads them: they end at `--` or at the first "
         "word that is not an option, and every word after is a path that is checked; of `find`, the word after each "
         "`-f` is checked as a path as well.",
         "Ogni percorso si legge dalla cartella di lavoro della chiamata, ed è per questo che un `cd`, un `chdir`, un "
         "`pushd` o un `popd` passa solo da solo, come intero comando (un'istruzione fatta solo di redirezioni non "
         "conta), e anche `cd docs; cd ..` è negato. Le opzioni di un comando si leggono come le legge getopt: "
         "finiscono a `--` o alla prima parola che non è un'opzione, e ogni parola dopo è un percorso che viene "
         "controllato; di `find`, anche la parola dopo ogni `-f` è controllata come percorso."),
        ("Everything else stays open, because the check reads only those nine command words, and of git only the "
         "options before the subcommand and those nine subcommands: any other command that writes or deletes, such as "
         "`mv`, `cp`, `ln`, `tee`, `python3` or `make`; any other git subcommand that changes what the worktrees "
         "share, such as `git switch -C` and `git checkout -B`, which the worker's own resumption uses, `git worktree "
         "add` and `move`, `git symbolic-ref`, `git reflog` and `git remote`; a command that another program runs, "
         "such as `sh -c`, `bash -c`, `source`, `xargs`, `find -exec`, `nice`, `timeout` or a script; a builtin that "
         "reads a word as arithmetic, and so runs a `$( ... )` written in single quotes inside it, such as `let`, `[[ "
         "... -eq ... ]]`, `[ ... -eq ... ]`, `unset`, `shift`, `exit`, `printf -v` and `read`, in bash and in zsh; a "
         "command word that an alias or a function defined before the call stands for; a variable that `env` sets "
         "for a command other than git, such as `PATH`, which chooses the program that a command word runs; a "
         "variable or a shell option "
         "set before the call, such as `CDPATH` for `cd`, `GIT_DIR` for git, or zsh's `extended_glob` and "
         "`cdable_vars` from the shell configuration; and the targets of redirections. Inside its worktree a worker "
         "can still delete `.pe/worker`, and so turn off the hold of its own session.",
         "Tutto il resto resta aperto, perché il controllo legge solo quelle nove parole di comando, e di git solo le "
         "opzioni prima del sottocomando e quei nove sottocomandi: ogni altro comando che scrive o cancella, come "
         "`mv`, `cp`, `ln`, `tee`, `python3` o `make`; ogni altro sottocomando di git che cambia ciò che i worktree "
         "condividono, come `git switch -C` e `git checkout -B`, che la ripresa del worker stesso usa, `git worktree "
         "add` e `move`, `git symbolic-ref`, `git reflog` e `git remote`; un comando che un altro programma esegue, "
         "come `sh -c`, `bash -c`, `source`, `xargs`, `find -exec`, `nice`, `timeout` o uno script; un comando interno "
         "della shell che legge una parola come aritmetica, e così esegue un `$( ... )` scritto fra apici singoli al "
         "suo interno, come `let`, `[[ ... -eq ... ]]`, `[ ... -eq ... ]`, `unset`, `shift`, `exit`, `printf -v` e "
         "`read`, in bash e in zsh; una parola di comando al posto della quale sta un alias o una funzione definiti "
         "prima della chiamata; una variabile che `env` imposta per un comando diverso da git, come `PATH`, che "
         "sceglie il programma che una parola di comando esegue; una variabile o un'opzione della shell impostate "
         "prima della chiamata, come `CDPATH` "
         "per `cd`, `GIT_DIR` per git, o `extended_glob` e `cdable_vars` di zsh dalla configurazione della shell; e i "
         "bersagli delle redirezioni. Dentro il suo worktree un worker può ancora cancellare `.pe/worker`, e spegnere "
         "così il vincolo della propria sessione."),
        ("(<https://code.claude.com/docs/en/sub-agents#what-loads-at-startup>). Claude Code documents another "
         "route, a `SubagentStart` hook that adds the rules as context, and the plugin does not take it: it would "
         "add about 9,500 characters to each of the most frequent subagents.",
         "(<https://code.claude.com/docs/en/sub-agents#what-loads-at-startup>). Claude Code documenta un'altra "
         "strada, un hook `SubagentStart` che aggiunge le regole come contesto, e il plugin non la prende: "
         "aggiungerebbe circa 9.500 caratteri a ciascuno dei sotto-agenti più frequenti."),
        ("this has not been tried here "
         "(<https://code.claude.com/docs/en/plugins/loading#hooks-when-two-enabled-plugins-share-a-name>).",
         "qui non è stato provato "
         "(<https://code.claude.com/docs/en/plugins/loading#hooks-when-two-enabled-plugins-share-a-name>)."),
        ("The plugin was tried live on macOS only; the CI runs the whole suite on Linux and the user-machine tests "
         "on macOS and Windows.",
         "Il plugin è stato provato dal vivo solo su macOS; la CI esegue tutta la suite su Linux e le prove delle "
         "parti che girano sulla tua macchina su macOS e Windows."),
        ("Claude Code gives the skill listing 1% of the model's context window. When a large environment overflows "
         "it, Claude Code drops descriptions starting with the least-invoked skills, and in a run with 129 skills "
         "the skills of this plugin were listed without a description. Claude Code documents these levers: "
         "`skillListingBudgetFraction`, the variable `SLASH_COMMAND_TOOL_CHAR_BUDGET`, "
         "`disable-model-invocation: true` on skills you rarely need, and `/skill-doctor`; `skillOverrides` does not "
         "apply to plugin skills (<https://code.claude.com/docs/en/skills#skill-descriptions-are-cut-short>).",
         "Claude Code assegna all'elenco delle skill l'1% della finestra di contesto del modello. Quando un ambiente "
         "grande lo supera, Claude Code toglie le descrizioni cominciando dalle skill meno invocate, e in "
         "un'esecuzione con 129 skill le skill di questo plugin sono state elencate senza descrizione. Le leve che "
         "Claude Code documenta sono `skillListingBudgetFraction`, la variabile `SLASH_COMMAND_TOOL_CHAR_BUDGET`, "
         "`disable-model-invocation: true` sulle skill che ti servono di rado e `/skill-doctor`; `skillOverrides` "
         "non vale per le skill dei plugin "
         "(<https://code.claude.com/docs/en/skills#skill-descriptions-are-cut-short>)."),
        ("A run without a person (`claude -p`) should pin `--model`: on some machines its default is a smaller "
         "model whose skill listing loses the descriptions, and the end-to-end test pins `--model opus`.",
         "Un'esecuzione senza una persona (`claude -p`) dovrebbe fissare `--model`: su alcune macchine il suo "
         "modello predefinito è uno più piccolo, il cui elenco delle skill perde le descrizioni, e la prova da "
         "capo a fondo fissa `--model opus`."),
        ("Imports in the user-scope `~/.claude/CLAUDE.md` load without the approval dialog, except in Cowork; an "
         "import outside the project written in a project file needs that dialog, and in a run without a person it "
         "was refused (<https://code.claude.com/docs/en/memory#import-additional-files>).",
         "Gli import nel `~/.claude/CLAUDE.md` di ambito utente si caricano senza la finestra di approvazione, "
         "tranne in Cowork; un import fuori dal progetto scritto in un file del progetto richiede quella finestra, "
         "e in un'esecuzione senza una persona è stato rifiutato "
         "(<https://code.claude.com/docs/en/memory#import-additional-files>)."),
        ("In a live run of 4 November 2026 the main session did not load your own `quality-scoring` at the final "
         "validation although the rule says to (the outcome of the gate was right, because both rubrics gave the same "
         "classes); in one of 5 November 2026 it loaded the plugin's first and then yours. The measuring step of the "
         "round (`interface-quality`, step 1) runs only when the main session loads `interface-quality`: on 5 November "
         "2026 it did in one live run of three, with the step's earlier text, and covered the six widths and the zoom "
         "from the markup, named the rendering it could not see, and said nothing about a second theme, which that "
         "page does not have; in the other two the UX lens checked 320 px and the contrast at rest from the markup and "
         "the single theme was named, with no other width, no zoom, no other state and no `Not verified:` line. On 6 "
         "November 2026, in three live runs of the same scenario with the plugin installed, whose rules then also asked "
         "the round to measure first (a clause removed because these runs did not show it), the main session loaded "
         "`interface-quality` in one, with the current text: its brief asked the UX lens to measure first, and the "
         "lens did, with a `Not verified:` line naming the widths, the zoom and the hover and focus states it could "
         "not see. In the other two the brief asked the UX lens to propose: when `interface-quality` is not loaded, "
         "nothing in the plugin makes the main session ask for the measure first.",
         "In un'esecuzione dal vivo del 4 novembre 2026 la sessione principale non ha caricato il tuo "
         "`quality-scoring` alla validazione finale, benché la regola lo dica (l'esito del cancello era giusto, perché "
         "le due rubriche davano le stesse classi); in una del 5 novembre 2026 ha caricato prima quello del plugin e "
         "poi il tuo. Il passo di misura del giro (`interface-quality`, passo 1) gira solo quando la sessione "
         "principale carica `interface-quality`: il 5 novembre 2026 è successo in un'esecuzione dal vivo su tre, con "
         "il testo precedente, e il passo ha coperto le sei larghezze e lo zoom dal markup, ha nominato il rendering "
         "che non poteva vedere, e non ha detto nulla di un secondo tema, che quella pagina non ha; nelle altre due la "
         "lente UX ha controllato 320 px e il contrasto a riposo dal markup e l'unico tema è stato nominato, senza "
         "altre larghezze, senza zoom, senza altri stati e senza la riga `Not verified:`. Il 6 novembre 2026, in tre "
         "esecuzioni dal vivo dello stesso scenario con il plugin installato, le cui regole chiedevano allora anche che il "
         "giro misurasse prima (una clausola tolta perché queste esecuzioni non l'hanno mostrata), la sessione "
         "principale ha caricato "
         "`interface-quality` in una, con il testo attuale: il suo ordine ha chiesto alla lente UX di misurare prima, "
         "e la lente lo ha fatto, con una riga `Not verified:` che nomina le larghezze, lo zoom e gli stati di hover e "
         "focus che non poteva vedere. Nelle altre due l'ordine chiedeva alla lente UX di proporre: quando "
         "`interface-quality` non è caricata, nel plugin niente fa chiedere alla sessione principale di misurare "
         "prima."),
        ("The reviewer checks the failure that the commit message names against the diff, which shows that the "
         "claim is consistent with the change, not that the test was really seen failing before the code.",
         "Il revisore controlla sul diff il fallimento che il messaggio del commit nomina, il che mostra che "
         "l'affermazione è coerente con la modifica, non che la prova sia stata davvero vista fallire prima del "
         "codice."),
        ("In a run without a person, a refused `git config` read leaves the office hours and the autonomy profile "
         "unset, and nothing says so.",
         "In un'esecuzione senza una persona, una lettura di `git config` rifiutata lascia non impostati l'orario "
         "d'ufficio e il profilo di autonomia, e nulla lo dice."),
        ("The `SessionStart` hook checks `~/.claude/CLAUDE.md` even when `CLAUDE_CONFIG_DIR` is set: the "
         "documentation says that variable moves settings, session history and plugins, and does not say where "
         "Claude Code then reads `CLAUDE.md` (<https://code.claude.com/docs/en/env-vars>).",
         "L'hook `SessionStart` controlla `~/.claude/CLAUDE.md` anche quando `CLAUDE_CONFIG_DIR` è impostata: la "
         "documentazione dice che quella variabile sposta le impostazioni, la cronologia delle sessioni e i "
         "plugin, e non dice dove Claude Code legga allora `CLAUDE.md` "
         "(<https://code.claude.com/docs/en/env-vars>)."),
    ),
    "reference": (
        ("in the worktree of a `worker` also `delivery.md` (its delivery file) and, in that of a worker session, "
         "`worker` (the signal that holds the session to its worktree, written by the coordinating session), and",
         "nel worktree di un `worker` anche `delivery.md` (il suo file di consegna) e, in quello di una sessione "
         "worker, `worker` (il segnale che vincola la sessione al suo worktree, scritto dalla sessione che "
         "coordina), e"),
        ("There are no commands in this version and, besides the `SessionStart` and `PreToolUse` hooks described "
         "below, only two scripts: `skills/safe-operations/recreate_night_commits.py`, which `safe-operations` tells "
         "the model to run, and `skills/team-lead/verify_delivery.py`, which `team-lead` tells the model to run.",
         "In questa versione non ci sono comandi e, oltre agli hook `SessionStart` e `PreToolUse` descritti sotto, "
         "ci sono due soli script: `skills/safe-operations/recreate_night_commits.py`, che `safe-operations` dice al "
         "modello di eseguire, e `skills/team-lead/verify_delivery.py`, che `team-lead` dice al modello di "
         "eseguire."),
        ("`skills/team-lead/verify_delivery.py` checks the delivery of a worker against git and exits 0 when it is "
         "accepted, 1 when it is refused, 2 on a usage error and 3 when it holds something the reviewer has not read. To "
         "run it by hand: `python3 <the folder of team-lead>/verify_delivery.py --integration <branch> --branch "
         "<branch> --tip <sha> --worktree <folder> --brief <file> [--reviewed <sha>] [--red <command>]`, from the "
         "checkout of the repository.",
         "`skills/team-lead/verify_delivery.py` controlla con git la consegna di un worker ed esce con 0 se è "
         "accettata, con 1 se è rifiutata, con 2 per un errore d'uso e con 3 quando contiene qualcosa che il revisore "
         "non ha letto. Per eseguirlo a mano: `python3 <la cartella di team-lead>/verify_delivery.py "
         "--integration <ramo> --branch <ramo> --tip <sha> --worktree <cartella> --brief <file> [--reviewed <sha>] "
         "[--red <comando>]`, dal checkout del repository."),
        ("`PreToolUse`, registered in `hooks/hooks.json` with the matcher `Agent|Bash|Write|Edit|NotebookEdit` as "
         "`python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/pre_tool_use.py\"`, with a timeout of 10 seconds and "
         "`\"onFailure\": \"continue\"`.",
         "`PreToolUse`, registrato in `hooks/hooks.json` con il matcher `Agent|Bash|Write|Edit|NotebookEdit` come "
         "`python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/pre_tool_use.py\"`, con un timeout di 10 secondi e "
         "`\"onFailure\": \"continue\"`."),
        ("the file writes of a worker outside its worktree, every Bash command of a worker outside the plain grammar "
         "that Known limits describes, and, in that grammar, a statement whose `rm`, `rmdir`, `unlink` or `find "
         "-delete` reaches outside the worktree, a `cd`, `chdir` or `pushd` to anything but one folder inside the "
         "worktree and of its own repository, a `popd` with any word, any of those four that is not the whole command, "
         "a git command that points outside the worktree, holds a glob or carries a configuration of its own (`-c`, "
         "`--config-env`, or a variable that `env` sets for it), and a git command that changes what all the "
         "worktrees share, each with its reason; Known "
         "limits lists what it does not read.",
         "fuori dalla sua definizione, le scritture di file di un worker fuori dal suo worktree, ogni comando Bash di "
         "un worker fuori dalla grammatica semplice che i limiti noti descrivono e, dentro quella grammatica, "
         "un'istruzione il cui `rm`, `rmdir`, `unlink` o `find -delete` esce dal worktree, un `cd`, un `chdir` o un "
         "`pushd` verso qualunque cosa che non sia una sola cartella dentro il worktree e del suo stesso repository, "
         "un `popd` con una parola qualsiasi, ciascuno di quei quattro che non sia l'intero comando, un comando git "
         "che punta fuori dal worktree, contiene un carattere jolly o porta una configurazione propria (`-c`, "
         "`--config-env`, o una variabile che `env` gli imposta), e un comando git che cambia ciò che tutti i "
         "worktree condividono, ciascuna con il suo "
         "motivo; i limiti noti elencano ciò che non legge."),
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
        EXCLUDE_SENTENCES,
    ),
    "explain-parallel": (EXCLUDE_SENTENCES,),
    # the one file every worker edits has no first owner, as in the entry conditions of team-lead
    "parallel": (
        ("The task file, which every worker edits, is the exception: each ticks only its own boxes there, and a "
         "conflict on it is the worker's to resolve, like any other.",
         "Il file dei compiti, che ogni worker modifica, è l'eccezione: ciascuno spunta lì solo le proprie caselle, "
         "e un conflitto su di esso lo risolve il worker, come ogni altro."),
    ),
}


@pytest.mark.parametrize("section", sorted(GUIDED_SENTENCES))
def test_readmes_state_the_guided_configuration_in_both_languages(section):
    for text, language in zip(pages(section), (0, 1)):
        assert [pair[language] for pair in GUIDED_SENTENCES[section] if pair[language] not in text] == []


# The words the limits sentence uses for the sizes of the hook's tables, in English and in Italian.
COUNT_WORDS = {
    7: ("seven", "sette"), 8: ("eight", "otto"), 9: ("nine", "nove"), 10: ("ten", "dieci"), 11: ("eleven", "undici"),
}


def test_readmes_count_the_explained_parts_that_end_with_a_guarantee_line():
    """The count follows EXPLAINED_POINTS, so a new explained point cannot leave 'Ten' standing."""
    sentences = ("%s of the parts below each end", "%s delle parti qui sotto chiudono")
    for intro, words, sentence in zip(pages("explanation"), COUNT_WORDS[len(EXPLAINED_POINTS)], sentences):
        assert sentence % words.capitalize() in intro


def test_readmes_count_the_command_words_and_git_subcommands_of_the_worker_check():
    """The counts in prose follow _COMMAND_CHECKS and _SHARED_STATE, so a new row of either cannot leave them stale."""
    commands = COUNT_WORDS[len(pre_tool_use._COMMAND_CHECKS)]
    subcommands = COUNT_WORDS[len(pre_tool_use._SHARED_STATE)]
    english, italian = pages("limits")
    assert "only those %s command words" % commands[0] in english
    assert "and those %s subcommands" % subcommands[0] in english
    assert "solo quelle %s parole di comando" % commands[1] in italian
    assert "e quei %s sottocomandi" % subcommands[1] in italian


# What the live run of team-lead on 6 November 2026 proved, in the status line, in the explanation of parallel
# work and in its guarantee line.
EN_STATUS = (
    "Not proven yet: an install on a clean machine, real work over several days and the parallel work of `team-lead` "
    "on a real project and with session workers, which so far has had one live run on a small test repository, with "
    "two sub-agent workers, on 6 November 2026."
)
IT_STATUS = (
    "Non ancora provato: l'installazione su una macchina pulita, il lavoro vero di più giorni e il lavoro in "
    "parallelo di `team-lead` su un progetto vero e con worker in sessione, che finora ha avuto un'esecuzione dal "
    "vivo su un piccolo repository di prova, con due worker sotto-agenti, il 6 novembre 2026."
)
EN_PARALLEL = (
    "Parallel work is not proven on a real project nor with session workers: it has had one live run on a small test "
    "repository, with two sub-agent workers, on 6 November 2026; see [Known limits](#known-limits)."
)
IT_PARALLEL = (
    "Il lavoro in parallelo non è provato su un progetto vero né con worker in sessione: ha avuto un'esecuzione dal "
    "vivo su un piccolo repository di prova, con due worker sotto-agenti, il 6 novembre 2026; vedi [Limiti "
    "noti](#limiti-noti)."
)
EN_GUARANTEE = (
    "(the `PreToolUse` hook, proven live only in part, in one run with two sub-agent workers on a small test "
    "repository on 6 November 2026, and not with session workers: see [Known limits](#known-limits))"
)
IT_GUARANTEE = (
    "(l'hook `PreToolUse`, provato dal vivo solo in parte, in un'esecuzione con due worker sotto-agenti su un "
    "piccolo repository di prova il 6 novembre 2026, e non con worker in sessione: vedi [Limiti noti](#limiti-noti))"
)


def test_readmes_date_the_live_regression_runs_and_drop_the_claims_they_made_false():
    status = ("Proven so far: the unit and structure tests, one live run of the end-to-end test of the rules import "
              "(29 October 2026), and the live regression runs against an existing setup of 4 November 2026: nine "
              "scenarios, each with and without the plugin, with a matrix of ten languages. " + EN_STATUS,
              "Provato finora: le prove di unità e di struttura, un'esecuzione dal vivo della prova da capo a fondo "
              "dell'import delle regole (29 ottobre 2026) e le esecuzioni dal vivo di regressione contro una "
              "configurazione esistente del 4 novembre 2026: nove scenari, ciascuno con e senza il plugin, con una "
              "matrice di dieci linguaggi. " + IT_STATUS)
    stale = (
        "the live regression scenarios against an existing setup", "a run in languages other than Python",
        "are declared, not enforced", "the runs on other languages are still to come", "tried on macOS only",
        "gli scenari dal vivo contro le regressioni", "l'uso in linguaggi diversi da Python",
        "sono dichiarati, non imposti", "le prove su altri linguaggi devono ancora arrivare",
        "provato solo su macOS", "dichiarati nell'agente, non imposti",
    )
    stale += ("Parallel work is not proven live", "hook, not proven live)", "in a live run.",
              "Il lavoro in parallelo non è provato dal vivo", "non provato dal vivo)", "in una prova dal vivo.")
    claims = ((EN_PARALLEL, EN_GUARANTEE), (IT_PARALLEL, IT_GUARANTEE))
    for path, text, claim, more in zip((README, README_IT), pages(), status, claims):
        missing = [sentence for sentence in (claim,) + more if sentence not in text]
        assert missing == [] and [old for old in stale if old in text] == [], path.name


def test_readmes_count_a_repeated_breach_once_and_name_wcag_2_2():
    for path, text in zip((README, README_IT), pages()):
        stale = ("S3 each", "S3 ciascuno", "WCAG AA measured", "WCAG AA misurato")
        assert [old for old in stale if old in text] == [], path.name


def test_readmes_measure_at_the_widths_of_the_iron_rules_not_at_the_three_old_ones():
    for path, text in zip((README, README_IT), pages()):
        assert [old for old in ("375, 768 and 1280", "375, 768 e 1280") if old in text] == [], path.name


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


def test_readmes_explain_that_the_coordinator_never_resolves_a_conflict():
    """The point on parallel work names the integration, the merge read and the script, and the rule on conflicts."""
    sentences = ("the coordinator never resolves a conflict", "il coordinatore non risolve mai un conflitto")
    for explanation, sentence in zip(pages("explain-parallel"), sentences):
        for needed in ("--ff-only", "--remerge-diff", "`verify_delivery.py`", sentence):
            assert needed in explanation, needed


def test_readmes_integrate_the_commit_id_the_check_accepted_and_the_guide_answers_the_developer():
    """The worker can move its branch after the check, so the merge takes the accepted id; the guide says what a
    developer who follows it needs: the test environment, the base he gets, what he sees when it stalls."""
    integrate = ("the commit id that the run after the PASS accepted, never the branch name",
                 "l'id di commit che l'esecuzione dopo il PASS ha accettato, mai il nome del ramo")
    guide = (
        ("its own database, port and cache index", "nothing is asked of you", "more than 10 minutes", "terminal",
         "stays yours", "(#known-limits)", "not proven on a real project"),
        ("il suo database, la sua porta e il suo indice di cache", "non ti viene chiesto nulla", "più di 10 minuti",
         "terminale", "resta tuo", "(#limiti-noti)", "non è provato su un progetto vero"),
    )
    for explanation, text, sentence, needed in zip(pages("explain-parallel"), pages("parallel"), integrate, guide):
        assert sentence in explanation
        assert [phrase for phrase in needed if phrase not in text] == []


def test_readmes_class_the_delivery_check_as_a_rule_for_the_model_and_say_when_the_brief_goes_out():
    """verify_delivery.py runs only when the model runs it, as the night script does: only the hook is a mechanism."""
    classed = ("a rule for the model", "una regola per il modello")
    mechanism = ("a mechanism for one thing, the hold of a worker", "un meccanismo per una cosa, il vincolo di un worker")
    check = ("is a check that the model is told to run", "è un controllo che il modello deve lanciare")
    sent = ("sends the brief only after", "manda il brief solo dopo")
    unmeasured = ("not measured", "non misurati")
    for guide, explanation, label, rule, after, caps, first, how in zip(
        pages("parallel"), pages("explain-parallel"), GUARANTEE_LABELS, classed, sent, unmeasured, mechanism, check
    ):
        line = guarantee_line(explanation, label)
        assert "`team-lead`" in line and "`PreToolUse`" in line
        assert first in line and how in line
        assert line.index(first) < line.lower().index(rule), "the mechanism comes first, then the rule for the rest"
        assert after in explanation and caps in guide


def test_readmes_place_the_parallel_guide_after_autonomy_and_the_final_team_lead_row():
    for text in pages():
        ids = list(marked_blocks(text))
        assert ids[ids.index("autonomy") + 1] == "parallel"
        row = next(line for line in marked_blocks(text)["reference"].splitlines() if line.startswith("| `team-lead` |"))
        assert "`worker`" in row and "`blunt-reviewer`" in row


def test_readmes_say_the_coordinator_ships_with_team_lead_and_only_the_guard_is_later():
    wording = (
        "The merge-request guard comes in a later version.",
        "La guardia sulle merge request arriva in una versione successiva.",
    )
    gone = ("multi-agent coordinator", "coordinatore a più agenti")
    for text, sentence, old in zip(pages(), wording, gone):
        status = text.split("<!-- section:")[0]
        assert sentence in status
        assert old not in status


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
    # CPython 3.9 has no 26.04 build; the job for macOS and Windows takes its runner from its matrix
    assert re.findall(r"runs-on: (\S+)", text) == ["ubuntu-24.04", "${{", "ubuntu-24.04"]
    assert re.findall(r"uses: (\S+)", text) == ["actions/checkout@v7", "actions/setup-python@v7"] * 3
    assert text.count("persist-credentials: false") == 3  # one per checkout; no step pushes


# The tests of what runs on the user's machine: the two hooks of the plugin and the two scripts of the skills.
USER_MACHINE_TESTS = (
    "tests/test_session_start.py tests/test_pre_tool_use.py tests/test_recreate_night_commits.py "
    "tests/test_pe_worktree.py tests/test_verify_delivery.py"
)


def ci_job(name: str) -> str:
    """The lines of one job of the workflow: those indented under its name."""
    jobs = CI_WORKFLOW.read_text(encoding="utf-8").split("\njobs:\n", 1)[1]
    match = re.search(r"^  %s:\n((?:    .*\n|\n)*)" % re.escape(name), jobs, re.MULTILINE)
    assert match, name
    return match.group(1)


def test_ci_runs_the_tests_of_what_runs_on_the_users_machine_on_macos_and_windows():
    job = ci_job("user-machine")
    assert "runs-on: ${{ matrix.os }}" in job and "os: [macos-latest, windows-latest]" in job
    assert "fail-fast: false" in job and 'python-version: "3.x"' in job
    assert 'python -m pip install "pytest>=7"' in job and "python -m pytest -q %s" % USER_MACHINE_TESTS in job
    assert "Git Bash" in job  # the comment that says which Windows case is not exercised
    assert all((REPO_ROOT / name).is_file() for name in USER_MACHINE_TESTS.split())


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


def direct_git_calls(source: str) -> List[int]:
    """The lines of a ``subprocess.<anything>(["git", ...])`` call: git started by the file itself."""
    lines = []
    for node in ast.walk(ast.parse(source)):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess" and node.args):
            continue
        command = node.args[0]
        if isinstance(command, (ast.List, ast.Tuple)) and command.elts:
            first = command.elts[0]
            if isinstance(first, ast.Constant) and first.value == "git":
                lines.append(node.lineno)
    return lines


def test_the_guard_against_a_direct_git_call_sees_one():
    fake = "import subprocess\n\ndef f():\n    return subprocess.run(['git', 'status'], capture_output=True)\n"
    assert direct_git_calls(fake) == [4]
    assert direct_git_calls("import subprocess\nsubprocess.run(['python3', 'x'])\nrun_git('status')\n") == []


def test_only_lib_pe_git_starts_git_in_lib_and_the_skill_scripts():
    """The runner pins ``--no-replace-objects``: a script that starts git itself reads what ``git replace`` says."""
    files = sorted(path for folder in ("lib", "skills") for path in (REPO_ROOT / folder).rglob("*.py"))
    assert REPO_ROOT / "lib" / "pe_git.py" in files
    offenders = {
        str(path.relative_to(REPO_ROOT)): direct_git_calls(path.read_text(encoding="utf-8"))
        for path in files if path.name != "pe_git.py" or path.parent.name != "lib"
    }
    assert {name: lines for name, lines in offenders.items() if lines} == {}
