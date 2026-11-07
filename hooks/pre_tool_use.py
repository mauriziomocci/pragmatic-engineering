#!/usr/bin/env python3
"""PreToolUse hook of the pragmatic-engineering plugin: blunt-reviewer's closed interface and the worker's worktree.

1. It denies an Agent call to pragmatic-engineering:blunt-reviewer whose
   prompt is not exactly one line of the agent's closed grammar
   (agents/blunt-reviewer.md, "The prompt you accept"), so whoever launches
   the reviewer cannot steer it through the prompt; the reason quotes the
   grammar, so the main session can relaunch with the right line.
2. Inside that agent (agent_type), it denies every Bash command that is not
   one of the git read forms of "How you read", written exactly as there,
   and every Write outside <toplevel>/.pe/, both paths compared after
   os.path.realpath so that a committed .pe symlink cannot lead out.
   --remerge-diff redoes each merge, so a merge driver defined in a git
   configuration (merge.<name>.driver) runs during that read.
3. It denies a Write, Edit or NotebookEdit of pragmatic-engineering:worker
   (agent_type) whose path lies outside <toplevel> of the call's cwd, the
   worker's own worktree, both paths compared after os.path.realpath; with
   no <toplevel> it denies them all. The same file calls of any other session
   or agent are held the same way when that <toplevel> carries the signal
   .pe/worker, its .pe is a real folder and not a symlink, and git tracks
   nothing under .pe in any letter case: the coordinator writes the signal
   into the worktree of a worker session, so the agents such a session
   launches there are held too, while a repository that tracks any file
   under .pe, or a .pe symlink, never holds a session.
   The worker agent pays one git subprocess to find <toplevel>, and a call
   that finds .pe/worker in its cwd or a folder above it pays two, the root
   and whether git tracks anything under .pe; any other call of these tools
   looks only for that file, without git, so a setup whose <toplevel> is not
   one of those folders (core.worktree, GIT_WORK_TREE) is never held.
4. For the same calls it reads each statement of a Bash command with
   read_statements of lib/pe_guard/filters.py, which accepts only a small
   grammar that it reads for sure and raises UnreadableCommand on anything
   else; the hook then denies the command with the reader's advice, because
   a check by command word would let through whatever its reader misreads.
   Every path is read from the call's cwd, so it denies a cd, chdir, pushd or
   popd (_FOLDER_CHECKS) in a command with any other statement (one made only
   of redirections is none): it would move the shell away from cwd for the
   statements after it, while the shell keeps the new folder for the next call,
   which is read from there. Alone, it denies a cd, chdir or pushd to anything
   but one folder at or below <toplevel>, with no leading ~ or glob, not -, +N
   or -N, and whose own repository root is <toplevel>, because the hold of the
   next call is found from it; and a popd with any word. It denies rm, rmdir,
   unlink and find -delete, whose start paths include the word after each -f,
   on a path that is not below <toplevel> or that the shell would still expand
   (a leading ~, a glob), and a find -delete with -files0-from; a git command
   with a glob in any word, which the shell could turn into another subcommand
   or option, or that -C, --git-dir or --work-tree points outside <toplevel>,
   or that carries a configuration of its own (-c, --config-env, or a variable
   that env NAME=value sets for it); and the git commands that change what all
   the worktrees share, in _SHARED_STATE, among them a fetch or a pull with a :
   in any word. The operands are read as getopt reads them: the options end at
   -- or at the first word that is not one, and every word after is an operand.
   The reader refuses eval and trap, which run their words as shell text, and
   reads the command after env's NAME=value words as any other. Any other
   command word, and any other git subcommand, gets no decision: the READMEs
   list under "Known limits" what stays open. lib/pe_guard is imported only for
   a worker's command, so a broken module fails no other call.

The reviewer's checks match closed shapes only: anything a pattern does not
describe is denied, so a gap in a pattern can only make the reviewer stricter.
Every other call, of the main session or of any other agent, gets no decision
and goes through the normal permission flow.

Exit 2 denies, with the reason on stderr, as tools/dev_guard.py does; exit 0
with no output is no decision. A malformed input is no decision. A failure
after the input is read denies when the call concerns the reviewer or comes
from the worker agent, and is no decision otherwise, so a bug here can never
block another tool; a worker session is known only from its signal, so a
failure on its call is no decision. The hook is registered with "onFailure":
"continue": a hook that cannot start or times out lets the call through, and
the limits of the reviewer and of the worker are then declared only.
"""
import importlib
import itertools
import json
import os
import posixpath
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, Tuple

