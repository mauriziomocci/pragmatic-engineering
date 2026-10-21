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
)
AGENTS: Tuple[str, ...] = ("blunt-reviewer",)
SUPERPOWERS_TESTED_VERSION = "6.4.1"
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
FUTURE_COMPONENTS: Tuple[str, ...] = (
    "team-lead", "memory-hygiene", "pe-guard", "review-start", "review-show",
    "mr-opened", "PE-REVIEW", "PE-REVIEW-RESULT",
)

_BACKTICKED = re.compile(r"`([^`\n]+)`")
_NAMESPACED = re.compile(r"\b(superpowers|pragmatic-engineering):([a-z0-9][a-z0-9-]*)")
_SPECKIT = re.compile(r"\bspeckit-[a-z]+\b")
_SKILL_LIKE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+")


def sections(text: str, level: int = 2) -> Dict[str, str]:
    """Map each heading of ``level`` to the text under it; fenced code is not scanned for headings."""
    result: Dict[str, str] = {}
    current: Optional[str] = None
    lines: List[str] = []
    in_fence = False
    for line in text.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
        elif not in_fence and line.startswith("#"):
            hashes = len(line) - len(line.lstrip("#"))
            if hashes <= level and line[hashes:hashes + 1] == " ":
                if current is not None:
                    result[current] = "\n".join(lines)
                current = line[hashes + 1:].strip() if hashes == level else None
                lines = []
                continue
        if current is not None:
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


def unknown_references(text: str) -> List[str]:
    """Problems with the skills, agents and commands that ``text`` cites; empty when all is well."""
    problems: List[str] = []
    local = set(A1_SKILLS) | set(AGENTS)
    for namespace, name in _NAMESPACED.findall(text):
        known = SUPERPOWERS_SKILLS if namespace == "superpowers" else local
        if name not in known:
            problems.append("%s:%s does not exist" % (namespace, name))
    for name in _SPECKIT.findall(text):
        if name not in SPECKIT_COMMANDS:
            problems.append("%s is not a spec-kit %s command" % (name, SPECKIT_TESTED_VERSION))
    for token in _BACKTICKED.findall(text):
        if not _SKILL_LIKE.fullmatch(token) or token in local or token in SPECKIT_COMMANDS:
            continue
        if token in SUPERPOWERS_SKILLS:
            problems.append("`%s` must be written superpowers:%s" % (token, token))
            continue
        near = sorted(k for k in local | SUPERPOWERS_SKILLS if _distance(token, k) <= 2)
        if near:
            problems.append("`%s` looks like a misspelt %s" % (token, near[0]))
    for name in FUTURE_COMPONENTS:
        if re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(name), text):
            problems.append("%s does not exist in this version" % name)
    return problems


def installed_superpowers() -> Optional[Path]:
    """Install path of superpowers from Claude Code's plugin registry, if installed."""
    registry = Path.home() / ".claude" / "plugins" / "installed_plugins.json"
    try:
        data = json.loads(registry.read_text(encoding="utf-8"))
        return Path(data["plugins"]["superpowers@claude-plugins-official"][0]["installPath"])
    except (OSError, ValueError, KeyError, IndexError, TypeError):
        return None
