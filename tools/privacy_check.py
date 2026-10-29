#!/usr/bin/env python3
"""Privacy check for the pragmatic-engineering repository.

The public repository must never carry a personal path, a private name or a
secret. This check looks at everything a push sends to the remote: the added
lines and the path of every file each pushed commit adds or changes (empty
files included; the history is as public as the tree), every commit message,
the header of every commit and annotated tag (author, committer and tagger
names and emails, the tag name), and the names of the pushed references. It
looks for two kinds of evidence: the maintainer's private terms, read from a
file outside every repository whose path is in ``git config
pe.privateTermsFile``, and generic patterns (home paths, recognisable keys and
tokens). A pattern finding names the pattern, never the matched text, so a
secret found in a line, a message or a header is not echoed into logs. The
location printed next to a finding does show the file path or the reference
name it concerns (a finding in a path or a reference name is located by that
very name), and a term finding shows the term, which comes from the
maintainer's own list.

What counts as a binary file does not depend on the clone or on the user: the
patch is read with a fixed size limit and without the user's global attributes
file. The repository's own ``.gitattributes`` (and ``.git/info/attributes``)
remains a known limit: a ``-diff`` rule there makes git report the matching
files as binary, so they are skipped, and the skip is listed, not silent.

Usage:
    privacy_check.py pre-push <remote-name> <remote-url>   (git's lines on stdin)
    privacy_check.py scan <revision>...                    (e.g. scan main..HEAD)

Exit status: 0 clean, 1 findings, 2 configuration or git failure. A pre-push
hook blocks the push on any non-zero status, so the check fails closed.
"""
import functools
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Pattern, Sequence, Set, TextIO, Tuple

ZERO_SHA = "0" * 40
MAX_REPORTED = 50
USAGE = "usage: privacy_check.py pre-push <remote-name> <remote-url> | scan <revision>..."

GENERIC_PATTERNS: Dict[str, Pattern[str]] = {
    "home-path-macos": re.compile(r"/Users/[A-Za-z0-9._-]+"),
    "home-path-linux": re.compile(r"/home/[A-Za-z0-9._-]+/"),
    "home-path-windows": re.compile(r"[A-Za-z]:\\+Users\\+[A-Za-z0-9._ -]+\\"),
    "claude-project-dir": re.compile(r"-Users-[A-Za-z0-9._]+"),
    "github-token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}"),
    "github-fine-grained-token": re.compile(r"\bgithub_pat_[A-Za-z0-9_]{22,}"),
    "gitlab-token": re.compile(r"\bglpat-[A-Za-z0-9_-]{20,}"),
    "aws-access-key-id": re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    "private-key-block": re.compile(r"-----BEGIN (?:[A-Z]+ )*PRIVATE KEY-----"),
    "slack-token": re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"),
    "anthropic-or-openai-key": re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}"),
    "google-api-key": re.compile(r"\bAIza[0-9A-Za-z_-]{35}"),
}
_ANY_GENERIC = re.compile("|".join("(?:%s)" % p.pattern for p in GENERIC_PATTERNS.values()))
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_OBJECT_ID = re.compile(r"\b[0-9a-f]{40}(?:[0-9a-f]{24})?\b")


class TermsError(Exception):
    """The private terms file is not configured, unreadable, empty or misplaced."""


class GitError(Exception):
    """A git command failed, or git produced input this check does not understand."""


@dataclass(frozen=True)
class Finding:
    where: str
    kind: str
    label: str


@dataclass
class ScanResult:
    findings: List[Finding] = field(default_factory=list)
    skipped_binaries: List[str] = field(default_factory=list)

    def extend(self, other: "ScanResult") -> None:
        self.findings.extend(other.findings)
        self.skipped_binaries.extend(other.skipped_binaries)


def load_terms(path: Path) -> List[str]:
    """Read one term per line; BOM, CRLF, blank lines and '#' comments are ignored."""
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as exc:
        raise TermsError(
            "cannot read the private terms file %s (%s)" % (path, exc.__class__.__name__)
        ) from exc
    terms: List[str] = []
    seen: Set[str] = set()
    for line in raw.splitlines():
        term = line.strip()
        if not term or term.startswith("#"):
            continue
        if term.lower() not in seen:
            seen.add(term.lower())
            terms.append(term)
    if not terms:
        raise TermsError("the private terms file %s contains no terms" % path)
    return terms


