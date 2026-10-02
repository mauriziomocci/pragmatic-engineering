"""Tests for tools/privacy_check.py: terms, generic patterns, pre-push and scan."""
import subprocess
import time
from pathlib import Path

import pytest

import privacy_check as pc
from support import REPO_ROOT, commit, git, init_repo, run_script

SCRIPT = REPO_ROOT / "tools" / "privacy_check.py"
TERM = "Zorblax"  # synthetic private term, never a real name
HOME_PATH = "/" + "Users" + "/alice/project/file.txt"
GITHUB_TOKEN = "gh" + "p_" + "A1b2C3d4" * 5


def configure_terms(repo: Path, tmp_path: Path, *terms: str) -> Path:
    terms_file = tmp_path / "private-terms.txt"
    terms_file.write_text("\n".join(terms) + "\n", encoding="utf-8")
    git(repo, "config", "pe.privateTermsFile", str(terms_file))
    return terms_file


def push_lines(*lines):
    return "".join(" ".join(parts) + "\n" for parts in lines)


def new_branch(tip: str, ref: str = "refs/heads/main"):
    return (ref, tip, ref, pc.ZERO_SHA)


def run_pre_push(repo: Path, stdin: str):
    return run_script(SCRIPT, ["pre-push", "origin", "https://example.invalid/r.git"], cwd=repo, stdin=stdin)


def fast_import(repo: Path, count: int, ref: str) -> None:
    """Create ``count`` linear commits on ``ref`` in one git process."""
    chunks = []
    for i in range(1, count + 1):
        message = ("commit %d\n" % i).encode()
        body = ("line %d\n" % i).encode()
        chunks.append(
            b"commit %s\nmark :%d\ncommitter Test <test@example.com> %d +0000\n"
            % (ref.encode(), i, 1700000000 + i)
        )
        chunks.append(b"data %d\n%s" % (len(message), message))
        if i > 1:
            chunks.append(b"from :%d\n" % (i - 1))
        chunks.append(b"M 100644 inline file%d.txt\ndata %d\n%s\n" % (i, len(body), body))
    subprocess.run(
        ["git", "fast-import", "--quiet"], cwd=str(repo), input=b"".join(chunks),
        check=True, capture_output=True,
    )


def test_load_terms_handles_bom_crlf_blank_and_comments(tmp_path):
    path = tmp_path / "terms.txt"
    raw = "﻿# private names\r\nZorblax\r\n\r\n  Quuxcorp  \r\n# note\r\nzorblax\r\n"
    path.write_bytes(raw.encode("utf-8"))
    assert pc.load_terms(path) == ["Zorblax", "Quuxcorp"]


def test_load_terms_fails_on_empty_or_missing_file(tmp_path):
    empty = tmp_path / "empty.txt"
    empty.write_text("# only comments\n\n", encoding="utf-8")
    with pytest.raises(pc.TermsError):
        pc.load_terms(empty)
    with pytest.raises(pc.TermsError):
        pc.load_terms(tmp_path / "missing.txt")


def test_terms_with_regex_metacharacters_match_literally():
    assert pc.find_terms("we ship C++ code", ["C++"]) == ["C++"]
    assert pc.find_terms("value axb here", ["a.b"]) == []
    assert pc.find_terms("value a.b here", ["a.b"]) == ["a.b"]


@pytest.mark.parametrize("text,expected", [
    ("Zorblax", True),
    ("ZORBLAX rocks", True),
    ("the zorblax_api module", True),
    ("zorblax-client", True),
    ("class ZorblaxExporter:", True),
    ("IoZorblax", True),
    ("zorblaxing", False),
    ("prezorblax", False),
])
def test_word_boundaries_for_names(text, expected):
    assert (pc.find_terms(text, [TERM]) == [TERM]) is expected


@pytest.mark.parametrize("text,expected", [
    ("QX-123", True),
    ("QX123", True),
    ("see qx-7", True),
    ("QXTRA", False),
    ("aqx-1", False),
])
def test_word_boundaries_for_ticket_prefixes(text, expected):
    assert (pc.find_terms(text, ["QX"]) == ["QX"]) is expected


def test_generic_patterns_find_home_paths_and_tokens():
    assert pc.find_generic("open " + HOME_PATH) == ["home-path-macos"]
    assert pc.find_generic("token=" + GITHUB_TOKEN) == ["github-token"]
    project_dir = "-" + "Users" + "-alice-Documents-work"
    assert pc.find_generic("~/.claude/projects/" + project_dir) == ["claude-project-dir"]
    key_block = "-----BEGIN " + "OPENSSH PRIVATE KEY-----"
    assert pc.find_generic(key_block) == ["private-key-block"]