if TYPE_CHECKING:  # the reader is imported only for a worker's command, see _shell_reader
    from pe_guard.filters import ShellStatement

REVIEWER = "pragmatic-engineering:blunt-reviewer"
WORKER = "pragmatic-engineering:worker"
PE_FOLDER = ".pe"
WORKER_SIGNAL = PE_FOLDER + "/worker"
GRAMMAR = "<base>..<tip> [round=1|2] [full=<path>,...]"
# A sha, HEAD, HEAD~n or a branch name: it starts with a letter or digit, so git never reads it as an option,
# and a dot is always followed by a name character, so ".." and "..." cannot hide inside it.
_REVISION = r"[A-Za-z0-9](?:\.?[A-Za-z0-9/_-])*(?:~[0-9]+)?"
# A repository-relative path: segments joined by "/", none empty, "." or "..", so it cannot be absolute or climb out.
_SEGMENT = r"(?!\.\.?(?![A-Za-z0-9._+-]))[A-Za-z0-9._+-]+"
_PATH = r"%s(?:/%s)*" % (_SEGMENT, _SEGMENT)
_RANGE = r"%s\.\.%s" % (_REVISION, _REVISION)
_PROMPT = re.compile(r"%s(?: round=[12])?(?: full=%s(?:,%s)*)?" % (_RANGE, _PATH, _PATH))
# The read-only git commands of agents/blunt-reviewer.md, one per call: no pipe, redirect or other shell syntax fits.
_PATCH_FLAGS = "--no-color --no-ext-diff --no-textconv --no-relative --ignore-submodules=none"
_READ_FORMS = re.compile("(?:%s)" % "|".join((
    r"git rev-parse --show-toplevel",
    r'git rev-parse --verify "%s\^\{commit\}"' % _REVISION,
    r"git merge-base --is-ancestor %s %s" % (_REVISION, _REVISION),
    r"git log --no-color --oneline(?: --merges)? %s" % _RANGE,
    r"git show %s(?: --stat --patch)? %s(?: -- %s)?" % (_PATCH_FLAGS, _REVISION, _PATH),
    r"git show %s --remerge-diff %s(?: -- %s)?" % (_PATCH_FLAGS, _REVISION, _PATH),
    r"git diff %s %s(?: -- %s)?" % (_PATCH_FLAGS, _RANGE, _PATH),
    r"git show %s %s:%s" % (_PATCH_FLAGS, _REVISION, _PATH),
)))
_PROMPT_REASON = (
    "blunt-reviewer accepts exactly one line in its closed grammar, `%s`, and nothing else: revisions are shas, HEAD, "
    "HEAD~n or branch names (letters, digits, / . _ -), and full= takes repository-relative paths separated by "
    "commas, without spaces; relaunch it with only that line" % GRAMMAR
)
_COMMAND_REASON = (
    "blunt-reviewer runs only the read-only git commands of its definition (agents/blunt-reviewer.md, \"How you "
    "read\"), written exactly as there, one per call, with no pipe, redirect or other shell syntax"
)
_WRITE_REASON = "blunt-reviewer writes only under .pe/ at the repository root (git rev-parse --show-toplevel)"
_WORKER_WRITE_REASON = (
    "a worker writes files only inside its own worktree, the repository root of its working directory (git "
    "rev-parse --show-toplevel); a file outside it is not the worker's: name it in the delivery file instead"
)
# Write and Edit name their file file_path, NotebookEdit notebook_path; every one of them present is checked.
_FILE_PATH_KEYS = ("file_path", "notebook_path")
GIT_TIMEOUT = 5.0  # seconds; the hook's own timeout in hooks/hooks.json is longer


def _launches_reviewer(payload: Any) -> bool:
    if not isinstance(payload, dict) or payload.get("tool_name") != "Agent":
        return False
    tool_input = payload.get("tool_input")
    return isinstance(tool_input, dict) and tool_input.get("subagent_type") == REVIEWER


def _prompt_problem(prompt: Any) -> Optional[str]:
    if isinstance(prompt, str) and _PROMPT.fullmatch(prompt):
        return None
    return _PROMPT_REASON


def _runs_in_reviewer(payload: Any) -> bool:
    return isinstance(payload, dict) and payload.get("agent_type") == REVIEWER


def _runs_in_worker(payload: Any) -> bool:
    return isinstance(payload, dict) and payload.get("agent_type") == WORKER


