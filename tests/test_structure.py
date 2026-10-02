"""Structure checks on the repository itself."""
import subprocess
from pathlib import Path
from typing import List

import privacy_check
from support import REPO_ROOT


def repository_files() -> List[Path]:
    """Tracked files plus untracked files that git does not ignore."""
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=str(REPO_ROOT), capture_output=True, check=True,
    ).stdout
    return [REPO_ROOT / name for name in out.decode("utf-8").split("\0") if name]


def test_repository_files_carry_no_generic_privacy_pattern():
    offenders = []
    for path in repository_files():
        if not path.is_file():
            continue
        data = path.read_bytes()
        if b"\0" in data[:8000]:
            continue
        names = privacy_check.find_generic(data.decode("utf-8", "replace"))
        if names:
            offenders.append("%s: %s" % (path.relative_to(REPO_ROOT), ", ".join(names)))
    assert offenders == []
