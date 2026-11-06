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

`python3 <this skill's folder>/verify_delivery.py --integration <rev> --branch <branch> --tip <sha> --worktree <folder> --brief <file> [--reviewed <sha>] [--red <command>]`

`--integration` is the branch the work is merged into, `--worktree` the folder of the worker and `--brief` the file with the `OWNED:` and `TESTS:` lines. The script reads git and changes nothing. `--branch` is always read as `refs/heads/<branch>`. A bare name given to `--integration` or `--reviewed` that is both a branch and a tag exits 2, because git reads the tag first and a worker can create one; write the full ref name (`refs/heads/<name>`) or a sha.

- It exits 0: the delivery is accepted.
- It exits 1: the delivery is refused, and every reason is on standard error: the branch is not at the declared tip, the worktree is not clean, a file is outside every `OWNED:` line, or, with `--red`, the tests were never red or do not pass at the tip. A refusal goes back to the worker with its reasons; nothing is reviewed.
- It exits 3: nothing is refused, but a merge of the delivery has a conflict resolution that the reviewer has not read, shown by `git show --remerge-diff`. Exit 3 is not a failure: the delivery goes to the review.
- It exits 2: the call is wrong (a missing argument, a brief without an `OWNED:` line, a revision that is not a commit or is both a branch and a tag, a test command that does not start). Fix the call and run it again.

Run it twice, before the review and again after the PASS. Before the review, exits 0 and 3 both send the delivery to `blunt-reviewer`, which reads every merge of the range with `--remerge-diff` (git 2.36 or later). After the PASS, run it again with `--reviewed <the tip the reviewer read>`: it must exit 0. An exit 3 then means a merge was added or changed after the review, and that merge is reviewed before anything is merged.

With `--red <command>` the script also checks that the worker's tests were red. It takes the changed files that match a `TESTS:` line, copies them from the tip into a temporary worktree of the integration tip, and requires the command to fail there and to pass in a temporary worktree of the delivery tip. The command is split without a shell and runs with the resources named in the brief; the script chooses none.

The script does not read the numbers of the worker's suite and does not check that the integration tip is an ancestor of the delivery tip.
