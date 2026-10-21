# pragmatic-engineering

A Claude Code plugin under construction. Its goal is to put a disciplined engineering method in order and to bring it to every agent of a session. It is not usable yet: this README describes only what exists, and it grows with each increment.

## What exists today

The repository's own privacy protection, used in the maintainer's clone:

- `tools/privacy_check.py` checks everything a push sends to the remote (for every pushed commit the added lines, the message, the author and committer names and emails and the path of every file it adds or changes; the reference names; the tagger and message of annotated tags) for the maintainer's private terms, listed in a file outside the repository that `git config pe.privateTermsFile` names, and for generic patterns such as home paths and recognisable tokens. It skips binary files and says so, and it fails closed.
- `tools/install_dev_hooks.py` copies that check, the project hook below and their shared filters into the clone's git directory, outside the working tree, and installs the clone's `pre-push` hook, which runs that copy. A change to the working tree takes effect only when the installer runs again. If the copy goes missing, every push and every tool the project hook watches is refused, and a push check that cannot run refuses the push as well; running `python3 tools/install_dev_hooks.py` again from your own terminal, at the root of the clone, restores the copy. The installer refuses to overwrite a `pre-push` hook it did not write, and to install while `core.hooksPath` is set.
- `tools/dev_guard.py` is a Claude Code `PreToolUse` hook, meant to be registered in the maintainer's `.claude/settings.local.json` (a file git ignores, which the installer does not write) and run from the same copy. It keeps an agent from skipping the check or switching hooks off, blocks MCP tools that write straight to a remote and raw API calls that write to pull requests, and runs the check on the text of pull requests. It reads that text only where it is written: in the command, or in a body file named by `--body-file` or `-F`. Text that the shell would fill in when the command runs blocks, with the hint to write the text to a file first, in a separate step: a here-document, standard input, a substitution, a variable and `xargs` followed by `gh` or `glab` all do. It checks the text of `gh pr create/new/edit/merge/comment/review/close/reopen/revert`, of `glab mr create/new/update/merge/note` and of the MCP tools that create, update or merge pull and merge requests.

## Not covered

The filters read text, and they defend against an agent's haste, not against a determined bypass. These cases are open, some by design and some not yet closed:

- releases and their notes (`gh release create`, `gh release edit`), and issues (`gh issue`, `glab issue`);
- MCP tools that create branches or other objects on the server, such as `create_branch`, and MCP tools that write issues or the comments and reviews of pull requests;
- raw API calls that write anywhere but pull requests, such as `gh api` or `glab api` on repository contents and references (`contents`, `git/refs`), GitLab's repository files and commits or a GraphQL mutation that creates a commit, and any call made by `curl` or another client;
- a git configuration file edited with the file tools to move the hooks folder (`core.hooksPath`), while the same setting through `git config` or `git -c` is blocked;
- `--no-verify` from the maintainer's own terminal;
- the check edited in the working tree: the file tools can change `tools/privacy_check.py` and a session can then run the installer, which puts the edited check into the copy; the installer is the maintainer's step and nothing guards it yet;
- files that a `-diff` rule in the clone's own `.gitattributes` makes git report as binary: they are skipped, and the skip is listed;
- forms the hook cannot see in the command: a `gh` call inside a script file, an alias, a function or a variable; a quoted or escaped option name (`'-F' -`); a quoted `gh` or subcommand word (`gh pr "create"`); a folder change by a program other than `cd`, `pushd` or `chdir` (`env -C`); another program that runs `gh` and supplies its text, other than `xargs` (`find -exec`, `parallel`); a term built from pieces by brace expansion or a glob; and a raw API call put together inside `sh -c`, `eval` or a pipe to `sh`;
- a step of the same command that writes the body file under another spelling of its name, or a script that does;
- the `gh` flags that fill a pull request from elsewhere, as read in the help of gh 2.102.0: `--fill`, `--fill-first` and `--fill-verbose` take the commit messages, which the pre-push checks when they are pushed; `--template` takes the starting body from the file it names, `--attach` appends the files it names, `--recover` takes the input of an earlier failed run, and `--editor` and `--web` take the text typed in an editor or in the browser;
- the project hook in sessions where it is not loaded: it runs in sessions opened in the main clone, and in worktree sessions started from the Claude desktop app, for which Claude Code reads the main checkout's settings; it does not run in a session started from a terminal inside a linked worktree, where the pre-push still runs.

## Tests

`python3 -m pytest -q` from the repository root. Requirements: Python 3.9 or later, pytest 7 or later, git 2.32 or later.

## License

MIT, see [LICENSE](LICENSE).
