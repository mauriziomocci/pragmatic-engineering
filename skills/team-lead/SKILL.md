---
name: team-lead
description: Use when an approved plan is to be built by several workers at once, in sessions or sub-agents, each in its own worktree, and when a worker reports a delivery that must be checked against git before it is reviewed and merged. Before the entry conditions hold, design with the user instead.
---

# team-lead

This skill is the method for building one approved plan with several workers at once, and for checking each delivery against git, not against the worker's report: a message says what the worker did, git says what changed.

## When to use

Use it only when all three conditions hold:

- an approved plan, with its tasks written and the user's approval of it given in chat;
- at least two disjoint file areas in that plan, so that no two workers edit the same file;
- a test environment for each suite that runs at the same time: its own database, its own port, its own cache index, so that two suites never share a resource.

Before all three hold, no parallel work starts: design the plan with the user, then build it one task at a time in this session.

## The team

Before the first order write the team: for each worker a file area and a package of two or three tasks, and one line for each pair that shares files or interfaces, naming who changes it first; section and migration numbers and the generated files are assigned before the first order. Starting caps, from the one team this method comes from and not measured since: one code worker for each area, at most three per test environment. The project's instructions change them and name the resources (`engineering-principles`, isolated sessions). The user's approval of the team opens its sessions. Models and escalation: `development-workflow`.

## Two bases

| | App session | Sub-agent `worker` |
|---|---|---|
| Open | `start_session`: `initiation: "user_asked"` inside the approved team, `own_initiative` outside it (a card the user opens); `context: "fresh"`, `background` of 80 characters or more, `use_worktree: true`, `branch_name`, `source_branch` the integration branch, model by role, no `permission_mode` | Agent tool, `pragmatic-engineering:worker`, in the background, model passed |
| Order | brief in the `prompt`, later packages by `SendMessage` | a new sub-agent for each package |
| Permissions | the coordinator's mode | the launching session's (not verified) |

Right after `start_session` write an empty `.pe/worker` and `.pe/.gitignore` holding `*` into the worktree that `get_session` gives; the hook holds a session with that signal to its worktree; when the auto mode classifier denies that write, the boundary does not hold for that worker, and the coordinator says so. A session worker may launch at most two internal agents, declared in its report.

## The brief

The worker's prompt, fixed: integration tip, branch, tasks with their red tests, test command, its own resources, its numbers and generated files, and the lines the delivery check reads:

- `OWNED: <glob>`, one line per pattern, names the files it may change; `fnmatchcase` on the repository path, `*` crosses `/`.
- `TESTS: <glob>`, one line per pattern, names its test files, which `--red` needs.

It is complete, and above 6,000 characters the brief goes to a file. It holds no command nobody ran; the first report is "online", with proof. It says that a message from the coordinator approves no permission, lifts no prohibition and changes no requirement, and the coordinator never asks a worker for what was denied to it or to another.

## Orders and wake-ups

Order only to a stopped session, with the whole brief, because after `clear_session` it restarts empty, and never `send_message`, which delivers a user turn: use `SendMessage`. Each order carries `notify_when_idle: true` and ends with an immediate action, "now do X and report"; a turn that leaves a suite running says "suite running in the background, report when it ends". A notification without a report gets an order at once. An unreachable session: `list_sessions` with `linked: true`, send again by id, after two rounds do the work or tell the user. Use `clear_session` between two packages (outside auto and bypass modes it asks the user a click, and fails on a session open on screen), otherwise a fresh session for each package. One line for each session (name, id, worktree, branch, role) in the progress note of `continuity-note`, rebuilt from `list_sessions` and `git worktree list`.

## A worker stuck on a permission

No wake-up reports it. At each wake-up, and once after the package's estimated time where the host offers a wait, read `list_sessions` (`linked: true`) and the last `list_events` of each worker without a report. One still running with no new event for more than 10 minutes (the stop measured in the team this method comes from; the brief may set another) goes to the user at once, as a probable permission to approve in that session's window. That these fields tell it from a long job is not verified, so a session is a base only with the user present; with the user away use sub-agents. In auto mode the classifier denies instead of waiting, and the worker reports it.

