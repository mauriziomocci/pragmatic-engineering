---
name: teach
description: Use when the user asks how code or a system works or asks to be taught, when resuming a session, and before a heavy gate. Brief high-level explanations followed by "is it clear?", the six-layer method for teaching code, and the state on one screen from the continuity note. Never a quiz or a verification question.
---

# teach

This skill says when and how to explain. The user should always know what is about to happen, what happened and why the architecture is the way it is, without having to ask and without reading a wall of text. Frankness of tone does not live here: it lives in the rules file.

## When to use

- When the user asks how some code or system works, or asks to be taught.
- When a session is resumed.
- Before every heavy gate (the spec and the final validation).

Explanations at the start and end of a work block, and at an architecture choice, happen without being asked: the next section says when.

## Brief explanations

Explain at four moments:

1. At the start of a work block: what is about to be done and why.
2. At every architecture choice: the choice, the main alternative that was discarded and why.
3. At the end of a work block: what changed and where to look.
4. Before every heavy gate: a summary of what the user is about to approve.

A work block is a feature, a decision or a delivery. It is never an atomic task and never a single tool call, so a plan that runs without pauses stays compatible with these explanations: they sit at its edges, not between its steps.

How to explain: brief and at a high level, in the language the user writes in, without chapters or headings. Then ask "is it clear?", also in the user's language. The answer is awaited only at the two heavy gates and at architecture choices. Everywhere else the question stays open and the work goes on; the user answers when they want to. Whatever the user says is unclear is explained again, with different words and with an example, not with the same sentence said louder.

## Teaching code in six layers

When the user asks to be taught some code, go through six layers in this order. Each one is short. A layer with nothing to say gets one honest line saying so, never silence.

### The problem

What this code solves and for whom. One or two sentences a person outside the module can follow.

### The path through the code

The route one request takes between files and functions, written as `file::function`, in the order in which it runs. A reader who follows the path with the files open must be able to find every step.

### Choices and discarded alternatives

Why it is built this way, what was considered instead and why it lost. If the reason is not known, say so and do not invent one.

### A concrete case

One real input, followed from the start to the end, with the values it has at each step. A concrete case teaches what a description cannot.

### Limits

What the code does not cover, where it breaks, and what is declared but not enforced. A rule that lives only in a comment or a document is named as such.

### How to check it yourself

A command or a test the user can run to see it with their own eyes. It is never a question put to the user. Every command given to the user names its folder, as in `git -C <folder> log`, because the user's terminal may stand in another folder.

For questions on how a system works, the shape of the answer of a technical FAQ (the fact first, then the entities, the path, one case and the source) lives in `engineering-principles`.

## Resuming a session

When a session resumes, show the state on one screen, taken from the continuity note or from the progress note (`continuity-note`): what is done, what is in progress, what comes next and which decisions are still open. Then ask "is it clear?".

## What teach never does

- There is no quiz, and no verification question of any kind.
- The user is never asked to explain something back in their own words as a condition for going on.
- There is no exam, and no step of the work waits for proof that the user understood.
- "is it clear?" does not prove understanding. The user chose it over a verification gate and accepted that cost: it is a declared limit, not a gap to close with a check.