def test_generic_patterns_ignore_portable_paths():
    assert pc.find_generic("edit ~/.claude/CLAUDE.md and $HOME/.config/x") == []


def test_scan_text_reports_the_pattern_name_not_the_secret():
    findings = pc.scan_text("key " + GITHUB_TOKEN, [TERM], "commit x message")
    assert findings == [pc.Finding("commit x message", "pattern", "github-token")]


def test_terms_file_from_git_requires_the_config_key(tmp_path):
    repo = init_repo(tmp_path / "repo")
    with pytest.raises(pc.TermsError, match="git config pe.privateTermsFile"):
        pc.terms_file_from_git(repo)


def test_terms_file_inside_the_repository_is_refused(tmp_path):
    repo = init_repo(tmp_path / "repo")
    (repo / "terms.txt").write_text("Zorblax\n", encoding="utf-8")
    git(repo, "config", "pe.privateTermsFile", "terms.txt")
    with pytest.raises(pc.TermsError, match="outside the repository"):
        pc.terms_file_from_git(repo)


def test_terms_file_path_expands_tilde(tmp_path, monkeypatch):
    home = tmp_path / "home"
    (home / ".config").mkdir(parents=True)
    (home / ".config" / "terms.txt").write_text("Zorblax\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    repo = init_repo(tmp_path / "repo")
    git(repo, "config", "pe.privateTermsFile", "~/.config/terms.txt")
    assert pc.terms_file_from_git(repo) == (home / ".config" / "terms.txt").resolve()


def test_clean_push_exits_zero_silently(tmp_path):
    repo = init_repo(tmp_path / "repo")
    configure_terms(repo, tmp_path, TERM)
    tip = commit(repo, {"a.txt": "clean\n"}, "clean change")
    proc = run_pre_push(repo, push_lines(new_branch(tip)))
    assert proc.returncode == 0, proc.stderr
    assert proc.stderr == ""


def test_term_in_an_old_commit_blocks_the_push(tmp_path):
    repo = init_repo(tmp_path / "repo")
    configure_terms(repo, tmp_path, TERM)
    commit(repo, {"notes.txt": "built for Zorblax\n"}, "add notes")
    tip = commit(repo, {"notes.txt": "built for a client\n"}, "neutral wording")
    proc = run_pre_push(repo, push_lines(new_branch(tip)))
    assert proc.returncode == 1
    assert 'notes.txt:1: term "Zorblax"' in proc.stderr


def test_term_in_a_commit_message_blocks_the_push(tmp_path):
    repo = init_repo(tmp_path / "repo")
    configure_terms(repo, tmp_path, TERM)
    tip = commit(repo, {"a.txt": "neutral\n"}, "fix the Zorblax import")
    proc = run_pre_push(repo, push_lines(new_branch(tip)))
    assert proc.returncode == 1
    assert 'message: term "Zorblax"' in proc.stderr


def test_term_in_a_branch_name_blocks_the_push(tmp_path):
    repo = init_repo(tmp_path / "repo")
    configure_terms(repo, tmp_path, TERM)
    tip = commit(repo, {"a.txt": "neutral\n"}, "neutral")
    proc = run_pre_push(repo, push_lines(new_branch(tip, "refs/heads/zorblax-fix")))
    assert proc.returncode == 1
    assert 'ref refs/heads/zorblax-fix: term "Zorblax"' in proc.stderr


def test_term_in_an_annotated_tag_message_blocks_the_push(tmp_path):
    repo = init_repo(tmp_path / "repo")
    configure_terms(repo, tmp_path, TERM)
    commit(repo, {"a.txt": "neutral\n"}, "neutral")
    git(repo, "tag", "-a", "v1.0", "-m", "release for Zorblax")
    tag_sha = git(repo, "rev-parse", "v1.0").strip()
    proc = run_pre_push(repo, push_lines(new_branch(tag_sha, "refs/tags/v1.0")))
    assert proc.returncode == 1
    assert 'tag refs/tags/v1.0 message: term "Zorblax"' in proc.stderr


def test_term_in_the_author_identity_blocks_the_push(tmp_path):
    repo = init_repo(tmp_path / "repo")
    configure_terms(repo, tmp_path, TERM)
    commit(repo, {"a.txt": "neutral\n"}, "neutral")
    git(repo, "-c", "user.email=dev@zorblax.example", "commit", "-q", "--allow-empty", "-m", "neutral")
    tip = git(repo, "rev-parse", "HEAD").strip()
    proc = run_pre_push(repo, push_lines(new_branch(tip)))
    assert proc.returncode == 1
    assert 'header: term "Zorblax"' in proc.stderr


def test_term_in_the_tagger_identity_blocks_the_push(tmp_path):
    repo = init_repo(tmp_path / "repo")
    configure_terms(repo, tmp_path, TERM)
    commit(repo, {"a.txt": "neutral\n"}, "neutral")
    git(repo, "-c", "user.email=release@zorblax.example", "tag", "-a", "v1.0", "-m", "release")
    tag_sha = git(repo, "rev-parse", "v1.0").strip()
    proc = run_pre_push(repo, push_lines(new_branch(tag_sha, "refs/tags/v1.0")))
    assert proc.returncode == 1
    assert 'tag refs/tags/v1.0 header: term "Zorblax"' in proc.stderr


def test_empty_file_in_a_folder_named_with_a_term_blocks_the_push(tmp_path):
    repo = init_repo(tmp_path / "repo")
    configure_terms(repo, tmp_path, TERM)
    tip = commit(repo, {"docs/zorblax/.gitkeep": ""}, "keep the folder")
    proc = run_pre_push(repo, push_lines(new_branch(tip)))
    assert proc.returncode == 1
    assert 'path docs/zorblax/.gitkeep: term "Zorblax"' in proc.stderr


def test_home_path_in_a_commit_blocks_the_push_without_echoing_it(tmp_path):
    repo = init_repo(tmp_path / "repo")
    configure_terms(repo, tmp_path, TERM)
    tip = commit(repo, {"cfg.txt": "path = " + HOME_PATH + "\n"}, "config")
    proc = run_pre_push(repo, push_lines(new_branch(tip)))
    assert proc.returncode == 1
    assert "cfg.txt:1: pattern home-path-macos" in proc.stderr
    assert "/alice/" not in proc.stderr


def test_commits_already_on_the_remote_are_not_rescanned(tmp_path):
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    repo = init_repo(tmp_path / "repo")
    configure_terms(repo, tmp_path, TERM)
    old = commit(repo, {"a.txt": "Zorblax legacy\n"}, "old public commit")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-q", "origin", "main")
    tip = commit(repo, {"b.txt": "clean\n"}, "clean change")
    proc = run_pre_push(repo, push_lines(("refs/heads/main", tip, "refs/heads/main", old)))
    assert proc.returncode == 0, proc.stderr


def test_deleting_a_branch_passes(tmp_path):
    repo = init_repo(tmp_path / "repo")
    configure_terms(repo, tmp_path, TERM)
    old = commit(repo, {"a.txt": "neutral\n"}, "neutral")
    proc = run_pre_push(repo, push_lines(("(delete)", pc.ZERO_SHA, "refs/heads/zorblax", old)))
    assert proc.returncode == 0, proc.stderr


def test_deleting_a_file_named_with_a_term_passes(tmp_path):
    remote = tmp_path / "remote.git"
    git(tmp_path, "init", "-q", "--bare", str(remote))
    repo = init_repo(tmp_path / "repo")
    configure_terms(repo, tmp_path, TERM)
    old = commit(repo, {"zorblax-notes.txt": "old\n"}, "old public commit")
    git(repo, "remote", "add", "origin", str(remote))
    git(repo, "push", "-q", "origin", "main")
    git(repo, "rm", "-q", "zorblax-notes.txt")
    tip = commit(repo, {}, "remove the old notes")
    proc = run_pre_push(repo, push_lines(("refs/heads/main", tip, "refs/heads/main", old)))
    assert proc.returncode == 0, proc.stderr


def test_only_the_second_of_two_pushed_refs_carries_the_term(tmp_path):
    repo = init_repo(tmp_path / "repo")
    configure_terms(repo, tmp_path, TERM)
    clean = commit(repo, {"a.txt": "clean\n"}, "clean")
    git(repo, "switch", "-q", "-c", "side")
    dirty = commit(repo, {"b.txt": "Zorblax\n"}, "side work")
    proc = run_pre_push(repo, push_lines(new_branch(clean), new_branch(dirty, "refs/heads/side")))
    assert proc.returncode == 1
    assert 'b.txt:1: term "Zorblax"' in proc.stderr


def test_malformed_pre_push_line_fails_closed(tmp_path):
    repo = init_repo(tmp_path / "repo")
    configure_terms(repo, tmp_path, TERM)
    commit(repo, {"a.txt": "neutral\n"}, "neutral")
    proc = run_pre_push(repo, "garbage\n")
    assert proc.returncode == 2


def test_missing_terms_configuration_fails_closed(tmp_path):
    repo = init_repo(tmp_path / "repo")
    tip = commit(repo, {"a.txt": "neutral\n"}, "neutral")
    proc = run_pre_push(repo, push_lines(new_branch(tip)))
    assert proc.returncode == 2
    assert "git config pe.privateTermsFile" in proc.stderr


def test_binary_files_are_skipped_and_reported(tmp_path):
    repo = init_repo(tmp_path / "repo")
    configure_terms(repo, tmp_path, TERM)
    tip = commit(repo, {"image.bin": b"\x00\x01Zorblax\x00" * 100}, "add binary")
    proc = run_pre_push(repo, push_lines(new_branch(tip)))
    assert proc.returncode == 0, proc.stderr
    assert "binary file(s) not scanned" in proc.stderr
    assert "image.bin" in proc.stderr


def test_many_commits_complete_in_reasonable_time(tmp_path):
    repo = init_repo(tmp_path / "repo")
    configure_terms(repo, tmp_path, TERM)
    fast_import(repo, 300, "refs/heads/big")
    tip = git(repo, "rev-parse", "refs/heads/big").strip()
    started = time.monotonic()
    proc = run_pre_push(repo, push_lines(new_branch(tip, "refs/heads/big")))
    elapsed = time.monotonic() - started
    assert proc.returncode == 0, proc.stderr
    assert elapsed < 60, elapsed


def test_large_diff_is_streamed_and_scanned_to_the_end(tmp_path):
    repo = init_repo(tmp_path / "repo")
    configure_terms(repo, tmp_path, TERM)
    big = "neutral line\n" * 200000 + "Zorblax at the end\n"
    tip = commit(repo, {"big.txt": big}, "big file")
    proc = run_pre_push(repo, push_lines(new_branch(tip)))
    assert proc.returncode == 1
    assert 'big.txt:200001: term "Zorblax"' in proc.stderr


def test_line_numbers_ignore_the_inter_hunk_context_setting(tmp_path):
    repo = init_repo(tmp_path / "repo")
    configure_terms(repo, tmp_path, TERM)
    git(repo, "config", "diff.interHunkContext", "5")
    commit(repo, {"f.txt": "one\ntwo\nthree\nfour\nfive\n"}, "base")
    tip = commit(repo, {"f.txt": "ONE\ntwo\nthree\nZorblax\nfive\n"}, "edit two lines")
    proc = run_pre_push(repo, push_lines(new_branch(tip)))
    assert proc.returncode == 1
    assert 'f.txt:4: term "Zorblax"' in proc.stderr


def test_pre_push_in_repo_path_with_spaces_apostrophe_and_accents(tmp_path):
    repo = init_repo(tmp_path / "my repo's àccents")
    configure_terms(repo, tmp_path, TERM)
    tip = commit(repo, {"dir with space/file's name.txt": "Zorblax\n"}, "add")
    proc = run_pre_push(repo, push_lines(new_branch(tip)))
    assert proc.returncode == 1
    assert "dir with space/file's name.txt:1" in proc.stderr


def test_content_added_only_by_a_merge_is_scanned(tmp_path):
    repo = init_repo(tmp_path / "repo")
    configure_terms(repo, tmp_path, TERM)
    commit(repo, {"base.txt": "base\n"}, "base")
    git(repo, "switch", "-q", "-c", "side")
    commit(repo, {"side.txt": "side\n"}, "side")
    git(repo, "switch", "-q", "main")
    commit(repo, {"main.txt": "main\n"}, "main")
    git(repo, "merge", "-q", "--no-ff", "--no-commit", "side")
    (repo / "merge-only.txt").write_text("Zorblax\n", encoding="utf-8")
    git(repo, "add", "merge-only.txt")
    git(repo, "commit", "-q", "-m", "merge side")
    tip = git(repo, "rev-parse", "HEAD").strip()
    proc = run_pre_push(repo, push_lines(new_branch(tip)))
    assert proc.returncode == 1
    assert 'merge-only.txt:1: term "Zorblax"' in proc.stderr


def test_scan_command_checks_a_revision_range(tmp_path):
    repo = init_repo(tmp_path / "repo")
    configure_terms(repo, tmp_path, TERM)
    base = commit(repo, {"a.txt": "Zorblax\n"}, "before the range")
    commit(repo, {"b.txt": "clean\n"}, "inside the range")
    inside = run_script(SCRIPT, ["scan", "%s..HEAD" % base], cwd=repo)
    assert inside.returncode == 0, inside.stderr
    everything = run_script(SCRIPT, ["scan", "HEAD"], cwd=repo)
    assert everything.returncode == 1


def test_unknown_subcommand_is_a_usage_error(tmp_path):
    proc = run_script(SCRIPT, ["bogus"], cwd=tmp_path)
    assert proc.returncode == 2
