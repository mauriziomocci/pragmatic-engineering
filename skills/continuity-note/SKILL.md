---
name: continuity-note
description: Write a self-contained continuity note (a handoff document) so another agent, a teammate or your future self can resume work without replaying the conversation. Use whenever work is passed on - the user says "write a continuity note", "write a handoff", "hand this off", "summarize this for the next session", "context is running out, save state" - when a long session ends with work in progress, and at every milestone in its short form, the progress note, so that a compaction loses at most the work done since the last save.
---

# Continuity Note

When the user's own configuration has a skill with this name, that one applies.

A continuity note (a handoff document) lets a **fresh context** resume your work. The
reader has none of this conversation: not the goal, not the decisions, not the
dead ends you already ruled out. They might be a different agent (a new session,
another tool, anything), a human teammate, or you tomorrow. The
whole value is that they can pick up and act *without asking you a single
question*. Optimize for that.

## When this is the right tool

Use it when work crosses a context boundary: ending a session with work unfinished,
switching to another agent or tool, handing to a colleague, or saving state
because the context window is about to be lost. The reader starts cold.

The full note is not for ordinary in-session compaction. Compaction summarizes the
conversation so the same agent keeps going, but a summary can lose the state: what
is done, what was decided, what comes next. That is why the short form, the
progress note (see "The progress note" below), is kept current at every milestone,
so that a compaction loses at most the work done since the last save. The full note
earns its cost when the next reader starts with nothing at all.

## What goes in (and what stays out)

The reader needs **state and direction**, not a transcript. Two failure modes,
both fatal:

- **Too little**: "continue the refactor." The reader has no idea what refactor,
  why, how far, or what's next. Useless.
- **Too much**: pasting whole files, full logs, the entire chat. The reader
  drowns and can't find the signal. Also re-pastes data that already lives in
  files - stale the moment you write it.

The rule that resolves both: **reference, don't duplicate**. Point to artifacts
by path or URL (files, PRDs, ADRs, issues, commits, diffs, dashboards). Carry
across only the things that exist *nowhere but your head*: why you chose A over
B, the trap that isn't obvious from the code, what to do next.

## Document structure

Write the document in this order. Lead with the parts a reader needs in the
first ten seconds; push detail down. Drop a section if it's genuinely empty -
don't pad.

```markdown
# Handoff: <short topic> (<YYYY-MM-DD>)

## Goal
One or two sentences. What are we ultimately trying to achieve, and why.

## Current state
Where things stand right now. What works, what's broken, what's half-done.
Be honest about confidence: mark what you VERIFIED versus what you ASSUME.
A reader who trusts an assumption as fact will waste hours.

## Done
- Concrete things already completed, terse bullets.

## Next steps
The most important section. Ordered, concrete, actionable - each step
something the reader can just do. Not "improve performance" but "add an index
on orders.created_at; the slow query is in reports/daily.py:88".

## Key decisions and why
Choices already made and the reasoning, so the reader doesn't relitigate them
or accidentally undo them. "Chose Postgres over SQLite because the test suite
needs concurrent writes."

## Gotchas and constraints
Traps, surprises, environment quirks. Things that look wrong but are
intentional. The stuff that would cost the reader an hour of confusion.

## Files and artifacts
Paths and URLs, each with one line on what it is and why it matters.
NOT the contents. "src/auth/jwt.py - token logic, the bug is here."

## How to verify
Commands or checks that confirm the current state, and how the reader will
know future work succeeded. "Run `pytest tests/auth/`; all green = done."

## Open questions
Unknowns and decisions that need the user. Be explicit that these are blockers
versus nice-to-knows.
```

## Rules that make a handoff trustworthy

**Redact secrets.** Never carry API keys, tokens, passwords, connection strings,
or personal data into the document. Point to where the credential lives ("token
in ~/.config/foo/key") - never the value. A handoff often gets pasted into
another tool or committed to a repo; treat it as if it will be read by someone
who shouldn't see secrets.

**Be portable across agents.** The reader may not share your tooling. Don't
write "run the /deploy skill" or "use the foo MCP" - the next agent may not have
either. Describe the *capability* in plain terms ("deploy with the project's
helm chart under deploy/") so any competent agent or human can act. If you do
know the next reader is the same setup, naming a specific tool as a shortcut is
fine - but always also say what it does.

**Distinguish verified from assumed.** This is what separates a handoff that
saves time from one that wastes it. If you ran the tests and they passed, say
so. If you only *think* the fix works, say "untested - needs verification". The
reader inherits your uncertainty either way; hiding it just moves the cost
downstream.

**Keep it lean.** Every line should earn its place. If a detail lives in a file
the reader will open anyway, link the file instead of restating it. Length is
not thoroughness - precision is.

## Where to save it

Default: write the document to the current working directory as
`handoff-<short-topic>-<YYYY-MM-DD>.md`, then tell the user the exact path so
they can move, commit, or send it. A handoff buried in an OS temp directory
tends to vanish before anyone reads it - keep it where it'll be found.

If the user names a destination (a docs folder, a ticket, a shared drive), use
that instead. If they explicitly want it throwaway, a temp path is fine - but
that's their call, not the default.

Adapt the language of the document to the user's working language.

## The progress note

The progress note is the short form of the continuity note: the state on a few lines, written for the agent that will read it after a compaction or in the next session.

- **What it holds:** the state, in four parts: what is done, what is in progress, what comes next, and the decisions still open. Nothing else; the rest belongs to the full note.
- **When it is updated:** at every milestone. A task is closed, a decision is taken, before launching or waiting for agents, before a long operation. It is updated at that moment, never saved for the end of the day. After a compaction it is read again before anything else is done.
- **Where it lives:** in the place the user's own configuration names for the state of the work (a resume card, a diary), or in the project's continuity note when the project's configuration declares one; only otherwise in `.pe/progress.md` at the root of the repository, with a `.pe/.gitignore` that contains `*`, so the folder never enters git. Outside a repository, ask the user where to keep it.
- **Never secrets.** The rule of "Redact secrets" above holds in full: the note says where a credential lives, never its value.

## Status line of deliverable files

Every task given to a sub-agent names its deliverable file. The file is written in blocks, never all at the end, and carries at the top the line:

`STATUS: IN PROGRESS - done: ...; next: ...`

The line is updated after every block, and the last block replaces it with `STATUS: COMPLETE`. If the sub-agent is cut off, the file says how far it got and what remains. Large files are read in bounded chunks, never whole. A short sub-agent with no deliverable file, such as one that only makes a commit, keeps none.
