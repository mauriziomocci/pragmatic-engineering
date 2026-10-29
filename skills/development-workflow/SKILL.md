---
name: development-workflow
description: Use for any work on code, a release, a merge or a closure. The three lanes (feature, support and incidents, operations), seven phases and four gates, one tool chain per feature (superpowers by default, spec-kit on request), the design in three steps, models by role, the role lenses and decisions while the user is away, the daily budget, instruction layers, the rule cycle, shared files, phase 6 before a merge request, closure and continuity.
---

# development-workflow

This skill puts the work in order: which lane a piece of work takes, which phases and gates a feature passes, which chain of tools serves each phase, and who decides what. How code is written lives in `engineering-principles`. How a review is done lives in `blunt-review`.

## The three lanes

The lane comes from the nature of the work. When it is not clear, ask.

- **Feature.** New behaviour or a structural change. The next sections describe this lane.
- **Support and incidents.** From the ticket to the fix. Primary evidence comes before hypotheses, and your own recent changes are checked before external causes (`evidence-based-investigation`). Phases 1-4 shrink to a short diagnosis and a short proposal, without spec-kit. When code is touched, the failing test comes first. The review follows `blunt-review`. Two gates remain, in short form: a go on the proposal, and a go before production. The answer to the customer is bound to the evidence, and its form follows the user's writing rules.
- **Operations on live systems.** Before a command or a tool that changes an external system, load `safe-operations`.

## Feature lane: phases and gates

A phase starts only when the gate before it is closed. No gate is skipped.

| Phase | What happens | Gate |
|---|---|---|
| Start | The plugin's rules arrive through the import in the user's `CLAUDE.md`. `SessionStart` warns when the import is missing. | none |
| 1 Idea and requirements | The frame of the PM lens (Role lenses), even when phases 1-4 are condensed. `superpowers:brainstorming`, or `speckit-specify` and `speckit-clarify`. `evidence-based-investigation`. `engineering-principles`: understand first, then reuse. | none |
| 2 Spec | Three-step design. `adversarial-review-panel` on costly decisions. On an interface or on API responses, one round of the UX lens and the review lens first (`interface-quality`). A spec touching a delivered API states "contract unchanged" or "CONTRACT CHANGE" and follows the client's scenario table (`engineering-principles`). The spec goes in the folder of the chosen chain. | heavy |
| 3 Plan | `superpowers:writing-plans`, or `speckit-plan`. | light |
| 4 Tasks | `superpowers:writing-plans` (titles `### Task N`), or `speckit-tasks` (lines `T001`). | light |
| 5 Implementation | In sequence, with the engine of the chosen chain: `superpowers:subagent-driven-development` or `speckit-implement`. `superpowers:test-driven-development`. The tests of the touched area before every commit. Documentation in the same commit. | escalation when a decision is missing |
| 6 Validation | Full suite. `superpowers:verification-before-completion`. `blunt-reviewer` on the whole diff. With findings, the review cycle of `blunt-review`. A score for each touched lens (`quality-scoring`); below 8 the gate stops and asks "fix or defer?". | heavy |
| 7 Closure | `superpowers:finishing-a-development-branch`, only after the gate of phase 6. The rest as in Closure. | none |

A heavy gate is a short synthesis, the question "is it clear?" in the user's language, and the user's written approval. A bare "ok" to a spec nobody read is not approval. A light gate is a quick coherence check: the foundations were validated at the heavy gate. After the light gate of phase 4, read the whole task list once more with fresh eyes before any code. It is the last coherence check, not a second brainstorm.

Trivial work (fewer than three files, an obvious fix, a configuration value) condenses phases 1-4 into a brief analysis. The two heavy gates stay. Gate 6 has one exception: `autonomous-execution`, invoked by the user by name, whose internal validation includes the review of `blunt-reviewer`. Gate 2 has none.

The rule that claims are verified before they are stated holds in every phase. This workflow changes only when the user asks.

## One chain per feature

A feature uses one chain of tools, never two. The default chain is superpowers: `superpowers:brainstorming`, `superpowers:writing-plans` and `superpowers:subagent-driven-development`, with the spec in `docs/superpowers/specs/` and the plan in `docs/superpowers/plans/`. When the user asks for spec-kit, its whole chain is used instead: `speckit-specify`, `speckit-clarify`, `speckit-plan`, `speckit-tasks` and `speckit-implement`, with the spec in `specs/NNN-slug/` as `spec-driven-layout` says. These names were tried with spec-kit 0.8.9. Names change between versions, so check the installed ones first.

Hand-over points between the superpowers chain and this workflow:

- `superpowers:subagent-driven-development` stops after the review of its last task.
- Its final review of the branch is the phase 6 review, made by `blunt-reviewer` on Opus, so the same diff is not read twice.
- In place of that final review, the coordinator reads the skill's ledger, lines marked `minor (deferred)`, `parked` and `Ruling:`. It carries those lines into the merge request description, as non-blocking findings with the decision taken. The rulings go to the user at the gate of phase 6.
- Then the method moves to phase 6 in place of the skill's own call of `superpowers:finishing-a-development-branch`, which comes only in phase 7.
- The per-task reviewers of that skill stay as an internal check.