def _command_problem(tool_input: Dict[str, Any], cwd: Any) -> Optional[str]:
    command = tool_input.get("command")
    if isinstance(command, str) and _READ_FORMS.fullmatch(command):
        return None
    return _COMMAND_REASON


def _git(cwd: str, *args: str) -> Optional[subprocess.CompletedProcess]:
    """Run git in ``cwd`` and return what it did, or None when git cannot start or hangs."""
    try:
        return subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=GIT_TIMEOUT)
    except (OSError, subprocess.SubprocessError):  # no git, or git hangs
        return None


def _toplevel(cwd: Any) -> Optional[str]:
    """The repository root of ``cwd`` with every symlink resolved, or None when git finds none."""
    proc = _git(cwd, "rev-parse", "--show-toplevel") if isinstance(cwd, str) and cwd else None
    top = proc.stdout.strip() if proc and proc.returncode == 0 else ""
    return os.path.realpath(top) if top else None


def _inside(root: str, cwd: str, path: str) -> bool:
    """Whether ``path``, read from ``cwd`` with every symlink resolved, lies below ``root``, taken as it is.

    ``root`` is not resolved here: the reviewer's ``.pe`` must stay unresolved, or a committed ``.pe`` symlink
    would carry the allowed folder out of the repository together with the path.
    """
    return Path(root) in Path(os.path.realpath(os.path.join(cwd, path))).parents


def _write_problem(tool_input: Dict[str, Any], cwd: Any) -> Optional[str]:
    path = tool_input.get("file_path")
    top = _toplevel(cwd)
    if isinstance(path, str) and path and top and _inside(os.path.join(top, PE_FOLDER), cwd, path):
        return None
    return _WRITE_REASON


# The reviewer's tools that the hook is registered for; its others (Read, Grep, Glob) only read.
_REVIEWER_TOOL_CHECKS: Dict[str, Callable[[Dict[str, Any], Any], Optional[str]]] = {
    "Bash": _command_problem,
    "Write": _write_problem,
}


def _signal_above(cwd: Any) -> bool:
    """Whether ``cwd`` or a folder above it, symlinks resolved, holds the worker signal; found without git."""
    if not (isinstance(cwd, str) and cwd):
        return False
    folder = Path(os.path.realpath(cwd))
    return any((parent / WORKER_SIGNAL).exists() for parent in (folder, *folder.parents))


def _signalled_root(cwd: Any) -> Optional[str]:
    """The root of a worker session: the repository root of ``cwd`` when it holds a signal no commit can make.

    Git is asked only after the signal is found at or above ``cwd``, so a session without workers starts none.
    Committed content must hold nothing, or it would hold every session opened in that repository, and the
    filesystem can find .pe/worker where the index has no such path: through a .pe symlink, or as .pe/Worker on a
    filesystem that ignores case. So a .pe symlink holds nothing, and git is asked about .pe itself, in any letter
    case. When git gives no clear "nothing tracked" (exit 1 of --error-unmatch), the session is not held, as one
    without a signal.
    """
    top = _toplevel(cwd) if _signal_above(cwd) else None
    folder = os.path.join(top, PE_FOLDER) if top else ""
    if not folder or os.path.islink(folder) or not os.path.exists(os.path.join(top, WORKER_SIGNAL)):
        return None
    proc = _git(top, "ls-files", "--error-unmatch", "--", ":(icase)" + PE_FOLDER)
    return top if proc and proc.returncode == 1 else None


def _worker_file_problem(tool_input: Dict[str, Any], cwd: Any, root: Optional[str]) -> Optional[str]:
    paths = [tool_input[key] for key in _FILE_PATH_KEYS if key in tool_input]
    if root and paths and all(isinstance(path, str) and path and _inside(root, cwd, path) for path in paths):
        return None
    return _WORKER_WRITE_REASON


# The glob characters, which the shell may expand into other words (bash before 5.2 counts .. among the matches of
# .?), and what the shell still changes in a word of the worker grammar before using it as a path: a leading ~ or a
# glob. A path with either is not the path the text spells; the grammar keeps out $, backticks, braces, backslashes
# and a leading =.
_GLOB = re.compile(r"[*?\[]")
_UNSPELLED = re.compile(r"^~|" + _GLOB.pattern)


