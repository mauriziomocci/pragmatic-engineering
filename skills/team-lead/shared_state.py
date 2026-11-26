#!/usr/bin/env python3
"""Record what the worktrees of a repository share, and compare it later with what is there, for team-lead.

Usage, from the coordinator's checkout:
python3 <this skill's folder>/shared_state.py start --integration <branch> --team <branch>...
python3 <this skill's folder>/shared_state.py team <branch>...
python3 <this skill's folder>/shared_state.py merged <sha>
python3 <this skill's folder>/shared_state.py accept <item>...

The record is ``.pe/shared-state.json`` at the root of that checkout, outside the common folder of the repository
(``git rev-parse --git-common-dir``), where both scripts find it. ``start`` is the one full read: it writes the record
again and lists the worktrees outside the team (branch, ``detached``, ``prunable``). Every later record is derived from
the one before and never read again, so nothing that changed since the last clean comparison is absorbed: ``team``
adds team names before a launch; ``merged <sha>`` moves the integration branch, and the HEAD of the worktrees on it, to
the commit just integrated (after ``--ff-only`` the accepted sha, after ``--no-ff`` ``git rev-parse HEAD`` right after
the merge); ``accept`` takes items as an exit 4 of ``verify_delivery.py`` printed them and records the found value
printed with each, without reading git, so a later change to the same item stays a difference. ``start`` and ``team``
refuse a name equal to ``--integration`` or whose branch is in the record, and ``start`` an ``--integration`` that is
no branch. Exit 0, or 2 with the reason.

The closed list of what may change between the record and a comparison:

- Team refs, only while absent from the record: ``refs/heads/<team name>``; the same followed by ``-sync`` and zero or
  more digits; the branches whose name starts with ``worktree-agent-``, which the host makes for each sub-agent. A
  recorded one stays compared.
- Worktrees absent from the record, detached or on a team ref. Each entry of their ``config.worktree`` is
  ``core.untrackedcache``, ``core.longpaths`` or an entry that a recorded ``config.worktree`` held at ``start``,
  because ``git worktree add`` copies the ``config.worktree`` of the worktree it runs from; the rest of their folder
  under ``worktrees/`` is not compared. A worktree recorded as ``prunable`` may disappear, and the files of a recorded
  folder under ``worktrees/`` go with the folder, which only a worktree that disappears can lose.
- Volatile, measured: ``objects/`` except ``objects/info/alternates`` and ``objects/info/http-alternates``; ``refs/``,
  ``packed-refs``, ``reftable/``, ``logs/``, ``info/refs``; ``index``, ``HEAD``, ``ORIG_HEAD``, ``COMMIT_EDITMSG``;
  ``fsmonitor--daemon.ipc``, ``fsmonitor--daemon/``; in a recorded folder under ``worktrees/`` all but
  ``config.worktree``, ``commondir`` and ``gitdir``. Volatile, not measured, from gitrepository-layout and git-lfs:
  ``FETCH_HEAD``, ``AUTO_MERGE``, ``MERGE_HEAD``, ``MERGE_MSG``, ``MERGE_MODE``, ``MERGE_RR``, ``rr-cache/``, ``lfs/``,
  ``gc.pid``, ``gc.log``, ``*.lock``.
- By entries and by lines: ``config`` may gain only ``extensions.worktreeconfig=true``; ``info/exclude`` only lines
  that start with ``.claude/`` or ``**/.claude/``.

Everything else is compared: each ref by name and symbolic target (``git for-each-ref``), its value from one ``git
cat-file --batch-check``, which reads a name as a lookup does (where the file system ignores case, a loose
``refs/heads/Main`` is what ``refs/heads/main`` reads, while ``for-each-ref`` still shows the packed value); each
worktree's HEAD, branch and ``prunable`` (``git worktree list --porcelain``); every other file of the common folder, a
regular file by its SHA-256, a symlink by its target, a socket or a FIFO by its kind; the entries of ``config`` and of
a new worktree's ``config.worktree`` by name and by the SHA-256 of the value, so that no secret of a configuration is
copied into the record or into a message; the lines of ``info/exclude``; and, present or absent, each configuration
file that ``git config --list --show-origin`` names, each target of ``include.path`` and ``includeIf.*.path``,
``~/.gitconfig``, ``$XDG_CONFIG_HOME/git/config`` (``~/.config/git/config`` without the variable) and the files of the
hooks folder (``git rev-parse --git-path hooks``) when it lies outside every worktree. No git call here starts a
program.

It sees what a worker changed in a hurry or by accident, after the fact; not a worker that rewrites the record, the
scripts, the plugin's hook or the coordinator's checkout.
"""
import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Dict, FrozenSet, Iterable, Iterator, List, Mapping, Optional, Sequence, Set, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lib"))
from pe_git import run_git  # noqa: E402  (the plugin's shared code, found from this file)

