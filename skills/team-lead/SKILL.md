---
name: team-lead
description: Use when an approved plan is to be built by several workers at once, in sessions or sub-agents, each in its own worktree, and when a worker reports a delivery that must be checked against git before it is reviewed and merged. Before the entry conditions hold, design with the user instead.
---

# team-lead

This skill is the method for building one approved plan with several workers at once, and for checking each delivery against git instead of against the worker's report. A worker's message says what it did; git says what changed. Two parallel workers that edit the same file, or a merge nobody read, cost more than the time the parallel work saved.

## When to use

Use it only when all three conditions hold:

- an approved plan, with its tasks written and the user's approval of it given in chat;
- at least two disjoint file areas in that plan, so that no two workers edit the same file;
- a test environment for each suite that runs at the same time: its own database, its own port, its own cache index, so that two suites never share a resource.

Before all three hold, no parallel work starts: design the plan with the user, then build it one task at a time in this session.

Each worker gets a brief that carries its area and its tests as lines the delivery check reads:

- `OWNED: <glob>`, one line per pattern, names the files the worker may change. The pattern is compared with `fnmatchcase` on the repository path, and `*` also crosses `/`.
- `TESTS: <glob>`, one line per pattern, names the test files of the worker, which `--red` needs.

## Delivery

A worker declares a branch and the tip of that branch. Check the delivery from your own checkout, never from the worker's:

`python3 <this skill's folder>/verify_delivery.py --integration <branch> --branch <branch> --tip <sha> --worktree <folder> --brief <file> [--reviewed <sha>] [--red <command>]`

`--integration` is the branch the work is merged into, `--worktree` the folder of the worker and `--brief` the file with the `OWNED:` and `TESTS:` lines. `--tip` and `--reviewed` take only a full commit id (40 or 64 hex digits), because a branch is what the worker moves and `--reviewed <branch>` would read the new tip and find nothing unread. `--integration` and `--branch` take a branch name, read only as `refs/heads/<name>` with or without that prefix: a tag, `refs/<name>` or `HEAD~1` never stands in for a branch, because a worker can create the first two. Git is read with `--no-replace-objects`, and `git status` runs with `--no-optional-locks`, so it does not refresh the worker's index. Without `--red` the script only reads the repository.

- It exits 0: the delivery is accepted.
- It exits 1: the delivery is refused, and every reason is on standard error: the branch is not at the declared tip, the worktree is not clean, a file the delivery changed is outside every `OWNED:` line, or, with `--red`, the tests were never red or do not pass at the tip. A refusal goes back to the worker with its reasons; nothing is reviewed. The files the delivery changed are counted from its merge base with the integration, so a delivery that another worker's merge has overtaken is not blamed for that worker's files.
- It exits 3: nothing is refused, but something is not in the integration and the reviewer has not read it, so it goes to the review. Exit 3 is not a failure. Without `--reviewed` that is a merge whose conflict resolution shows in `git show --remerge-diff`. With `--reviewed` it is every commit above the reviewed tip, listed by sha, except a merge with an empty remerge diff.
- It exits 2: the call is wrong (a missing argument, a brief without an `OWNED:` line, a value that is neither a commit id nor a branch of the repository, a test command that is empty, has an unbalanced quote or does not start). Fix the call and run it again.

Run it twice, before the review and again after the PASS. Before the review, exits 0 and 3 both send the delivery to `blunt-reviewer`, which reads every merge of the range with `--remerge-diff` (git 2.36 or later). After the PASS, run it again with `--reviewed <the commit id of the tip the reviewer read>`: it must exit 0. An exit 3 then lists the commits added after the review that are not in the integration, or says that the tip does not descend from the reviewed tip (the branch was moved below or away from what was read); either way they are reviewed before anything is merged.

With `--red <command>` the script also checks that the worker's tests were red: it takes the changed files that match a `TESTS:` line, copies them from the tip into a temporary worktree of the integration tip, and requires the command to fail there and to pass in a temporary worktree of the delivery tip. A refusal carries the last 20 lines of the command's output. This changes the repository: the script adds the two temporary worktrees and removes them, and runs `git worktree prune`, which drops the records of every worktree of the repository whose folder is gone. It also runs the delivery's own code. The command is split with `shlex.split` and runs without a shell, so write a path in it with `/`, never with a backslash, which is an escape. It inherits the environment of the session that runs the script, and the script enforces none of the resources of the brief: set them in the command itself, through `env NAME=value <command>`, or in the environment.

The script does not read the numbers of the worker's suite and does not check that the integration tip is an ancestor of the delivery tip.