def _shell_reader() -> ModuleType:
    """lib/pe_guard/filters.py, imported only for a worker's command: a broken module stops no other call."""
    lib = str(Path(__file__).resolve().parent.parent / "lib")
    if lib not in sys.path:
        sys.path.insert(0, lib)
    return importlib.import_module("pe_guard.filters")


def _operands(arguments: List[str]) -> List[str]:
    """The words after the options, as getopt reads them: the options end at -- or at the first word that is not one,
    and a lone - is not one; every word after is an operand. BSD rm, macOS's, deletes a -d/.. written after a path;
    GNU rm reads it as an option, so reading it as a path only denies more."""
    position = 0
    while position < len(arguments) and arguments[position].startswith("-") and arguments[position] != "-":
        if arguments[position] == "--":
            return arguments[position + 1:]
        position += 1
    return arguments[position:]


def _spelled_below(root: Optional[str], cwd: Any, path: str) -> bool:
    """Whether ``path`` is the path the shell uses and lies below ``root``: a path a worker may delete."""
    return bool(root) and not _UNSPELLED.search(path) and _inside(root, cwd, path)


def _spelled_within(root: Optional[str], cwd: Any, path: str) -> bool:
    """Whether ``path`` is ``root`` or lies below it, spelled as above: a folder a worker may work in.

    A folder is within the worktree when a name inside it lies below the root, which also holds for the root itself;
    posixpath joins with /, which _UNSPELLED accepts, where os.path on Windows would join with a backslash.
    """
    return _spelled_below(root, cwd, posixpath.join(path, "x"))


_WORKER_DELETE_REASON = (
    "a worker deletes only below the root of its own worktree, never the root itself, and only paths that the command "
    "spells out: none that starts with ~ or holds a glob (*, ?, [); name each path in full"
)
_WORKER_CD_REASON = (
    "a worker's shell stays in its own worktree: cd, chdir and pushd take one folder inside it, spelled out in full "
    "(not -, +N or -N) and not inside another repository, such as a submodule or a nested worktree, popd takes no "
    "word, and each runs alone, in a call of its own, because the hook reads every path of a call from the folder "
    "where the call starts, and the shell keeps the new folder for the next call, whose worktree the hook finds from "
    "it; run the cd in its own call, or use git -C <folder> and paths from the current folder"
)
_WORKER_GIT_PLACE_REASON = (
    "a worker runs git only on its own worktree: no -C, --git-dir or --work-tree that points outside it, and no "
    "configuration of its own (-c, --config-env, or a variable that env sets for it), which can point it elsewhere, "
    "as core.worktree and GIT_DIR do"
)
_WORKER_GIT_SHARED_REASON = (
    "a worker leaves alone what all the worktrees share: no git stash, git worktree remove or prune, git push, git "
    "update-ref or git config that writes, no git branch or git tag that deletes, moves or forces one, and no git "
    "fetch or git pull into a local branch (<src>:<dst>); name the need in the delivery file instead"
)
_WORKER_GIT_GLOB_REASON = (
    "a worker writes every word of a git command without a glob (*, ?, [), quoted or not, because the shell may "
    "expand one into another subcommand, option or path; write each word in full, and list files with the Glob or "
    "Grep tool"
)
_WORKER_COMMAND_REASON = "a worker's Bash call carries its command as one string, which the hook reads"
_WORKER_UNREADABLE_REASON = "the hook cannot read this worker command for sure, so it denies it: %s"


def _deletion_problem(statement: "ShellStatement", cwd: Any, root: Optional[str]) -> Optional[str]:
    targets = _operands(statement.arguments)
    return None if all(_spelled_below(root, cwd, target) for target in targets) else _WORKER_DELETE_REASON


def _find_problem(statement: "ShellStatement", cwd: Any, root: Optional[str]) -> Optional[str]:
    """find -delete deletes what it finds below its start paths: the word after each -f, BSD find's (macOS's) way to
    name one that starts with -, and the words between its leading options and its expression; without any, the start
    is the working directory. GNU find's -files0-from reads them from a file instead, which the command does not spell
    out, so it is denied."""
    arguments = statement.arguments
    if "-delete" not in arguments:
        return None
    after_options = itertools.dropwhile(lambda word: word.startswith("-"), arguments)
    starts = [path for option, path in zip(arguments, arguments[1:]) if option == "-f"]
    starts += itertools.takewhile(lambda word: not word.startswith(("-", "(", "!")), after_options)
    spelled = "-files0-from" not in arguments
    inside = all(_spelled_below(root, cwd, start) for start in starts or ["."])
    return None if spelled and inside else _WORKER_DELETE_REASON