RECORD = Path(".pe") / "shared-state.json"
NO_RECORD = "no record at %s: `shared_state.py start` begins a new run; in a run, stop and go to the user"
HEADS = "refs/heads/"
HOST_BRANCH = "worktree-agent-"
SYNC = "(?:-sync[0-9]*)?"
VOLATILE = ("objects/", "refs/", "packed-refs", "reftable/", "logs/", "info/refs", "index", "HEAD", "ORIG_HEAD",
            "COMMIT_EDITMSG", "fsmonitor--daemon.ipc", "fsmonitor--daemon/", "FETCH_HEAD", "AUTO_MERGE", "MERGE_HEAD",
            "MERGE_MSG", "MERGE_MODE", "MERGE_RR", "rr-cache/", "lfs/", "gc.pid", "gc.log")
NOT_VOLATILE = ("objects/info/alternates", "objects/info/http-alternates")
LOCK = ".lock"
READ_APART = ("config", "info/exclude", "worktrees/")  # by entries, by lines, folder by folder
SKIPPED_FOLDERS = tuple(name for name in VOLATILE + READ_APART if name.endswith("/"))
ADMIN_COMPARED = ("config.worktree", "commondir", "gitdir")
CONFIG_MAY_GAIN = ("extensions.worktreeconfig=true",)
EXCLUDE_MAY_GAIN = (".claude/", "**/.claude/")
NEW_WORKTREE_ENTRIES = ("core.untrackedcache", "core.longpaths")
OBJECT_ID = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")
FILE_KINDS = {stat.S_IFSOCK: "socket", stat.S_IFIFO: "fifo", stat.S_IFDIR: "folder"}

Item = Tuple[Optional[str], ...]  # its kind, then its name: ("ref", "refs/heads/main")
Entry = Tuple[str, Optional[str]]  # a configuration entry: its name and the digest of its value, None for no value


class RecordError(Exception):
    """The call or the record is wrong, or git could not answer: nothing was recorded or compared."""


@dataclass(frozen=True)
class Record:
    integration: str
    team: FrozenSet[str]
    items: Mapping[Item, Any]
    copied: FrozenSet[Entry]  # the entries of the recorded config.worktree files at start, which worktree add copies


@dataclass(frozen=True)
class Observation:
    items: Mapping[Item, Any]
    admin_folders: FrozenSet[str]  # the folders under worktrees/ that are there now


@dataclass(frozen=True)
class Difference:
    item: Item
    recorded: Any  # None: absent from the record
    found: Any  # None: absent now

    def line(self) -> str:
        """The one line that exit 4 prints and that ``accept`` takes back."""
        return json.dumps({"item": list(self.item), "recorded": self.recorded, "found": self.found})


def digest(text: str) -> str:
    return "sha256 " + hashlib.sha256(text.encode("utf-8", "surrogateescape")).hexdigest()


def listed_entry(text: str) -> Entry:
    """One entry of ``git config --list --null``: its name, then a newline and its value unless it has none."""
    name, newline, value = text.partition("\n")
    return name, digest(value) if newline else None