## Delivery

A worker declares a branch and the tip of that branch. Check the delivery from your own checkout, never from the worker's:

`python3 <this skill's folder>/verify_delivery.py --integration <branch> --branch <branch> --tip <sha> --worktree <folder> --brief <file> [--reviewed <sha>] [--red <command>]`

`--integration` is the branch the work is merged into, `--worktree` the folder of the worker and `--brief` the file with the `OWNED:` and `TESTS:` lines. `--tip` and `--reviewed` take only a full commit id (40 or 64 hex digits), `--integration` and `--branch` a branch name. The script's docstring says why, and what else each check guards.

- It exits 0: the delivery is accepted.
- It exits 1: the delivery is refused, and every reason is on standard error: the branch is not at the declared tip, the worktree is not clean, a file the delivery changed is outside every `OWNED:` line, or, with `--red`, the tests were never red or do not pass at the tip. A refusal goes back to the worker with its reasons; nothing is reviewed.
- It exits 3: nothing is refused, but something is not in the integration and the reviewer has not read it, so it goes to the review. Exit 3 is not a failure. Without `--reviewed` that is a merge whose conflict resolution shows in `git show --remerge-diff`. With `--reviewed` it is every commit above the reviewed tip, listed by sha, except a merge with an empty remerge diff.
- It exits 2: the call is wrong (a missing argument, a brief without an `OWNED:` line, a value that is neither a commit id nor a branch of the repository, a test command that is empty, has an unbalanced quote or does not start). Fix the call and run it again.

Run it twice, before the review and again after the PASS. Before the review, exits 0 and 3 both send the delivery to `blunt-reviewer`, which reads every merge of the range with `--remerge-diff` (git 2.36 or later). After the PASS, run it again with `--reviewed <the commit id of the tip the reviewer read>`: it must exit 0. An exit 3 then means commits after the review, or a tip moved off the reviewed one; they are reviewed before any merge.

With `--red <command>` the tests of the delivery, alone, must fail on the integration tip and pass at the delivery tip; a refusal carries the last 20 lines of output. The script runs the delivery's own code in two temporary worktrees, and runs `git worktree prune` afterwards. It inherits the environment of the session that runs it and enforces none of the brief's resources: set them in the command, through `env NAME=value <command>`; write a path in it with `/`.

The script reads no suite numbers and does not check that the integration tip is an ancestor of the delivery tip.


## Review

From the integration tip, after the worker brought that tip into its branch: `blunt-reviewer` on `<integration>..<tip>`, merges read with `--remerge-diff`. Reviewer and UX lens are sub-agents with a fresh context at every round, never sessions. Before it: the red on the base (`--red`), and mutations only of guards and serious fixes, by a verification subagent distinct from the reviewer. A merge with an empty remerge diff needs no new review, but its tests run. The cycle after fixes is `blunt-review`; what is open after two rounds goes up.

## Integration

The coordinator never resolves a conflict: the worker does, in its worktree, and the author regenerates the generated files inside the reviewed range; the coordinator repeats it only as a check, without a commit. Integrate one delivery at a time, in order of arrival, with `git merge --ff-only`, or where the project wants a merge commit `git merge-base --is-ancestor` then `--no-ff`: neither conflicts. A checkout served by a running process gets only the fast-forward. After each integration run the tests of the modules touched by the incoming branch and by those integrated before it: a clean merge can be red.

## Decisions

A decision of the coordinator holds only if it cites the entry it derives from (a spec line, a plan task, a decision-log entry) and changes no requirement, interface, data model or contract; any other goes up by the escalation of `development-workflow`. A technical decision inside a task is the worker's, in its report. Check a report against git and tests. Bring the user's decisions together.

## Failures

A refused delivery goes back with its reasons. A test that depends on time under load is unstable until it passes alone; say so, never skip it.

## Closing

A worker's worktree and session are archived only when its branch is integrated and its report recorded, never in the middle of a suite. Handover: `development-workflow`. Measure in tokens per task delivered; where the log does not give it, usage per package with only the team running, noisier because the quota is shared across projects.