# The folders that cd, chdir and pushd name by a shorthand: - is $OLDPWD, even after --, and +N or -N an entry of
# zsh's directory stack.
_CD_SHORTHAND = re.compile(r"[+-][0-9]*")


def _cd_problem(statement: "ShellStatement", cwd: Any, root: Optional[str]) -> Optional[str]:
    """cd, chdir and pushd without a folder go home or swap folders, and zsh reads two folders as a substitution in the
    path, so only one folder, spelled out, passes; and only one of the same repository, because from the root of a
    submodule or a nested worktree the next call would find no signal."""
    folders = _operands(statement.arguments)
    if len(folders) != 1 or _CD_SHORTHAND.fullmatch(folders[0]) or not _spelled_within(root, cwd, folders[0]):
        return _WORKER_CD_REASON
    return None if _toplevel(os.path.join(cwd, folders[0])) == root else _WORKER_CD_REASON


def _popd_problem(statement: "ShellStatement", cwd: Any, root: Optional[str]) -> Optional[str]:
    """popd goes back to the folder that the last pushd left; a word names another entry of the directory stack or an
    option the check does not read, so only a bare popd passes."""
    return _WORKER_CD_REASON if statement.arguments else None


# git's options before the subcommand that take the next word as their value when no = joins it to them; those that
# point git at another repository or working tree; and those that give git a configuration of its own, which can do
# the same (core.worktree). A variable does it too (GIT_DIR, GIT_CONFIG_COUNT): one written before git never gets
# past the grammar, and git takes none that env sets, as it takes no -c.
_GIT_VALUE_OPTIONS = frozenset({
    "-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env", "--super-prefix", "--attr-source",
})
_GIT_PLACE_OPTIONS = frozenset({"-C", "--git-dir", "--work-tree"})
_GIT_CONFIG_OPTIONS = frozenset({"-c", "--config-env"})
# The options of git branch and git tag that delete, move or force one (branch -C is --copy --force); git takes short
# ones bundled (-Df) and long ones shortened to a prefix (--del), so a word that could be either counts.
_BRANCH_WRITES = ("dDfmMC", ("delete", "force", "move"))
_TAG_WRITES = ("df", ("delete", "force"))
# The first words of git config that only read; any other form may write the configuration all the worktrees share.
_CONFIG_READS = frozenset({"--get", "--get-all", "--get-regexp", "--list", "-l", "get", "list"})


def _git_options(arguments: List[str]) -> Tuple[List[str], List[str], List[str]]:
    """git's options before the subcommand, the folders they name, and the words from the subcommand on."""
    options: List[str] = []
    places: List[str] = []
    position = 0
    while position < len(arguments) and arguments[position].startswith("-"):
        option, joined, value = arguments[position].partition("=")
        if not joined and option in _GIT_VALUE_OPTIONS:
            position += 1
            value = arguments[position] if position < len(arguments) else ""
        options.append(option)
        if option in _GIT_PLACE_OPTIONS:
            places.append(value)
        position += 1
    return options, places, arguments[position:]


def _has_option(words: List[str], letters: str, names: Tuple[str, ...]) -> bool:
    return any(_is_option(word, letters, names) for word in words)


def _is_option(word: str, letters: str, names: Tuple[str, ...]) -> bool:
    if word.startswith("--"):
        return len(word) > 2 and any(name.startswith(word[2:]) for name in names)
    return word.startswith("-") and bool(set(letters) & set(word[1:]))


def _names_a_destination(words: List[str]) -> bool:
    """Whether a fetch or a pull names a refspec with a destination, which moves a local branch (. HEAD:integration):
    any word, because git reads one as an operand and as the value of an option in any place (--refmap=a:b)."""
    return any(":" in word for word in words)


# The git subcommands that change what all the worktrees of a repository share, each with the test of the words after
# it: one stash stack, one list of worktrees, one set of branches and tags, one configuration; a worker never pushes
# and never moves a ref by hand.
_SHARED_STATE: Dict[str, Callable[[List[str]], bool]] = {
    "stash": lambda words: True,
    "worktree": lambda words: words[:1] in (["remove"], ["prune"]),
    "branch": lambda words: _has_option(words, *_BRANCH_WRITES),
    "tag": lambda words: _has_option(words, *_TAG_WRITES),
    "fetch": _names_a_destination,
    "pull": _names_a_destination,
    "push": lambda words: True,
    "update-ref": lambda words: True,
    "config": lambda words: not (words and words[0] in _CONFIG_READS),
}