CONFIG_GAINS = frozenset(listed_entry(text.replace("=", "\n", 1)) for text in CONFIG_MAY_GAIN)


# --- the comparison and the derivations: no read of git ------------------------------------------------------------


def is_team_ref(record: Record, name: str) -> bool:
    if ("ref", name) in record.items or not name.startswith(HEADS):
        return False
    branch = name[len(HEADS):]
    return branch.startswith(HOST_BRANCH) or any(re.fullmatch(re.escape(team) + SYNC, branch) for team in record.team)


def admin_folder(path: str) -> Optional[str]:
    """The folder under ``worktrees/`` that a path of the common folder lies in, if any."""
    parts = path.split("/")
    return parts[1] if len(parts) == 3 and parts[0] == "worktrees" else None


def goes_with_its_folder(now: "Observation", item: Item, recorded: Any) -> bool:
    """A file of a recorded folder under ``worktrees/`` that is gone: the worktree list judges its worktree."""
    folder = admin_folder(item[1])
    return folder is not None and folder not in now.admin_folders


# What may appear while absent from the record, and what may disappear, kind by kind; any other change is a difference.
MAY_APPEAR: Dict[str, Callable[[Record, Item, Any], bool]] = {
    "ref": lambda record, item, found: is_team_ref(record, item[1]),
    "worktree": lambda record, item, found: found[1] is None or is_team_ref(record, found[1]),
    "config": lambda record, item, found: item[1:] in CONFIG_GAINS,
    "worktree-config": lambda record, item, found: item[2] in NEW_WORKTREE_ENTRIES or item[2:] in record.copied,
    "exclude": lambda record, item, found: item[1].startswith(EXCLUDE_MAY_GAIN),
}
MAY_DISAPPEAR: Dict[str, Callable[[Observation, Item, Any], bool]] = {
    "worktree": lambda now, item, recorded: recorded[2],
    "file": goes_with_its_folder,
}
ITEM_KINDS = ("ref", "worktree", "file", "config", "worktree-config", "exclude")


def is_free(record: Record, now: Observation, change: Difference) -> bool:
    kind = change.item[0]
    if change.recorded is None:
        return kind in MAY_APPEAR and MAY_APPEAR[kind](record, change.item, change.found)
    return change.found is None and kind in MAY_DISAPPEAR and MAY_DISAPPEAR[kind](now, change.item, change.recorded)


def differences(record: Record, now: Observation) -> List[Difference]:
    """Every change since the record that the closed list does not allow, in a stable order."""
    items = sorted(set(record.items) | set(now.items), key=json.dumps)
    found = (Difference(item, record.items.get(item), now.items.get(item)) for item in items)
    return [change for change in found if change.recorded != change.found and not is_free(record, now, change)]


def with_team(record: Record, names: Sequence[str]) -> Record:
    """A team name must be a new branch: the integration, or a branch in the record, would be freed for the run."""
    taken = [name for name in names if name == record.integration or ("ref", HEADS + name) in record.items]
    if taken:
        raise RecordError("%s: a team name must be a branch that is neither the integration nor in the record"
                          % ", ".join(taken))
    return replace(record, team=record.team | frozenset(names))


def merged(record: Record, sha: str) -> Record:
    if not OBJECT_ID.fullmatch(sha):
        raise RecordError("%r is not a full commit id (40 or 64 hex digits)" % sha)
    branch = HEADS + record.integration
    items = {item: (sha, value[1], value[2]) if item[0] == "worktree" and value[1] == branch else value
             for item, value in record.items.items()}
    items[("ref", branch)] = sha
    return replace(record, items=MappingProxyType(items))


def frozen(value: Any) -> Any:
    """A JSON value with its lists made tuples, as the record holds them."""
    return tuple(frozen(part) for part in value) if isinstance(value, list) else value


