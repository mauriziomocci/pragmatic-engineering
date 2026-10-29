"""Helpers shared by the test suite: synthetic git repositories, script runs and content checks."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Tuple, Union

REPO_ROOT = Path(__file__).resolve().parent.parent


def git(repo: Path, *args: str) -> str:
    """Run git in ``repo`` and return stdout; fail the test on a non-zero exit."""
    proc = subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True)
    if proc.returncode != 0:
        raise AssertionError("git %s failed: %s" % (" ".join(args), proc.stderr))
    return proc.stdout


def init_repo(path: Path) -> Path:
    """Create an empty repository whose default branch is main."""
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    return path


def commit(repo: Path, files: Dict[str, Union[str, bytes]], message: str) -> str:
    """Write ``files`` (text or bytes), commit everything and return the new sha."""
    for name, content in files.items():
        target = repo / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", message)
    return git(repo, "rev-parse", "HEAD").strip()


def run_script(
    script: Path,
    args: List[str],
    cwd: Path,
    stdin: str = "",
    env: Optional[Dict[str, str]] = None,
) -> subprocess.CompletedProcess:
    """Run a repository script with the current interpreter, as a hook would."""
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(cwd),
        input=stdin,
        capture_output=True,
        text=True,
        env=full_env,
        timeout=120,
    )


A1_SKILLS: Tuple[str, ...] = (
    "engineering-principles",
    "evidence-based-investigation",
    "blunt-review",
    "adversarial-review-panel",
    "development-workflow",
    "spec-driven-layout",
    "autonomous-execution",
    "teach",
    "continuity-note",
    "safe-operations",
    "quality-scoring",
    "interface-quality",
)
AGENTS: Tuple[str, ...] = ("blunt-reviewer",)
SUPERPOWERS_TESTED_VERSION = "7.0.0"
SUPERPOWERS_SKILLS: FrozenSet[str] = frozenset((
    "brainstorming", "diagnosing-superpowers", "dispatching-parallel-agents", "executing-plans",
    "finishing-a-development-branch", "receiving-code-review", "requesting-code-review",
    "subagent-driven-development", "systematic-debugging", "test-driven-development",
    "using-git-worktrees", "using-superpowers", "verification-before-completion",
    "writing-plans", "writing-skills",
))
SPECKIT_TESTED_VERSION = "0.8.9"
SPECKIT_COMMANDS: FrozenSet[str] = frozenset((
    "speckit-specify", "speckit-clarify", "speckit-plan", "speckit-tasks", "speckit-implement",
    "speckit-analyze", "speckit-checklist", "speckit-constitution",
))
# Tools a skill names that are installed apart from this plugin and from superpowers.
EXTERNAL_NAMES: FrozenSet[str] = frozenset(("mcp-code-review",))
FUTURE_COMPONENTS: Tuple[str, ...] = (
    "team-lead", "memory-hygiene", "pe-guard", "review-start", "review-show",
    "mr-opened", "PE-REVIEW", "PE-REVIEW-RESULT",
)

_BACKTICKED = re.compile(r"`([^`\n]+)`")
_NAMESPACED = re.compile(r"\b(superpowers|pragmatic-engineering):([a-z0-9][a-z0-9-]*)")
_SPECKIT = re.compile(r"\bspeckit-[a-z]+\b")
_SKILL_LIKE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+")


def sections(text: str, level: int = 2) -> Dict[str, str]:
    """Map each heading of ``level`` to the text under it; fenced code is not scanned for headings.

    A heading that appears twice raises ValueError: the second copy would silently hide the first.
    """
    result: Dict[str, str] = {}
    current: Optional[str] = None
    lines: List[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
        hashes = len(line) - len(line.lstrip("#"))
        if not in_fence and 0 < hashes <= level and line[hashes:hashes + 1] == " ":
            if current is not None:
                result[current] = "\n".join(lines)
            current = line[hashes + 1:].strip() if hashes == level else None
            if current in result:
                raise ValueError("heading %r appears twice" % current)
            lines = []
        elif current is not None:
            lines.append(line)
    if current is not None:
        result[current] = "\n".join(lines)
    return result


def _distance(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, char_a in enumerate(a, 1):
        current = [i]
        for j, char_b in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (char_a != char_b)))
        previous = current
    return previous[-1]


def _backticked_problems(text: str, strict: bool) -> List[str]:
    """Problems with the backticked names of ``text``; see ``unknown_references`` for ``strict``."""
    problems: List[str] = []
    local = set(A1_SKILLS) | set(AGENTS)
    for token in _BACKTICKED.findall(text):
        if token in SUPERPOWERS_SKILLS:
            problems.append("`%s` must be written superpowers:%s" % (token, token))
        elif _SKILL_LIKE.fullmatch(token) and token not in (local | SPECKIT_COMMANDS):
            near = sorted(k for k in local | SUPERPOWERS_SKILLS if _distance(token, k) <= 2)
            if near:
                problems.append("`%s` looks like a misspelt %s" % (token, near[0]))
            elif strict and token not in EXTERNAL_NAMES:
                problems.append("`%s` is not a skill, agent or spec-kit command of this plugin" % token)
    return problems


def unknown_references(text: str, strict: bool = False) -> List[str]:
    """Problems with the skills, agents and commands that ``text`` cites; empty when all is well.

    Not strict, a backticked hyphenated word is flagged only when it is within edit distance 2
    of a real name. Strict flags every one that is not a component: for a skill, which cites
    its siblings by bare name, so any other hyphenated backticked word is a broken reference.
    """
    problems: List[str] = []
    local = set(A1_SKILLS) | set(AGENTS)
    for namespace, name in _NAMESPACED.findall(text):
        known = SUPERPOWERS_SKILLS if namespace == "superpowers" else local
        if name not in known:
            problems.append("%s:%s does not exist" % (namespace, name))
    for name in _SPECKIT.findall(text):
        if name not in SPECKIT_COMMANDS:
            problems.append("%s is not a spec-kit %s command" % (name, SPECKIT_TESTED_VERSION))
    problems.extend(_backticked_problems(text, strict))
    for name in FUTURE_COMPONENTS:
        if re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(name), text):
            problems.append("%s does not exist in this version" % name)
    return problems


def installed_superpowers() -> Optional[Path]:
    """Install path of the user-scope superpowers in Claude Code's plugin registry, if installed.

    No registry, or no superpowers entry in it, means "not installed". A registry that cannot
    be read as JSON raises instead: a skipped test must never hide a broken registry.
    """
    registry = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
    try:
        entries = json.loads(registry.read_text(encoding="utf-8"))["plugins"]["superpowers@claude-plugins-official"]
    except (FileNotFoundError, KeyError):
        return None
    return next((Path(entry["installPath"]) for entry in entries if entry["scope"] == "user"), None)


def parse_frontmatter(text: str) -> Tuple[Dict[str, str], str]:
    """Split a '---' frontmatter made of single-line 'key: value' pairs from the body."""
    lines = text.splitlines()
    if not lines or lines[0] != "---" or "---" not in lines[1:]:
        raise AssertionError("missing or unterminated frontmatter")
    end = lines.index("---", 1)
    fields: Dict[str, str] = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(": ")
        if not sep:
            raise AssertionError("frontmatter line is not 'key: value': %r" % line)
        fields[key.strip()] = value.strip()
    return fields, "\n".join(lines[end + 1:])


def yaml_plain_safe(value: str) -> bool:
    """True when ``value`` carries no YAML indicator that changes its meaning as a plain scalar.

    It does not look at the type: "true" and "123" pass, and read as a boolean and a number.
    A trailing colon and any tab are rejected because YAML takes them for a mapping key or for
    separation space.
    """
    if not value or value != value.strip():
        return False
    if value[0] in "[]{}>|*&!%@#`'\",?:-" or value[-1] == ":" or "\t" in value:
        return False
    return ": " not in value and " #" not in value
