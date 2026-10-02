"""Structure checks on the repository itself."""
import subprocess
import unicodedata
from pathlib import Path
from typing import List, Tuple

import privacy_check
from support import REPO_ROOT


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


def test_repository_files_carry_no_invisible_characters():
    """A byte-order mark, a zero-width or a bidirectional control character hides text.

    They are Unicode format characters (category Cf); a test that needs one
    writes it as an escape sequence instead of the raw character.
    """
    offenders = []
    for name, text in repository_texts():
        for number, line in enumerate(text.splitlines(), 1):
            for char in line:
                if unicodedata.category(char) == "Cf":
                    offenders.append("%s:%d: U+%04X" % (name, number, ord(char)))
    assert offenders == []