def printed_change(line: str) -> Tuple[Item, Any]:
    """The item and the found value of one line that exit 4 printed."""
    try:
        change = json.loads(line)
        item, found = tuple(change["item"]), frozen(change["found"])
    except (ValueError, TypeError, KeyError) as error:
        raise RecordError("%r is not an item that verify_delivery.py printed: %s" % (line, error)) from error
    if not item or item[0] not in ITEM_KINDS or not all(part is None or isinstance(part, str) for part in item):
        raise RecordError("%r is not an item that verify_delivery.py printed" % line)
    return item, found


def accepted(record: Record, lines: Sequence[str]) -> Record:
    items = dict(record.items)
    for item, found in map(printed_change, lines):
        if found is None:
            items.pop(item, None)
        else:
            items[item] = found
    return replace(record, items=MappingProxyType(items))


def started(integration: str, team: Sequence[str], now: Observation, copied: FrozenSet[Entry]) -> Record:
    if ("ref", HEADS + integration) not in now.items:
        raise RecordError("--integration %r is not a branch of this repository" % integration)
    return with_team(Record(integration, frozenset(), now.items, copied), team)


# --- the reader: only reads, each git call through run_git ----------------------------------------------------------


def git(*args: str, stdin: Optional[str] = None) -> str:
    proc = run_git(*args, input=stdin)
    if proc.returncode != 0:
        raise RecordError("`git %s` failed: %s" % (" ".join(args), proc.stderr.strip()))
    return proc.stdout


def common_dir(folder: Optional[str] = None) -> str:
    """The common folder of the repository of the current folder, or of ``folder``, as an absolute path."""
    return git(*(("-C", folder) if folder else ()), "rev-parse", "--path-format=absolute", "--git-common-dir").strip()


def read_refs() -> Dict[Item, str]:
    """Names from ``for-each-ref``, values from one lookup each; a name gone in between is left out, as if absent."""
    listed = [line.split("\0") for line in git("for-each-ref", "--format=%(refname)%00%(symref)").splitlines()]
    looked_up = git("cat-file", "--batch-check=%(objectname)", stdin="".join(name + "\n" for name, _ in listed))
    return {("ref", name): value + (" -> " + target if target else "")
            for (name, target), value in zip(listed, looked_up.splitlines()) if OBJECT_ID.fullmatch(value)}


def read_worktrees() -> Dict[Item, Tuple[Optional[str], Optional[str], bool]]:
    found = {}
    for block in git("worktree", "list", "--porcelain", "-z").split("\0\0"):
        fields = dict(field.partition(" ")[::2] for field in block.split("\0") if field)
        if "worktree" in fields:
            found[("worktree", fields["worktree"])] = (fields.get("HEAD"), fields.get("branch"), "prunable" in fields)
    return found


def file_value(path: str) -> Optional[str]:
    """A regular file by the SHA-256 of its bytes, a symlink by its target, anything else by its kind; None if absent."""
    try:
        mode = os.lstat(path).st_mode
        if stat.S_ISLNK(mode):
            return "symlink " + os.readlink(path)
        if stat.S_ISREG(mode):
            return "sha256 " + hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except FileNotFoundError:
        return None
    return FILE_KINDS.get(stat.S_IFMT(mode), "other")


def scanned(folder: str) -> List[os.DirEntry]:
    with os.scandir(folder) as entries:
        return sorted(entries, key=lambda entry: entry.name)


def walk(root: str, skipped: Callable[[str], bool], below: str = "") -> Iterator[Tuple[str, str]]:
    """Each path below ``root`` that is not a folder, relative with ``/`` and absolute; a symlink is never followed,
    and a folder, written with its ``/``, is entered unless ``skipped`` says so."""
    for entry in scanned(os.path.join(root, below)):
        path = below + entry.name + ("/" if entry.is_dir(follow_symlinks=False) else "")
        if skipped(path):
            continue
        if path.endswith("/"):
            yield from walk(root, skipped, path)
        else:
            yield path, entry.path