@functools.lru_cache(maxsize=None)
def _term_regex(term: str) -> Pattern[str]:
    # A lookahead finds overlapping occurrences, so a rejected occurrence
    # cannot hide an accepted one that overlaps it.
    return re.compile("(?=(%s))" % re.escape(term), re.IGNORECASE)


def _is_boundary(text: str, index: int) -> bool:
    """True when ``index`` falls between two words of ``text``, or at an end of it.

    The boundaries are the ones a camel-case identifier has: next to a
    non-letter, from a lower-case to an upper-case letter ('getZorblax'), and
    inside a run of capitals, before the last one, when a lower-case letter
    follows it ('HTTPZorblax', 'ZORBLAXClient').
    """
    if index <= 0 or index >= len(text):
        return True
    before, after = text[index - 1], text[index]
    if not (before.isalpha() and after.isalpha()):
        return True
    if before.islower() and after.isupper():
        return True
    return before.isupper() and after.isupper() and text[index + 1:index + 2].islower()


def _term_occurs(text: str, term: str) -> bool:
    """True when ``term`` occurs in ``text`` as a whole word, ignoring case.

    A word boundary is where a camel-case identifier splits (see
    ``_is_boundary``), so a name inside 'IoZorblax', 'HTTPZorblaxClient' or
    'getZORBLAXData' is found while 'cat' is not found in 'concatenate' and
    'QX' is not found in 'QXTRA'. A side of the term that is not a letter (the
    '+' of 'C++') needs no boundary on that side.
    """
    check_start = term[0].isalpha()
    check_end = term[-1].isalpha()
    for match in _term_regex(term).finditer(text):
        start, end = match.start(1), match.end(1)
        if check_start and not _is_boundary(text, start):
            continue
        if check_end and not _is_boundary(text, end):
            continue
        return True
    return False


def find_terms(text: str, terms: Sequence[str]) -> List[str]:
    lowered = text.lower()
    return [t for t in terms if t.lower() in lowered and _term_occurs(text, t)]


def find_generic(text: str) -> List[str]:
    if not _ANY_GENERIC.search(text):
        return []
    return [name for name, pattern in GENERIC_PATTERNS.items() if pattern.search(text)]


def scan_text(text: str, terms: Sequence[str], where: str) -> List[Finding]:
    found = [Finding(where, "term", term) for term in find_terms(text, terms)]
    found.extend(Finding(where, "pattern", name) for name in find_generic(text))
    return found