## Superpowers skills by phase

Tested with superpowers 7.0.0. Each skill is written `superpowers:<name>`. The plugin's rules reach the session as the user's own instructions, and `superpowers:using-superpowers` ranks those above every skill.

| Skill | Where it is used |
|---|---|
| `superpowers:using-superpowers` | Always. The plugin's rules, as the user's instructions, stand above the skills. |
| `superpowers:brainstorming` | Phases 1-2: intent, requirements and the written spec. |
| `superpowers:writing-plans` | Phases 3-4. Task titles are `### Task N`. |
| `superpowers:subagent-driven-development` | Phase 5, in sequence, with the hand-over points above. |
| `superpowers:executing-plans` | Phase 5, only if the user chooses execution in the main session. |
| `superpowers:test-driven-development` | Phase 5, every task. |
| `superpowers:using-git-worktrees` | As `superpowers:subagent-driven-development` uses it. |
| `superpowers:dispatching-parallel-agents` | Parallel investigations, not implementation. |
| `superpowers:systematic-debugging` | Every bug and every red test, together with `evidence-based-investigation`. |
| `superpowers:verification-before-completion` | Phase 6. |
| `superpowers:requesting-code-review` | Not used: the independent review is `blunt-reviewer`. |
| `superpowers:receiving-code-review` | When findings arrive, handled through `blunt-review`. |
| `superpowers:finishing-a-development-branch` | Phase 7, only after the gate of phase 6. |
| `superpowers:writing-skills` | When skills are written or changed. |
| `superpowers:diagnosing-superpowers` | When a superpowers session went wrong and the user wants to know why. |

## Three-step design

Before any design document (a spec, an architecture proposal, a data model, an interface contract) the design takes three steps. None is skipped.

1. **Initial proposal.** After the requirements are gathered, a complete design, detailed enough to judge on its merits: parts, interfaces, data flow, trade-offs, dependencies. No spec file yet.
2. **First self-review.** Following `blunt-review`, hunt anti-patterns, missing edge cases, decisions hidden behind "for simplicity", structures that need special cases, scaling limits, races and security gaps. List the findings by severity, each with its fix.
3. **Second self-review and consolidation.** Review the fixes of step 2 with fresh eyes, because a fix can bring a new problem. Then write the consolidated design. Only now is the spec file written.

A self-review that removes nothing from the first proposal did not happen. For a decision that is costly to reverse (a data model, a public interface, a boundary between modules, a new dependency), run `adversarial-review-panel` before choosing, and after its consolidation the review cycle of `blunt-review`.

When requirements come from several documents, first write their synthesis. Then take one area of impact at a time, alternating the agent's passes and the user's corrections.

Before going deep, build a tracer bullet: a thin slice that runs end to end through every layer. It is not a spike. A spike is a throwaway prototype that answers one question and is discarded. The tracer bullet stays and grows.

## Tasks, models and escalation

Tasks are atomic, each with a checkbox, run one at a time and in order, never in a batch. `engineering-principles` says how a task is written. For each task: the failing test first, the code, the tests of the touched area, a review of the diff following `blunt-review`, then the box is ticked.

Models follow the role. Opus for judgment, design and review. Sonnet for the execution of a fully specified task. Haiku never, for code, design, review or documentation. The main session keeps the model the user chose. The roles apply to the agents it dispatches, and the model is always set explicitly, because an omitted one inherits the session's. Effort is high for transactions, security, permissions and migrations. Reads are targeted. Orders are few and complete, naming the files, the isolated resources and the shape of the report; reports stay under 10-15 lines, with commits, results and the confidence level. Each piece of work gets a new session.

Escalation: an unforeseen edge case, a wrong assumption in the spec, an undeclared refactor or an incoherence with the existing code stops the task and goes back to whoever decides. The executor invents nothing. If the answer to "what do I do here?" cannot be derived from the task and the spec, escalate. The spec or the plan is revised before work resumes. An executor that reports it is blocked or needs context gets more context, a more capable model or a smaller task, never the same retry.

A new instruction from the user in the middle of an execution suspends the plan until it is reconciled with the instruction.

Keep a work log of decisions and difficulties. It is the hook for later sessions; when the user keeps one, use that one. Explanations to the user follow `teach`.

## Role lenses

Four lenses, named for roles, never for people, and provisional until their re-evaluation. The main session holds the PM lens; the UX lens runs as a subagent on Opus and the user lens on Sonnet, both briefed with `interface-quality`; the review lens is `blunt-review`.