def skipped_in_common(path: str) -> bool:
    """Volatile, or read apart; a folder on the way to a compared file is entered."""
    if path in NOT_VOLATILE or (path.endswith("/") and any(kept.startswith(path) for kept in NOT_VOLATILE)):
        return False
    return path.endswith(LOCK) or path.startswith(SKIPPED_FOLDERS) or path in VOLATILE + READ_APART


def file_items(paths: Iterable[Tuple[str, str]]) -> Dict[Item, str]:
    found = ((("file", key), file_value(path)) for key, path in paths)
    return {item: value for item, value in found if value is not None}


def config_entries(path: str) -> Counter:
    if not os.path.isfile(path):
        return Counter()
    listed = git("config", "--file", path, "--list", "--null").split("\0")
    return Counter(listed_entry(text) for text in listed if text)


def read_admin_folders(common: str, registered: Optional[FrozenSet[str]]) -> Observation:
    """The three compared files of each recorded folder under ``worktrees/``, and the entries of the
    ``config.worktree`` of each other one; at ``start`` (``registered`` None) every folder there is recorded."""
    folder = os.path.join(common, "worktrees")
    entries = scanned(folder) if os.path.isdir(folder) else []
    present = frozenset(entry.name for entry in entries if entry.is_dir(follow_symlinks=False))
    items: Dict[Item, Any] = {}
    for name in present:
        if registered is None or name in registered:
            items.update(file_items(("worktrees/%s/%s" % (name, file), os.path.join(folder, name, file))
                                for file in ADMIN_COMPARED))
        else:
            config = config_entries(os.path.join(folder, name, "config.worktree"))
            items.update({("worktree-config", name) + entry: count for entry, count in config.items()})
    return Observation(items, present)


def read_exclude(common: str) -> Dict[Item, int]:
    path = Path(common, "info", "exclude")
    lines = path.read_bytes().decode("utf-8", "surrogateescape").splitlines() if path.is_file() else []
    return {("exclude", line): count for line, count in Counter(lines).items()}


def configuration_files(top: str) -> Set[str]:
    """Each file git reads its configuration from here, and each file an include names, read now or not."""
    words = git("config", "--list", "--show-origin", "--null").split("\0")
    files = set()
    for origin, text in zip(words[0::2], words[1::2]):
        if origin.startswith("file:"):
            source = os.path.join(top, origin[len("file:"):])
            files.add(source)
            files.update(include_target(source, text))
    return files


def include_target(source: str, text: str) -> List[str]:
    name, _, value = text.partition("\n")
    if not value or not (name == "include.path" or (name.startswith("includeif.") and name.endswith(".path"))):
        return []
    return [os.path.normpath(os.path.join(os.path.dirname(source), os.path.expanduser(value)))]


def global_files() -> Set[str]:
    xdg = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return {os.path.join(os.path.expanduser("~"), ".gitconfig"), os.path.join(xdg, "git", "config")}


def is_below(path: str, folder: str) -> bool:
    return path == folder or path.startswith(folder.rstrip(os.sep) + os.sep)


def outside_hooks(inside: Sequence[str]) -> List[str]:
    """The files of the hooks folder, when it lies outside the common folder and every worktree."""
    hooks = os.path.realpath(git("rev-parse", "--path-format=absolute", "--git-path", "hooks").strip())
    if not os.path.isdir(hooks) or any(is_below(hooks, folder) for folder in inside):
        return []
    return [path for _, path in walk(hooks, lambda path: False)]


def read_outside(common: str, worktrees: Iterable[str]) -> Dict[Item, str]:
    inside = [os.path.realpath(folder) for folder in [common, *worktrees]]
    top = git("rev-parse", "--show-toplevel").strip()
    paths = configuration_files(top) | global_files() | set(outside_hooks(inside))
    return file_items((path, path) for path in sorted(paths) if not is_below(os.path.realpath(path), inside[0]))


def recorded_admin_folders(record: Record) -> FrozenSet[str]:
    return frozenset(admin_folder(item[1]) for item in record.items if item[0] == "file") - {None}


