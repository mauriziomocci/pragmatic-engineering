#!/usr/bin/env python3
"""Install the privacy pre-push hook in the maintainer's clone of this repository.

The installer copies the privacy check, the project hook and the shared
filters (tools/privacy_check.py, tools/dev_guard.py, lib/pe_guard/) into
<git common dir>/pragmatic-engineering/step-zero, a folder of its own
inside the guard's data folder, outside the working tree and protected by
the same filters as the rest of that folder, and writes a pre-push hook
that runs that copy; the project hook in the local settings runs the same
copy. Refreshing the copy touches only that folder. A branch without the
tools therefore cannot stop every tool, and an edit to the working tree
changes nothing until the installer runs again. Linked worktrees share the
copy and the hook. The installer refuses to overwrite a pre-push hook it
did not write (a symlink counts as one), and refuses when core.hooksPath
is set, even to an empty value, because git would then ignore the hook.
It is a tool of this repository, not part of the plugin.
"""
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

SOURCE_ROOT = Path(__file__).resolve().parent.parent
# python3 -I drops the script's own folder from sys.path, so both folders are added by hand
sys.path.insert(0, str(SOURCE_ROOT / "lib"))
sys.path.insert(0, str(SOURCE_ROOT / "tools"))

from pe_guard.filters import GUARD_DATA_DIR  # noqa: E402
import privacy_check  # noqa: E402

HOOK_MARKER = "pragmatic-engineering privacy pre-push"
COPY_SUBDIR = GUARD_DATA_DIR + "/step-zero"  # relative to the git common dir
COPIED: Tuple[str, ...] = ("tools/privacy_check.py", "tools/dev_guard.py", "lib/pe_guard")


class InstallError(Exception):
    """The hook cannot be installed safely; the message says what the user can do."""


def render_hook() -> str:
    return (
        "#!/bin/sh\n"
        "# %s\n"
        "# Written by tools/install_dev_hooks.py: every push runs the installed copy of the privacy check.\n"
        "common=$(git rev-parse --git-common-dir) || exit 1\n"
        'exec python3 "$common/%s/tools/privacy_check.py" pre-push "$@"\n'
    ) % (HOOK_MARKER, COPY_SUBDIR)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=str(repo), capture_output=True, text=True)


def _git_path(repo: Path, *args: str) -> Path:
    proc = _git(repo, "rev-parse", *args)
    if proc.returncode != 0:
        raise InstallError("not a git repository: %s" % repo)
    path = Path(proc.stdout.strip())
    return path if path.is_absolute() else repo / path


def copy_dir(repo: Path) -> Path:
    """Folder of the installed copy, under the git directory that every worktree shares."""
    return _git_path(repo, "--git-common-dir") / COPY_SUBDIR


def _remove_tree(path: Path) -> None:
    if path.exists():
        shutil.rmtree(str(path))


def refresh_copy(repo: Path) -> Path:
    """Replace the installed copy with the checks of the tree this installer comes from.

    The new copy is built aside and swapped in by two renames, not by
    deleting the old one first: while no copy exists every watched tool is
    blocked, so that window is kept to the time between the two renames.
    """
    target = copy_dir(repo)
    staging = target.with_name(target.name + ".new")
    previous = target.with_name(target.name + ".old")
    _remove_tree(staging)
    for relative in COPIED:
        source, destination = SOURCE_ROOT / relative, staging / relative
        if source.is_dir():
            shutil.copytree(str(source), str(destination), ignore=shutil.ignore_patterns("__pycache__"))
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(source), str(destination))
    _remove_tree(previous)
    if target.exists():
        target.rename(previous)
    staging.rename(target)
    _remove_tree(previous)
    return target


def _refuse_custom_hooks_path(repo: Path) -> None:
    """Raise InstallError when git would not look for hooks where this installer writes them.

    Only exit status 1 means "not set". An empty value exits 0 with no output and
    makes git run no hook, and a git that cannot answer must not be read as "not set".
    """
    proc = _git(repo, "config", "--show-origin", "--show-scope", "--get", "core.hooksPath")
    if proc.returncode == 1:
        return
    if proc.returncode != 0:
        raise InstallError(
            "cannot read core.hooksPath (git config exited %d): %s"
            % (proc.returncode, proc.stderr.strip())
        )
    scope, origin, _value = proc.stdout.split("\t", 2)
    kind, _, name = origin.partition(":")
    if kind == "file":
        # The origin names the file that holds the value, an included one too, so
        # --file always edits the right place; --global would miss an included file.
        source = str(repo / name)  # git prints the clone's own config relative to its top
        advice = (
            "the user can remove it from their own terminal with: "
            "git config --file %s --unset core.hooksPath" % shlex.quote(source)
        )
    else:
        source = kind  # "command line": no file to edit
        advice = "remove it where it is defined"
    raise InstallError(
        "core.hooksPath is set in the %s configuration (%s), so git would ignore this hook; %s"
        % (scope, source, advice)
    )


def _is_foreign_hook(hook: Path) -> bool:
    """True when ``hook`` exists and this installer did not write it.

    A symlink is foreign even when its target carries the marker, and even when
    the target is missing: writing would go through the link, outside the git directory.
    """
    if hook.is_symlink():
        return True
    return hook.exists() and HOOK_MARKER not in hook.read_text(encoding="utf-8", errors="replace")


def install(repo: Path) -> Path:
    """Refresh the copy, write the hook into the clone's hooks directory and make it executable."""
    _refuse_custom_hooks_path(repo)
    hooks_dir = _git_path(repo, "--git-path", "hooks")
    hook = hooks_dir / "pre-push"
    if _is_foreign_hook(hook):
        raise InstallError(
            "a pre-push hook that this installer did not write already exists at %s; move it away, "
            "or chain it by hand into a hook that does not keep the line '%s', because the "
            "installer overwrites any file that carries it" % (hook, HOOK_MARKER)
        )
    refresh_copy(repo)
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook.write_text(render_hook(), encoding="utf-8")
    hook.chmod(0o755)
    return hook


def main(argv: Optional[List[str]] = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    start = Path(args[0]) if args else Path.cwd()
    try:
        top = privacy_check.repository_root(start)
        hook = install(top)
    except (InstallError, privacy_check.GitError, OSError) as exc:
        print("install_dev_hooks: %s" % exc, file=sys.stderr)
        return 1
    print("installed %s" % hook)
    print("copied the checks to %s" % copy_dir(top))
    return 0


if __name__ == "__main__":
    sys.exit(main())
