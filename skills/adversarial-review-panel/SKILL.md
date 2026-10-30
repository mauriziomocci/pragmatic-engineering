---
name: adversarial-review-panel
description: Use for decisions where being wrong is expensive - architecture, specs, risky refactors, security-relevant changes, technology choices, data models. Runs a contradictory review with four distinct lenses (structure and taste, rigour and correctness, economy and simplicity, product and priority) that argue against each other, then one cross-examination pass asking what all four missed; conflicts resolve by a written precedence order, not by a judge, and the result is ONE decision. Do NOT use for ordinary reviews, small fixes or trivial changes - there blunt-review is enough.
---

# adversarial-review-panel

When the user's own configuration has a skill with this name, that one applies.

## What this is for

A single reviewer has a single bias. On a decision that is expensive to undo — a
data model, a module boundary, a security control, a dependency you will carry
for years — the defect that kills you is usually the one your own lens cannot
see. This skill forces the same problem through four lenses that genuinely
disagree, then makes one call.

It is a **decision procedure**, not a performance. If it produces four
paragraphs of characterisation and one obvious conclusion, it has failed and
cost four times a normal review to do it.

## When to run it (and when not to)

Run it when at least one is true:

- the choice is expensive to reverse (schema, module boundary, public API, storage);
- it is security- or privacy-relevant;
- it introduces a dependency, a service, or a repository;
- two reasonable approaches exist and the team disagrees;
- the user explicitly asks for a panel or an adversarial review.

Do **not** run it for: ordinary code review after writing code, bug fixes, typos,
renames, config tweaks, or anything where the answer is already obvious. There
`blunt-review` applies. Running the panel everywhere is the fastest way to make
people stop reading it.

## The four lenses

Each voice is a **lens, not a character**. Never write in-character prose, never
give them names, never dramatise. Each produces findings in the mandatory output
shape (evidence with `file:line` or a measured number). A lens that has nothing
to say writes one line saying so — that is a valid and frequent outcome.

### 1. Structure and taste

Asks: *is this shaped right?* Hunts the special case that should not exist, the
string built to be taken apart, N ways to do one thing, the missing decorator
behind repeated preambles, stringified errors, dead code. Its characteristic
verdict is "the structure is wrong, and with the right one this problem
disappears". Pragmatic: prefers the thing that works and can be maintained over
the thing that is elegant on paper.

### 2. Rigour and correctness

Asks: *how do we know it is right?* Wants the invariant stated, the edge cases
enumerated, the proof or the guard that enforces the claimed property. Hunts
properties asserted in prose but not enforced by a test, off-by-one and boundary
conditions, concurrency and ordering assumptions, unhandled error paths, and
anything justified by "it works in practice". Its characteristic verdict is
"this may be true but nothing forces it to stay true".

### 3. Economy and simplicity

Asks: *what can be removed?* Counts the moving parts and challenges every one.
Hunts speculative generality, layers that only forward calls, configuration
nobody sets, abstractions with one implementation, parameters always passed the
same value, helpers called once, and features added for a hypothetical future.
Its characteristic verdict is "the smallest thing that solves the real problem is
smaller than this".

It works on the burden of proof on adding, stated here in full because this lens
uses it (the complete rule also lives in `blunt-review`). The default answer to
adding anything is no, and whoever adds it proves the need. The order of
preference is fixed: delete > do nothing > extend what exists > write new. The
last is allowed only after the first three are ruled out. Its sharpest question is
**"what breaks if we delete this?"** — when the answer is "nothing", that is a
finding, not a detail. Counts parts, never characters: shorter is not the target,
fewer moving parts is.

Two limits, both deliberate. It never argues against code that **enforces a
property** — tests, guards, validation, error handling — because that is not
accumulation and it pays for itself the first time it fires. And it is in
permanent tension with lens 2: rigour adds code to guarantee, economy removes
code so there is less to guarantee. **That tension is the point — do not resolve
it inside a lens**, and do not let either side win by decree. The precedence
below resolves it, and only at equal correctness.

### 4. Product and priority

Asks: *does this matter, to whom, and is it worth it now?* Hunts work with no
user, gold-plating, and effort spent on the rare case while the common one is
broken. States the cost in the terms the organisation pays: time, repositories,
deployments, migrations, on-call burden, who maintains it. Its characteristic
verdict is "this is correct and nobody needs it" or "this is the only part that
matters, do it first and drop the rest".

## Cross-examination (one pass, after the lenses)

Four lenses share one blind spot: they all examine the artifact that was put in
front of them. None of them asks whether that artifact should have been the
subject at all. So before deciding, answer one question explicitly:

> **What did all four lenses miss?**