def observe(record: Optional[Record] = None) -> Observation:
    """Everything a record holds, read now. ``record`` says which folders under ``worktrees/`` are recorded; without
    one, at ``start``, every folder there is."""
    common = common_dir()
    registered = None if record is None else recorded_admin_folders(record)
    try:
        worktrees = read_worktrees()
        admin = read_admin_folders(common, registered)
        files = file_items(walk(common, skipped_in_common))
        config = config_entries(os.path.join(common, "config"))
        items = {**read_refs(), **worktrees, **files, **admin.items, **read_exclude(common),
                 **{("config",) + entry: count for entry, count in config.items()},
                 **read_outside(common, (item[1] for item in worktrees))}
    except OSError as error:
        raise RecordError("the shared state cannot be read: %s" % error) from error
    return Observation(MappingProxyType(items), admin.admin_folders)


def copied_entries(common: str, folders: Iterable[str]) -> FrozenSet[Entry]:
    paths = [os.path.join(common, "config.worktree")] + [os.path.join(common, "worktrees", name, "config.worktree")
                                                         for name in folders]
    return frozenset(entry for path in paths for entry in config_entries(path))


# --- the record on disk ---------------------------------------------------------------------------------------------


def record_path() -> Path:
    return Path(git("rev-parse", "--show-toplevel").strip()) / RECORD


def load(path: Path) -> Record:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Record(data["integration"], frozenset(data["team"]),
                      MappingProxyType({tuple(item): frozen(value) for item, value in data["items"]}),
                      frozenset(tuple(entry) for entry in data["copied"]))
    except FileNotFoundError as error:
        raise RecordError(NO_RECORD % path) from error
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise RecordError("the record %s cannot be read: %s" % (path, error)) from error


def save(record: Record, path: Path) -> None:
    """Whole or not at all; with the ``.gitignore`` holding ``*`` that keeps ``.pe/`` out of git."""
    data = {"integration": record.integration, "team": sorted(record.team),
            "copied": sorted(record.copied, key=json.dumps),
            "items": sorted(([list(item), value] for item, value in record.items.items()), key=json.dumps)}
    path.parent.mkdir(exist_ok=True)
    ignore = path.parent / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n", encoding="utf-8")
    partial = path.with_name(path.name + ".partial")
    partial.write_text(json.dumps(data), encoding="utf-8")
    os.replace(str(partial), str(path))


# --- the commands ---------------------------------------------------------------------------------------------------


def start(args: argparse.Namespace) -> None:
    now = observe()
    record = started(args.integration, args.team, now, copied_entries(common_dir(), now.admin_folders))
    save(record, record_path())
    worktrees = sorted((item[1], value) for item, value in record.items.items() if item[0] == "worktree")
    for path, (_, branch, prunable) in worktrees:
        print("%s %s%s" % (path, branch[len(HEADS):] if branch else "detached", " prunable" if prunable else ""))


DERIVED: Dict[str, Callable[[Record, argparse.Namespace], Record]] = {
    "team": lambda record, args: with_team(record, args.names),
    "merged": lambda record, args: merged(record, args.sha),
    "accept": lambda record, args: accepted(record, args.items),
}


def parser() -> argparse.ArgumentParser:
    commands = argparse.ArgumentParser(prog="shared_state")
    command = commands.add_subparsers(dest="command", required=True)
    first = command.add_parser("start")
    first.add_argument("--integration", required=True)
    first.add_argument("--team", nargs="+", required=True)
    command.add_parser("team").add_argument("names", nargs="+")
    command.add_parser("merged").add_argument("sha")
    command.add_parser("accept").add_argument("items", nargs="+")
    return commands


def main(argv: Sequence[str]) -> int:
    args = parser().parse_args(argv)  # a wrong call: argparse prints why and exits 2
    try:
        if args.command == "start":
            start(args)
        else:
            path = record_path()
            save(DERIVED[args.command](load(path), args), path)
    except RecordError as error:
        print("shared_state: %s" % error, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
