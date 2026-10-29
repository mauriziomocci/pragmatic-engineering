---
name: evidence-based-investigation
description: Use for investigations, diagnoses, verifications and technical answers where a wrong conclusion has a cost. Verify before asserting, state the confidence level, look at primary evidence and your own recent changes first, rule out hypotheses one by one, scope a defect in four steps, separate verified from inferred facts, and answer in several passes. Not for design or review.
---

# evidence-based-investigation

Most investigations reach the wrong answer not because data is missing but because the investigator confirms the first plausible explanation without testing the alternatives, states as certain what is only inferred, or stops when the numbers match. This skill prevents those three failures with multiple passes, explicit hypothesis testing and an honest separation of what is verified from what is not.

The method is the point; the domain (a customer ticket, a bug, a reconciliation, a security audit) is only its surface. Use it whenever a wrong conclusion has a real cost.

## When to use

- A customer ticket where a precise explanation matters and the customer will scrutinise the answer.
- A bug with a plausible first hypothesis that nobody has verified, which is almost every bug.
- A reconciliation between two systems that report different numbers for the same thing.
- A security audit, where "looks fine" is not a verdict.
- A check that a piece of work is really finished and works where it matters.
- Any technical answer that someone will act on and that you cannot take back.

## When not to use

- A typo in a single file, a mechanical rename, a format-preserving tweak or an obvious configuration value.
- Pure execution of a plan whose analysis was already done, such as applying a written plan exactly as specified.
- Designing a feature or a structure: that belongs to `development-workflow`.
- Reviewing code, tests, documents or infrastructure: that belongs to `blunt-review`.

## Investigation rules

- Primary evidence first, hypotheses second. Start from what can be observed directly: the log, the data, the code, the system that is running. A hypothesis formed before looking tends to be confirmed by whatever is found afterwards.
- Your own recent changes before external causes. Look first at the last deploy, the last commit and the last configuration you touched: the most likely cause of a new failure is the most recent thing someone changed, and it is the cheapest to check. Blame a third party or the infrastructure only after your own side is cleared.
- To find the cause of a bug or a red test, call `superpowers:systematic-debugging`. This skill starts where that one ends: it keeps the conclusion honest and scopes what the fix covers.

## Confidence levels

State the confidence level explicitly, and use exactly one of these three labels:

- **Verified in the real environment**: the original scenario was run in the real environment and no longer reproduces.
- **Tests passing, deployed, real-environment verification pending**: the tests are green and the change is deployed, but nobody has yet observed the original scenario in the real environment.
- **Unit tests only**: the logic was tested in isolation.

A passing test proves the logic in isolation, not that the fix works where the problem was seen. A deploy proves that the new version is running, not that the problem is gone. Report each for exactly what it is, and never extrapolate from one level to the next. A problem is resolved only when the original scenario no longer reproduces in the real environment.

## The multi-pass loop

```
read -> compute -> hypothesize -> rule out -> distinguish -> review -> repeat
```

Each pass produces output, the reader (or your own re-read) corrects the assumptions in it, and only then does the next pass start. Running every pass autonomously without a review reintroduces the assumptions the skill exists to prevent.

### Pass 1: read and gather the raw inputs

Read the original input verbatim: the ticket, the bug report, the failing test, the file under review. Identify what is claimed (a delta, an error, a change), who claims it and how reliable that source is, and which attachments, logs or data it refers to. The output is a short factual summary with no interpretation. The anti-pattern is "the cause is probably X" before the whole input has been read.

### Pass 2: compute with two independent sources

For every quantitative claim, compute the number from two independent sources. If they agree, that is a verified fact. If they disagree, the disagreement is the investigation: do not go on until you understand it. Examples: purchases paid against invoices issued should match; the timestamp of an error in the log against the timestamp of the matching metric should align; a vulnerability scanner's output against a manual trace of the code path should agree. The output is a table of "Source A says X, Source B says X, agreement: yes or no".

### Pass 3: parse the artifact into structured data

Take the artifact at the centre of the investigation (a report, a log, a source file, a manifest) and parse it into a form that supports filtering, aggregation and comparison. A spreadsheet becomes one record per row with totals per outcome; a log becomes events per timestamp and errors per type; a source diff becomes changes per function. The output is the structured form plus the totals derived from it. The anti-pattern is trusting a total counted by eye.

### Pass 4: rule out the hypotheses one by one

A match between the observed delta and a plausible explanation is a hint, not a confirmation. Generate at least two alternative explanations and test each against the data: say which data would confirm it and which would rule it out, run the test, then confirm or rule out. Do not leave a hypothesis untested because the first one already matches. If only one explanation survives, it becomes the answer but stays a hypothesis until an independent confirmation or an explicit acknowledgement from the source arrives. The output is a table "hypothesis, test, verdict", and a verdict of "consistent with the data but not directly confirmed" is written as such.

### Pass 5: separate verified facts from inferred ones

Reread every sentence of the draft conclusion and classify it:

- **Verified**: a tool call, a query result or a citation of the source code proves it directly.
- **Inferred**: it follows logically from verified facts, but the reasoning could be wrong.
- **Assumed**: it depends on an interpretation nobody has confirmed, such as "the customer probably means X".
- **Unverifiable**: it concerns something that cannot be observed from your side, such as the state of someone else's bank account.

The four categories stay visible in the answer. Verified statements stand as they are. Inferred statements are framed as "based on X and Y, the conclusion is Z". Assumed statements become explicit questions to the source. Unverifiable statements are replaced by what can be said: "the gateway reports the payment as captured" instead of "the money is on the account". This is the single most important pass, and the one most often skipped.

### Pass 6: write more than one draft

Write the final answer (the pull request description, the customer email, the ticket comment, the design note, the postmortem), then reread it with three questions. For every sentence that asserts something: is it verified or inferred? For every sentence that implies certainty: is there evidence you could show if challenged? For every conclusion: would a pedantic, adversarial reader find a hole? Revise, and repeat. Do not send the first draft when the second would have been more honest.

One customer answer needed three revisions, each triggered by "are you sure?". The first removed an assumption about which column of a report the customer had read. The second removed a claim about where the money was and kept only what the gateway reported. The third replaced a vague "in the following days" with the exact date and the report needed to confirm it. Ask yourself that question before sending.

### Pass 7: extract what is reusable

The investigation cost time, so keep the lesson. It becomes a knowledge-base entry when the pattern is likely to repeat, a tool when the manual sequence is likely to be run again, a regression test when the bug can be pinned, or a proposed rule for the right layer, following the rules cycle of `development-workflow`. Always cite the incident that produced the lesson, so that a future reader can judge whether it still applies.

Each pass is cheap. Skipping passes feels like saving time and produces a wrong answer that costs a multiple of that time to undo. Match the depth of the investigation to the consequence of being wrong.

## Scoping a defect

When a defect is found, never stop at the first problem. These are four steps of scoping, not the phases of `superpowers:systematic-debugging`, which finds the cause; here the cause is known or suspected and the question is how far the defect reaches and what a fix covers.

1. **Boundary.** Declare the limits of the analysis before starting: the method, class, module or flow that is in scope.
2. **Comparison with the working twin.** If a method, route or job that does the same thing correctly exists (the working twin), compare it line by line to the end. Do not stop at the first difference: every differing line is a potential independent defect.
3. **Symptom-cause map.** Build a table with the columns "Symptom | Identified cause | Required fix | Covered by this fix?". A symptom without a cause means the analysis is incomplete.
4. **Statement of coverage.** Close with "This fix resolves X. It does NOT resolve Y, which requires a separate fix on Z." A partial fix is never presented as the complete solution.

## Scoping techniques for fixes and data corrections

Four techniques sharpen the passes above when the investigation ends in a correction of code or data.

1. **Enumerate every writer of the state before designing the fix.** Before correcting or migrating a field, list every place in the code that writes it (search for the assignments, not only the obvious one you started from) and classify each path: does it produce the corrupted value or a legitimate one? The population to correct is defined by this classification, not by the first path found. A field written by three code paths, only one of which corrupted it, is the typical case.
2. **Use the discriminator the system already encodes.** To separate the affected records from the unaffected ones, look for a distinction the code base already makes (a field, an invariant stated in a docstring, a status) before inventing a filter. If the documentation of a property says that a value set while an owner reference is empty means "created automatically", that sentence is the exact filter.
3. **Anchor persistent artifacts to stable symbols, never to line numbers.** Memory notes, knowledge-base entries, design documents and tickets cite method, property and constant names. Line numbers move with every edit; add them only as "approximately at line N on <date>", with the instruction to locate the code by its symbol.
4. **Delimit the population before writing a fix or a migration.** Ask explicitly "does this hold for every instance or only for one subtype?" and answer with data or code before building anything. A migration that touches the wrong superset is worse than the bug. This is a precondition of any correction script.

## Output rules

Whoever the recipient is (a colleague from another department, a technical peer, a customer, yourself in a postmortem):

- State numbers from two independent sources.
- Show the data, not only the conclusion: the reader must be able to recompute it.
- Use the labels verified, inferred and asked explicitly when the stakes warrant it.
- Make no claim of certainty about what cannot be observed from your side.
- Ask an explicit question when an assumption carries weight, instead of burying it in a subordinate clause.

## Anti-patterns

Watch for these in your own draft:

- "The cause is X" before alternative causes were tested.
- A numerical match between the observed delta and one hypothesis, treated as proof.
- "We confirm that..." for something that is only inferred.
- "The money is on your account" when the only evidence is a payment reported as captured on the gateway side.
- "Tests pass" with no test output shown, or "deployed" with no check in the real environment.
- A single-pass draft sent without a rereading in an adversarial frame of mind.
- Stopping at the first matching explanation while others remain untested.
- Treating a daily report or a snapshot as a live source of the current state.

Skills that combine with this method: `superpowers:systematic-debugging` for bugs and failing tests; `superpowers:verification-before-completion` for the check that something is really done; `superpowers:writing-plans` for turning verified requirements into implementation tasks.
