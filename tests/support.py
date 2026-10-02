"""Helpers shared by the test suite: synthetic git repositories and script runs."""
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Union

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
