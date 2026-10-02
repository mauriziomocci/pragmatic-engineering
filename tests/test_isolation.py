"""The suite must not depend on the git configuration of whoever runs it."""
import os
import subprocess
import sys

from support import REPO_ROOT


def test_the_user_xdg_git_config_does_not_leak_into_the_suite(tmp_path):
    """Git reads ``$XDG_CONFIG_HOME/git/ignore`` even when GIT_CONFIG_GLOBAL is set.

    A user who ignores ``*.bin`` there would make a test that commits a binary
    file commit nothing. The nested run stands for that user: it starts with
    such a file and must still pass, because the autouse fixture isolates it.
    """
    xdg = tmp_path / "xdg"
    (xdg / "git").mkdir(parents=True)
    (xdg / "git" / "ignore").write_text("*.bin\n", encoding="utf-8")
    env = dict(os.environ)
    env["XDG_CONFIG_HOME"] = str(xdg)
    proc = subprocess.run(
        [
            sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
            "tests/test_privacy_check.py", "-k", "binary_files_are_skipped",
        ],
        cwd=str(REPO_ROOT), env=env, capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
