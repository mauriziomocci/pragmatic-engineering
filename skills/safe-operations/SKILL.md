---
name: safe-operations
description: Use before running a command or a tool that changes an external system - a deploy, a rollout, a migration, a data fix, a cluster, a cloud account, a tool with effects on end users. Verify and state the active target, dry run where one exists, say the blast radius and the way back first, get a separate explicit go for every run on production, never poll long operations, verify at every level afterwards.
---

# safe-operations

This skill is the method for acting on a system outside the repository: a command or a tool whose effect outlives the session. A wrong test run costs a minute. A wrong run against the wrong cluster or database costs other people's work, and some of it cannot be undone. The method asks for little each time, and nobody skips it.

## When to use

Load it before running a command or a tool that changes an external system: a deploy, a rollout, a migration, a data fix, a change on a cluster or a cloud account, a tool with effects on end users. Reading from such a system needs none of this; the first write does.

## Before

1. Verify and state the active target: the cluster context, the cloud account or profile, the database, the environment. Verify it with a command that shows it, never from memory and never from what the previous session was doing, and write the result in the message. Name the target inside the command itself whenever the tool allows it.
2. Use a dry run where one exists (a plan, a preview, a diff against the live state) and read its output before running the real command.
3. Say the blast radius first: what the command touches beyond the task, and who notices if it fails. Say the way back: the exact steps that undo it. If there is no way back, say so and stop, because that is a decision for the user.

## Production and shared systems

Approving a change is not approving its execution. "Yes, fix it" approves the content of the correction, not running it on production. Every run with effects on production or on a shared system asks for its own explicit go, even right after the user approved the change. The go covers that single run on that target: it does not carry over to the next run, and a go given for one target is not a go for another.

## Long operations

A long, asynchronous operation (a rollout, a migration, a pipeline) is not watched in a loop. Polling spends attention and tokens and adds nothing the user's own signal does not give. Say how the operation is checked (the command, the page, the end state to expect), then wait for the user's confirmation or for a notification. One check made because the user asked is not a loop.

## After

Verify at every level, not only at the first one that answers. A process that has started is not a responding service, and a service that responds does not prove the data is right. Walk up the levels: the job or process ran, the service answers, the answer carries the correct data, and the end user sees what was meant. Say which levels were verified, with the evidence for each, and which were not. A level that was not checked is reported as unchecked, never assumed.

## Effects on third parties

Actions with visible effects on third parties, such as end users and customers, are decided by whoever owns them. The agent supplies the data: who is affected, how many people, what changes for them and what each option costs. The owner decides. In support work this means the agent investigates and reports, and does not send, refund, cancel or notify on its own initiative.

When the user gives a new instruction in the middle of an operation, the rule of `development-workflow` on instructions that arrive during execution applies. It is named here and not rewritten.

## What stays with the user

The concrete commands, contexts and systems of the user's own environment stay in the user's memories and in their own stack skills. This skill carries only the method.
