---
name: safe-operations
description: Use before running a command or a tool that changes an external system - a deploy, a rollout, a migration, a data fix, a cluster, a cloud account, a tool with effects on end users - and, when office hours are set in git config pe.officeHours, before a push, a merge request, a pipeline, a tracker edit or a message. Verify and state the active target, dry run where one exists, say the blast radius and the way back first, prefer a dedicated resource to a shared one, get a separate explicit go for every run on production, never poll long operations, verify at every level afterwards, and outside office hours save work only as local commits.
---

# safe-operations

This skill is the method for acting on a system outside the repository: a command or a tool whose effect outlives the session. A wrong test run costs a minute. A wrong run against the wrong cluster or database costs other people's work, and some of it cannot be undone. The method asks for little each time, and nobody skips it.

## When to use

Load it before running a command or a tool that changes an external system: a deploy, a rollout, a migration, a data fix, a change on a cluster or a cloud account, a tool with effects on end users. Reading from such a system needs none of this; the first write does. When office hours are set, load it also before a push, a merge request, a pipeline, a tracker edit or a message.

## Before

1. Verify and state the active target: the cluster context, the cloud account or profile, the database, the environment. Verify it with a command that shows it, never from memory and never from what the previous session was doing, and write the result in the message. Name the target inside the command itself whenever the tool allows it.
2. Use a dry run where one exists (a plan, a preview, a diff against the live state) and read its output before running the real command.
3. Say the blast radius first: what the command touches beyond the task, and who notices if it fails. Say the way back: the exact steps that undo it. If there is no way back, say so and stop, because that is a decision for the user.
4. Prefer a dedicated resource (a namespace, a release, a controller, a load balancer, a storage class) to changing a shared one, and change a whole cluster only when the change is additive. The values, releases, load balancers, certificates and configurations of a shared component are never touched as a side effect, and each change to them has its own go.

## Production and shared systems

Approving a change is not approving its execution. "Yes, fix it" approves the content of the correction, not running it on production. Every run with effects on production or on a shared system asks for its own explicit go, even right after the user approved the change. The go covers that single run on that target: it does not carry over to the next run, and a go given for one target is not a go for another.

## Outside office hours

The window comes from `git config --get pe.officeHours`, two hours such as `06-21`, the second one outside the window: `06-21` runs from 06:00 up to 20:59; unset, or set to `none`, this section does not apply. Weekends and the dates of `pe.holidays` (entries separated by commas, each `MM-DD`, or `easter+N` and `easter-N` in days from Gregorian Easter) open at the hour of `pe.weekendFrom` instead, which defaults to the opening hour of the window. The time is read with `date`, never estimated, and Easter is computed, never recalled. A remote is personal only when every push URL it has starts with one of the values that `git config --get-all pe.personalRemotes` prints; without that key, no remote is personal.

Outside the window, work is saved only as local commits: no push to a remote that is not personal, no merge request, no pipeline, no tracker edit and no message. Unattended work runs only with the user's authorisation for that piece of work, with a start time and a hard stop, and it follows the approved spec and tasks to the letter, one task at a time, test first. An unforeseen technical case is decided by the review lens, provisionally and in writing; a case that would change the spec, an interface or the data model is parked, and the independent tasks go on. What breaks is fixed at its cause. An autonomy that opens `design` lifts the letter and the parking, the lenses deciding as `development-workflow` says, and the authorisation with its hard stop is still needed: a chat autonomy that covers the night is one, a profile never is.

Never outside the window, even with a go given during the day: merges into shared branches, writes to clusters or cloud accounts, deletions outside the worktree, irreversible actions, messages to people, credentials not already configured. At the hard stop every session commits locally at a clean point and stops. When the window opens, one report comes first: what was done with its confidence level, what was parked and why, the provisional decisions, the commits to re-create, the budget used and the tracker updates to make.

Commits made outside the window and never pushed are re-created inside it with their real dates, never faked ones, before the branch is integrated, with one command, `git rebase --exec "git commit --amend --no-edit --reset-author" <base>`, where `<base>` is the last commit already pushed: it amends each commit as it replays it, so both of its dates become the time of the moment. The dates of author and committer are checked again on the integrated branch before its push. Before long unattended work, ask the host to keep the machine awake. When the user says in chat that they are working outside the window, interactive work goes on, and the traces in company systems still wait for the window.

## Long operations

A long, asynchronous operation (a rollout, a migration, a pipeline) is not watched in a loop. Polling spends attention and tokens and adds nothing the user's own signal does not give. Say how the operation is checked (the command, the page, the end state to expect), then wait for the user's confirmation or for a notification. One check made because the user asked is not a loop.

## After

Verify at every level, not only at the first one that answers. A process that has started is not a responding service, and a service that responds does not prove the data is right. Walk up the levels: the job or process ran, the service answers, the answer carries the correct data, and the end user sees what was meant. Say which levels were verified, with the evidence for each, and which were not. A level that was not checked is reported as unchecked, never assumed.

## Effects on third parties

Actions with visible effects on third parties, such as end users and customers, are decided by whoever owns them. The agent supplies the data: who is affected, how many people, what changes for them and what each option costs. The owner decides. In support work this means the agent investigates and reports, and does not send, refund, cancel or notify on its own initiative.

When the user gives a new instruction in the middle of an operation, the rule of `development-workflow` on instructions that arrive during execution applies. It is named here and not rewritten.

## What stays with the user

The concrete commands, contexts and systems of the user's own environment stay in the user's memories and in their own stack skills. This skill carries only the method. Deletions outside the work's own folder or worktree stay with the user too: the agent names them, and the user runs them.