def _run_git(repo: Path, *args: str, timeout: Optional[float] = None) -> "subprocess.CompletedProcess[bytes]":
    """Run git in ``repo``; a timeout, or a git that cannot start, becomes a GitError.

    Every way git can fail reaches the callers as one exception type, so the
    exit status contract of ``main`` (2 for a git failure) holds without each
    caller knowing about subprocess errors.
    """
    command = " ".join(("git",) + args)
    try:
        return subprocess.run(["git", *args], cwd=str(repo), capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise GitError("%s timed out after %s seconds" % (command, timeout)) from exc
    except OSError as exc:
        raise GitError("cannot run %s: %s" % (command, exc.strerror or exc.__class__.__name__)) from exc


def _git(repo: Path, *args: str, timeout: Optional[float] = None) -> str:
    proc = _run_git(repo, *args, timeout=timeout)
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", "replace").strip()
        raise GitError("git %s failed: %s" % (" ".join(args), detail))
    return proc.stdout.decode("utf-8", "replace")


def repository_root(path: Path, timeout: Optional[float] = None) -> Path:
    """Top of the working tree that contains ``path``; a hook passes a timeout.

    Raises GitError, also when git times out or cannot start.
    """
    return Path(_git(path, "rev-parse", "--show-toplevel", timeout=timeout).strip())


def terms_file_from_git(repo: Path, timeout: Optional[float] = None) -> Path:
    """Return the configured terms file, which must live outside the repository.

    Raises TermsError when none is configured or it is misplaced, and GitError
    when git times out or cannot start.
    """
    proc = _run_git(repo, "config", "--type=path", "--get", "pe.privateTermsFile", timeout=timeout)
    value = proc.stdout.decode("utf-8", "replace").strip()
    if proc.returncode != 0 or not value:
        raise TermsError(
            "no private terms file is configured for this clone; set one outside "
            "the repository with: git config pe.privateTermsFile <path>"
        )
    path = Path(value)
    if not path.is_absolute():
        path = repo / path
    resolved = path.resolve()
    top = repo.resolve()
    if resolved == top or top in resolved.parents:
        raise TermsError("the private terms file must live outside the repository: %s" % path)
    return resolved


def _is_local_commit(repo: Path, sha: str) -> bool:
    return _run_git(repo, "cat-file", "-e", sha + "^{commit}").returncode == 0


def commits_to_push(repo: Path, local_sha: str, remote_sha: str, remote_name: str) -> List[str]:
    """Commits reachable from ``local_sha`` that the remote does not already show."""
    args = ["rev-list", local_sha, "--not", "--remotes=%s" % remote_name]
    if remote_sha != ZERO_SHA and _is_local_commit(repo, remote_sha):
        args.append(remote_sha)
    return _git(repo, *args).split()


def _strip_side_prefix(path: str) -> str:
    return path[2:] if path.startswith(("a/", "b/")) else path


def _object_parts(repo: Path, kind: str, sha: str) -> Tuple[str, str]:
    """Split a commit or tag object into its header (identities, tag name) and its message.

    The object ids of the header (tree, parent, object, the one inside a
    mergetag) are removed: they are hex digits, and a short term made of the
    letters a to f would match inside them. The rest of the header is kept:
    author, committer, tagger, tag name, mergetag and signature lines.
    """
    header, _, message = _git(repo, "cat-file", kind, sha).partition("\n\n")
    return _OBJECT_ID.sub("", header), message


def _scan_paths(repo: Path, sha: str, terms: Sequence[str], result: ScanResult) -> None:
    """Scan the path of every file a commit adds or changes (first parent for merges).

    The list comes from git, not from the patch, because a new empty file has
    no +++ line; deleted paths are left out, so removing a name is never blocked.
    ``--root`` lists the files of a root commit even when ``log.showRoot`` is off.
    """
    short = sha[:12]
    names = _git(
        repo, "show", "--format=", "--name-only", "-z", "--no-relative", "--root",
        "--diff-merges=first-parent", "--diff-filter=d", sha,
    )
    for path in names.split("\0"):
        if path:
            result.findings.extend(scan_text(path, terms, "commit %s path %s" % (short, path)))


def _scan_patch_lines(lines: Iterable[bytes], short: str, terms: Sequence[str], result: ScanResult) -> None:
    """Scan the lines a patch adds, each with its path and its line number in the new file; list the binaries."""
    path = "?"
    new_line = 0
    in_header = False
    for raw in lines:
        line = raw.decode("utf-8", "replace").rstrip("\r\n")
        if line.startswith("diff --git "):
            in_header = True
        elif in_header and line.startswith("+++ "):
            # git appends a tab to ---/+++ lines when the path has a space.
            path = _strip_side_prefix(line[4:].rstrip("\t"))
        elif line.startswith("Binary files ") and line.endswith(" differ"):
            names = line[len("Binary files "):-len(" differ")]
            result.skipped_binaries.append("%s %s" % (short, names))
        elif line.startswith("@@ "):
            in_header = False
            match = _HUNK.match(line)
            new_line = int(match.group(1)) if match else 0
        elif not in_header and line.startswith("+"):
            where = "commit %s %s:%d" % (short, path, new_line)
            result.findings.extend(scan_text(line[1:], terms, where))
            new_line += 1


def _scan_patch(repo: Path, sha: str, terms: Sequence[str], result: ScanResult) -> None:
    """Stream one commit's patch (first parent for merges) and scan the lines it adds.

    ``core.bigFileThreshold`` and the user's attributes file are pinned on the
    command line, so which files git calls binary does not depend on the clone's
    or the user's configuration; ``--root`` shows a root commit even when
    ``log.showRoot`` is off.
    """
    short = sha[:12]
    command = [
        "git", "-c", "core.quotepath=off", "-c", "core.bigFileThreshold=2g",
        "-c", "core.attributesFile=/dev/null",
        "show", "--format=", "--patch", "--no-color", "--no-ext-diff", "--no-textconv",
        "--no-relative", "--root", "--diff-merges=first-parent",
        "-U0", "--inter-hunk-context=0", "--src-prefix=a/", "--dst-prefix=b/", sha,
    ]
    with tempfile.TemporaryFile() as errors:
        try:
            proc = subprocess.Popen(command, cwd=str(repo), stdout=subprocess.PIPE, stderr=errors)
        except OSError as exc:
            raise GitError(
                "cannot run git show %s: %s" % (short, exc.strerror or exc.__class__.__name__)
            ) from exc
        assert proc.stdout is not None
        _scan_patch_lines(proc.stdout, short, terms, result)
        status = proc.wait()
        if status != 0:
            errors.seek(0)
            detail = errors.read().decode("utf-8", "replace").strip()
            raise GitError("git show %s failed: %s" % (short, detail))


def scan_commits(repo: Path, shas: Sequence[str], terms: Sequence[str]) -> ScanResult:
    result = ScanResult()
    for sha in shas:
        header, message = _object_parts(repo, "commit", sha)
        result.findings.extend(scan_text(header, terms, "commit %s header" % sha[:12]))
        result.findings.extend(scan_text(message, terms, "commit %s message" % sha[:12]))
        _scan_paths(repo, sha, terms, result)
        _scan_patch(repo, sha, terms, result)
    return result


def check_pre_push(repo: Path, remote_name: str, lines: Iterable[str], terms: Sequence[str]) -> ScanResult:
    """Check every reference line that git hands to a pre-push hook (F1, F6)."""
    result = ScanResult()
    seen: Set[str] = set()
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        parts = line.split(" ")
        if len(parts) != 4:
            raise GitError("unexpected pre-push line: %r" % line)
        local_ref, local_sha, remote_ref, remote_sha = parts
        if local_sha == ZERO_SHA:
            continue  # a deletion sends no content
        for ref in sorted({local_ref, remote_ref}):
            result.findings.extend(scan_text(ref, terms, "ref %s" % ref))
        kind = _git(repo, "cat-file", "-t", local_sha).strip()
        if kind == "tag":
            header, message = _object_parts(repo, "tag", local_sha)
            result.findings.extend(scan_text(header, terms, "tag %s header" % remote_ref))
            result.findings.extend(scan_text(message, terms, "tag %s message" % remote_ref))
        elif kind != "commit":
            raise GitError("pushing a %s object is not supported by the privacy check" % kind)
        shas = [s for s in commits_to_push(repo, local_sha, remote_sha, remote_name) if s not in seen]
        seen.update(shas)
        result.extend(scan_commits(repo, shas, terms))
    return result


def _report(result: ScanResult, out: TextIO) -> int:
    if result.skipped_binaries:
        print("privacy check: %d binary file(s) not scanned:" % len(result.skipped_binaries), file=out)
        for item in result.skipped_binaries[:MAX_REPORTED]:
            print("  " + item, file=out)
    if not result.findings:
        return 0
    print("privacy check: blocked, %d finding(s):" % len(result.findings), file=out)
    for finding in result.findings[:MAX_REPORTED]:
        if finding.kind == "term":
            what = 'term "%s"' % finding.label
        else:
            what = "pattern %s" % finding.label
        print("  %s: %s" % (finding.where, what), file=out)
    if len(result.findings) > MAX_REPORTED:
        print("  ... and %d more" % (len(result.findings) - MAX_REPORTED), file=out)
    print("privacy check: remove the text from those commits, then push again.", file=out)
    return 1


def main(argv: Optional[List[str]] = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) < 2 or args[0] not in ("pre-push", "scan"):
        print(USAGE, file=sys.stderr)
        return 2
    try:
        repo = repository_root(Path("."))  # not Path.cwd(): it raises when the directory is gone
        terms = load_terms(terms_file_from_git(repo))
        if args[0] == "pre-push":
            result = check_pre_push(repo, args[1], sys.stdin, terms)
        else:
            shas = _git(repo, "rev-list", *args[1:]).split()
            result = scan_commits(repo, shas, terms)
    except (TermsError, GitError) as exc:
        print("privacy check: %s" % exc, file=sys.stderr)
        return 2
    return _report(result, sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
