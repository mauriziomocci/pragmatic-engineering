# pragmatic-engineering

A Claude Code plugin under construction. Its goal is to put a disciplined engineering method in order and to bring it to every agent of a session. It is not usable yet: this README describes only what exists, and it grows with each increment.

## What exists today

The repository's own privacy protection, used in the maintainer's clone:

- `tools/privacy_check.py` checks everything a push sends to the remote (for each pushed commit the added lines, the message, the author and committer names and emails, and the path of every file added or changed; the reference names; annotated tags) for the maintainer's private terms, listed in a file outside the repository that `git config pe.privateTermsFile` names, and for generic patterns such as home paths and recognisable tokens. It skips binary files and says so, and it fails closed.
- `tools/install_dev_hooks.py` copies that check, the project hook below and their filters into the clone's git directory, outside the working tree, and installs the `pre-push` hook that runs the copy; a change to the working tree takes effect only when the installer runs again. If the copy goes missing or breaks, a check that cannot run refuses the push or the tool; running `python3 tools/install_dev_hooks.py` again from your own terminal restores it. It refuses to overwrite a `pre-push` hook it did not write, and to install while `core.hooksPath` is set.
- `tools/dev_guard.py` is a Claude Code `PreToolUse` hook, registered in the maintainer's `.claude/settings.local.json` (a file git ignores) as `python3 "<copy>/tools/dev_guard.py" || exit 2`, so any exit other than 0 blocks. It keeps an agent from skipping the check or switching hooks off, blocks MCP tools that write straight to a remote and raw API calls that write to pull requests, and checks the text of pull and merge request commands (`gh`, `glab` and MCP tools). It reads that text only where it is written, and blocks what the shell fills in at run time, with the hint to write it to a file first. The exact rules are in the module docstrings of `tools/dev_guard.py` and `lib/pe_guard/filters.py`.

## Not covered

The filters read text and defend against an agent's haste, not against a determined bypass. Open, some by design and some not yet closed:

- other `gh` and `glab` commands that write text: releases, issues, gists, labels, repository settings;
- MCP tools that create branches or other objects, write issues, or comment on and review pull requests;
- raw API writes outside pull requests (repository contents, references, GitLab files and commits, a GraphQL commit mutation), and any call by `curl` or another client;
- `core.hooksPath` edited with the file tools (`git config` and `git -c` are blocked);
- `--no-verify` from the maintainer's own terminal;
- the check edited in the working tree, then installed: nothing guards the installer yet;
- files that a `-diff` rule of `.gitattributes` makes git report as binary: skipped, and the skip is listed;
- a term in lower case inside a longer word (`myterm`) or with an ending (`terms`): terms match as whole words, in any letter case, with camel-case capitals as boundaries, so such forms must be listed too;
- forms the hook cannot see in the command: a call hidden in a script, alias, function or variable, or built inside `sh -c`; quoted or escaped words; a folder change by a program other than `cd`; brace expansion and globs; a body file written under another spelling of its name;
- the `gh` flags that fill a pull request from elsewhere: templates, attachments, an earlier failed run, an editor, the browser, and commit messages, which the pre-push checks;
- sessions where the project hook is not loaded: it runs in the main clone and in worktree sessions started from the Claude desktop app (they read the main checkout's settings), not in a terminal session inside a linked worktree, where the pre-push still runs.

The exact lists are in the module docstrings named above.

## Tests

`python3 -m pytest -q` from the repository root. Requirements: Python 3.9 or later, pytest 7 or later, git 2.32 or later.

## License

MIT, see [LICENSE](LICENSE).