Where the answer usually hides: the problem was never confirmed to be real; the
user asked for something adjacent and the framing drifted; the constraint that
decides everything was never stated; the person maintaining this in a year is
nobody in this conversation; a cheaper option was excluded before the panel
started.

Rules: it must name something **no lens already said** — restating a finding is
padding. "Nothing" is a legitimate and frequent answer, written in one word. Do
not manufacture an insight to justify the step.

Borrowed from the peer-review round of council-style panels, reduced to a single
pass: the value is the question, not the ceremony of everyone reviewing everyone.

## Resolving conflicts: precedence, not a judge

There is **no fifth arbitrating voice**. Two reasons. A judge is a role that
costs output without producing information, and a judge briefed on
organisational constraints is exactly the mechanism by which inconvenient
technical findings get buried. Conflicts resolve mechanically instead, by a
written order — the same way the working rules settle their own conflicts, by a
written precedence.

**Do not require unanimity.** Lenses 2 and 3 are built to disagree: rigour adds
code to guarantee, economy removes code so there is less to guarantee. Forcing
consensus produces one of three bad outcomes — a lens caves (implicit,
unaccountable arbitration), they converge on the mushy middle, or it deadlocks.
Disagreement is the output, not a failure.

**Precedence, applied in order:**

1. **Correctness, security, privacy win over everything.** Something wrong or
   unsafe is not shippable at any price. A finding at this level is never
   overruled by elegance, simplicity or schedule — it is refuted with evidence,
   or it stands.
2. **At equal correctness, simplicity wins over structural purity.** Fewer moving
   parts means fewer things that break. An abstraction that is beautiful and
   unnecessary loses to the blunt version that does the job.
3. **The product lens never decides what is true — only what is done now.** It
   sets scope and sequence, never the validity of a finding. "We ship with the
   gap because the audit is Friday" is a legitimate call; "the gap is not a gap"
   is not.
4. **If precedence does not resolve it, the conflict is genuine: escalate to the
   user.** State the two options, what each costs, and what you would pick. Do
   not manufacture a decision to avoid asking, and do not present a neutral menu.

Whatever gets deferred is written down: what is accepted, and who carries the
risk. A deferred defect that nobody recorded is a hidden defect.

## Output shape (mandatory)

Keep it compact. The panel must fit on one screen for a normal decision.

```
PANEL: <the decision under review>

Structure ....... <finding, or "no objection">
Rigour .......... <finding, or "no objection">
Economy ......... <finding, or "no objection">
Product ......... <finding, or "no objection">

Missed by all: <what none of the four lenses saw, or "nothing">

CONFLICT: <the real disagreement, in one sentence. Omit if there is none.>
Resolved by: <which precedence rule decided it — 1 correctness, 2 simplicity,
              3 scope-only, 4 escalated. Omit if there was no conflict.>

THE DECISION: <what we do>
Because: <the reasoning that beat the alternative>
Deferred: <what is knowingly not being done, and the risk accepted. Omit if nothing.>
```

Rules that keep it honest:

- **Agreement is a valid result.** If three lenses have no objection, they write
  "no objection" and the panel is four lines. Manufacturing disagreement to fill
  the format is the failure mode this skill exists to avoid.
- **Every finding carries evidence.** Same rule as any review: `file:line` or a
  measured number. A lens speaking in generalities is noise.
- **`CONFLICT` names one disagreement, not a summary.** If there is no real
  conflict, delete the line — do not invent one.
- **The decision is one course of action**, not a menu. If the user must choose,
  the panel has not finished its job; say precisely what information is missing.

## After the decision: the review cycle

The panel decides; it does not check its own fixes. Once the decision is
consolidated and the corrections that follow from it are made, follow the review
cycle of `blunt-review`: a fresh reviewer rereads the corrected document in
full. The cycle stops as `blunt-review` says.

## Common failure modes

- **Theatre**: four voices, zero new information, a conclusion identical to the
  first instinct. Cure: allow "no objection", and skip the panel when the answer
  is obvious.
- **Symmetry bias**: forcing each lens to produce exactly one finding. Real
  reviews are lopsided; one lens often carries everything.
- **Softening through the product lens**: using schedule or organisational
  pressure to bury a correctness or security finding, instead of recording it as
  knowingly deferred. Precedence rule 1 forbids it; rule 3 confines the product
  lens to scope and sequence.
- **Consensus-seeking**: massaging the lenses until they agree. Lenses 2 and 3
  are built to disagree; a panel that always converges has stopped working.
- **Redundant lenses**: structure and economy often agree, because both hate
  complexity. When they do, say it once and move on rather than padding.
- **Running it on everything**: the panel is expensive. Its value comes from
  being reserved for decisions that deserve it.