def _git_problem(statement: "ShellStatement", cwd: Any, root: Optional[str]) -> Optional[str]:
    if any(_GLOB.search(word) for word in statement.arguments):
        return _WORKER_GIT_GLOB_REASON
    options, places, words = _git_options(statement.arguments)
    configured = statement.variables or _GIT_CONFIG_OPTIONS.intersection(options)
    if configured or not all(_spelled_within(root, cwd, place) for place in places):
        return _WORKER_GIT_PLACE_REASON
    shared = _SHARED_STATE.get(words[0]) if words else None
    return _WORKER_GIT_SHARED_REASON if shared and shared(words[1:]) else None


_StatementCheck = Callable[["ShellStatement", Any, Optional[str]], Optional[str]]
# The builtins of bash and zsh that move the shell to another folder (zsh's chdir is cd); and the commands whose words
# the check reads, by the name of the command word.
_FOLDER_CHECKS: Dict[str, _StatementCheck] = {
    "cd": _cd_problem,
    "chdir": _cd_problem,
    "pushd": _cd_problem,
    "popd": _popd_problem,
}
_COMMAND_CHECKS: Dict[str, _StatementCheck] = {
    "rm": _deletion_problem,
    "rmdir": _deletion_problem,
    "unlink": _deletion_problem,
    "find": _find_problem,
    **_FOLDER_CHECKS,
    "git": _git_problem,
}


def _worker_command_problem(tool_input: Dict[str, Any], cwd: Any, root: Optional[str]) -> Optional[str]:
    """Why a statement of a worker's command reaches outside its worktree, or None; see the module docstring."""
    command = tool_input.get("command")
    if not isinstance(command, str):
        return _WORKER_COMMAND_REASON
    filters = _shell_reader()
    try:
        statements = filters.read_statements(command)
    except filters.UnreadableCommand as unreadable:
        return _WORKER_UNREADABLE_REASON % unreadable
    if len(statements) > 1 and any(s.name in _FOLDER_CHECKS for s in statements):
        return _WORKER_CD_REASON  # after a cd the shell runs the rest elsewhere than the cwd it is read from
    reasons = (_COMMAND_CHECKS[s.name](s, cwd, root) for s in statements if s.name in _COMMAND_CHECKS)
    return next((reason for reason in reasons if reason), None)


# The tools a worker changes files with, its shell included.
_WORKER_TOOL_CHECKS: Dict[str, Callable[[Dict[str, Any], Any, Optional[str]], Optional[str]]] = {
    "Write": _worker_file_problem,
    "Edit": _worker_file_problem,
    "NotebookEdit": _worker_file_problem,
    "Bash": _worker_command_problem,
}


def decide(payload: Any) -> Optional[str]:
    """Return why the tool call must be denied, or None for no decision."""
    if not isinstance(payload, dict):
        return None
    if _launches_reviewer(payload):
        return _prompt_problem(payload["tool_input"].get("prompt"))
    tool_input = payload.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    cwd = payload.get("cwd")
    if _runs_in_reviewer(payload):
        check = _REVIEWER_TOOL_CHECKS.get(payload.get("tool_name"))
        return check(tool_input, cwd) if check else None
    worker_check = _WORKER_TOOL_CHECKS.get(payload.get("tool_name"))
    if worker_check is None:
        return None
    if _runs_in_worker(payload):  # held even when git finds no root, so a lost root fails closed
        return worker_check(tool_input, cwd, _toplevel(cwd))
    root = _signalled_root(cwd)
    return worker_check(tool_input, cwd, root) if root else None


def main() -> int:
    try:
        # Bytes, so json decodes the UTF-8 that Claude Code sends; text would use the locale's code page (cp1252 on
        # Windows), which turns some valid input into a decode error.
        payload = json.loads(sys.stdin.buffer.read())
    except (OSError, ValueError, RecursionError):  # not JSON, not UTF-8, or nested too deeply to parse
        return 0
    try:
        reason = decide(payload)
    except Exception as exc:  # taste-exempt: a crash must deny the reviewer's and the worker's calls, and no other
        concerned = _launches_reviewer(payload) or _runs_in_reviewer(payload) or _runs_in_worker(payload)
        reason = "check failed (%s: %s)" % (exc.__class__.__name__, exc) if concerned else None
    if reason:
        print("pragmatic-engineering: " + reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