The PM lens opens phase 1 of every feature, condensed or not, with a frame: a pre-mortem of three lines (how it can fail, each with what prevents it); the why (what for, for whom, what happens if we do not do it, how we know it is done); the reuse statement, without which the plan goes back; the smallest version and its measured cost, never an invented one. It mediates when the other lenses ask for more than the frame holds, keeps the budget and holds the 8/10 gate. Company constraints come only from the user, and every cut of scope is a proposal to the user.

Each lens re-checks the others' claims on the evidence before accepting them. An agreement is written with what each lens verified by itself, and an agreement without an independent check is a finding; a round on a question that is not trivial and changes nothing of the first proposal is flagged as possible theatre. Never traded: evidence, known defects, test first, tests, guards, validation, error handling, bug fixes, and the bars of taste and architecture. When time or tokens run short, scope is cut, never quality, and there the review lens prevails without convincing anyone.

**While the user is away.** When the user says so or, with `pe.officeHours` set, a blocking question gets no answer for 30 minutes inside the window, and only in work the user started: the review lens decides a technical case; the PM lens decides scope, interface, time, or a disagreement between the UX and review lenses inside an approved spec, in one sentence with the reason, after hearing both and weighing five costs (tokens, time, quality, working behaviour, the satisfaction of customer and end user). Data model and API contract are never decided in the user's absence: a provisional proposal on a local branch, the dependent tasks parked, the others carried on. Outside the window only technical decisions are taken. Production, shared systems, deletions, merges into protected branches, irreversible actions and changed requirements wait for the user. Every such decision is provisional, written with both positions and the five costs, and reported to the user first.

**Decision log.** One entry per decision, in the log the project's configuration names, otherwise in the progress note: who decided, the positions, the costs and the state (confirmed, overturned, pending). Defects are marked by origin, found by a lens or later by people, and decisions taken again are marked, because the calibration of `quality-scoring` counts missed defects from there.

## Budget

Where the host exposes the account's usage, the day's allowance and ceiling of the budget rule are computed at the first block of the day and written in the progress note, with the weekly share they start from; usage is read again at every block.

## Instruction layers

When instructions disagree, this order decides.

1. The user's explicit request.
2. The project's configuration, for stack, commands, conventions and the language of prose: the constitution of spec-kit and the project's `CLAUDE.md`.
3. The user's personal configuration.
4. The plugin's default rules.

A conflict with the five precedence rules (evidence, no bug left behind, test-first, blunt review, burden of proof on adding) goes to the user and is never resolved silently. If the project declares neither its test command nor the language of its prose, ask, and offer to write it down.

## Rule cycle

A lesson (a rejected mistake, a recurring trap) becomes a proposed rule, with the layer where it should live: the project's `CLAUDE.md`, the user's personal configuration, or the project's memory. A proposed rule is never applied without the user's explicit request.

## Shared files

Before changing an instruction, settings or memory file (a `CLAUDE.md`, a `settings.json`, a memory), make a dated copy, show the diff, and wait for the user's explicit go. Then add one line to the project's rollback log, if it keeps one.

## Phase 6 and the merge request

1. Run the full suite and follow `superpowers:verification-before-completion`: no claim of success without the output of the command.
2. Launch `blunt-reviewer` with the prompt `<merge-base>..HEAD` and nothing else, as its closed grammar requires. Here `<merge-base>` is the result of `git merge-base HEAD <remote target>`. Launch it in the background while the suite runs and the merge request description is prepared, so phase 6 does not wait for it in series.
3. With verdict `changes`, follow the review cycle of `blunt-review`. Its rounds run on the ranges of the fixes.
4. Score each touched lens with `quality-scoring`, from the reviewer's `FINDINGS:` line and the sheets of the UX lens. With a lens below 8 the gate stops: the PM lens proposes to the user the fix or a tracked deferral, each with its cost.
5. The description carries the scores and the reviewer's lines `VERDICT:`, `FINDINGS:` and `COVERAGE:`, declared as the reviewer's own, because no mechanism records them in this version. It also carries the non-blocking findings with the decision taken and, with `superpowers:subagent-driven-development`, the ledger lines described in One chain per feature.
6. The merge request is opened only after the review and the heavy gate of phase 6.

A rebase without conflicts asks for no new review. A conflict resolution does, on the range that contains it.

## Closure

Phase 7 prescribes no merge and no push: the user's rules and the user's go apply. `autonomous-execution`, invoked by name, counts as the go to push the work's branch and open its merge request, never to merge. After a merge, clean up the branches already merged, following the user's rules, and report those that still hold unmerged work.

Before a version change, classify the changes in the diff and state the semver part chosen, with the proofs. Then write the continuity note and the rule proposals that the lessons suggest.

## Continuity

The progress note is updated at every milestone and read again after a compaction. Every task given to a sub-agent names its deliverable file, written in blocks with a status line at the top. At the end of a session, or when the work passes to another agent, the full note is written. Where the note lives, when it is updated and how the status line is made are in `continuity-note`, sections "The progress note" and "Status line of deliverable files". They are not repeated here.
