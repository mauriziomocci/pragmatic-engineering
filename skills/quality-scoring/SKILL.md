---
name: quality-scoring
description: Use at every review that feeds the 8/10 gate of phase 6, before work is integrated or released, and when the quality of a project is measured again. A score from 1 to 10 for each lens the work touches, computed from findings classed S1, S2 or S3 with their evidence, so that two reviewers reach the same score from the same evidence; who scores which lens, the score sheet and the calibration log.
---

# quality-scoring

When the user's own configuration has a skill with this name, load that one and follow it where the two differ; this one holds only where that one is silent.

The gate of phase 6 asks every lens the work touches to score at least 8 out of 10. A gate like that means something only if the score does not depend on who gives it, so here the score is computed from classified findings, never chosen. The same perimeter, the same evidence and the same rubric give the same score within half a point.

## When to use

- At every review whose result feeds the gate of phase 6 in `development-workflow`, before work is integrated or released.
- When the quality of a project is measured again.

## The lenses

Each lens has a short id, which the score sheet and the final message of `blunt-reviewer` use.

| Lens | Id |
|---|---|
| New code | `code` |
| Old code the work touches | `legacy` |
| Architecture | `architecture` |
| APIs | `api` |
| Documentation | `docs` |
| Interface clarity | `clarity` |
| Interface aspect | `aspect` |
| Accessibility, measured | `accessibility` |

## The perimeter

Write it before reviewing: the lenses in scope, only those the work touches; the files or the git range; the pages and the widths; the API endpoints. Old code is scored only on what the work touches: the touched functions meet the thresholds after the change, and the touched files do not get worse, measured before and after. Untouched old code is out of scope, otherwise its score would never move. On a touched page the perimeter is what the change touches and the states it reaches; an old breach elsewhere on the page is listed as a note and does not count, as for old code.

## Findings

Every finding carries `file:line`, a measured number or the name of a screenshot, and the concrete action. One finding is one root cause: the same pattern in twelve places is one finding with its places listed, so splitting or merging findings cannot move the score. When the cause of such a finding is a shared component that repeats it across pages, an S3 rises to S2. The breach of a mechanical threshold is a finding too. Notes below S3, such as a preference of style or wording, are listed and do not count.

## Classes

| Class | Meaning | Examples |
|---|---|---|
| S1, critical | wrong or unsafe for a user, a piece of data or a service | a scenario that fails; an invariant contradicted by the code; a security or privacy problem, such as a write without a permission check; an operation with no way back; data lost or corrupted; a wrong result shown or computed; a crash on a main path; the text or the control of a primary action below WCAG AA |
| S2, serious | holds today, breaks with normal use or with growth | a missing or tautological test on a behaviour that changed; a new or changed test on a changed behaviour whose commits name no red, or name one the diff contradicts, closed when the red is seen now and named in the fix commit, which leaves no S3; a document contradicted by the code, such as an instruction that no longer works; a race without a lock or a constraint; a server error on bad input instead of a typed client error; a query that grows with the data; an import cycle or a dependency against the declared direction; a business rule in a view, a template or a serializer; error text leaking to clients; a page that does two jobs |
| S3, medium | debt, no wrong behaviour | a function over 40 lines or nested deeper than 3 without a written reason; a new catch-all exception handler; a twin of an existing helper; two names for one thing; repeated information on a page; a branch whose behaviour the work did not change, without a test; a red that its commit says was seen only after the code, except the red seen now to close the S2 above; a drifted count or path in a document whose instructions still work; jargon in text for people |

In doubt between two classes, take the more severe one; the second reviewer lowers it only with evidence. A failure of a WCAG 2.2 success criterion at level A or AA is at least S2, and S1 on a primary action, on whatever lens its line names.

## Mechanical thresholds

Each breach is a finding of the class in brackets, or of the higher class that the WCAG rule under the class table gives it. The checks are named for any language, and Python is used for example.

- `code`, `legacy` and `architecture`: a function over 40 lines or nested deeper than 3 (S3); the language's complexity checks, for example in Python the ruff rules C901, PLR0912, PLR0915 and PLR1702 (S3); a new catch-all handler (S3); a new lint suppression or `# taste-exempt:` comment without a reason (S3); a new entry in the ignore list of the import contracts (S2); a query to the data layer from a view or a template (S2).
- `api`: a route without an explicit permission check for its kind of caller (S1 on a write, S2 on a read); an error body outside the single error shape (S2); a public route without a rate limit (S2); a delivered contract whose shape changed with neither the user's go given after the notice nor the autonomy exception that `engineering-principles` describes (S1); a schema or a document that disagrees with the code (S2).
- `docs`: every claim checked against the code; each false instruction (S2); each drifted number or path (S3); a documentation build that fails in strict mode (S2).
- `clarity`: for each touched page, the elements, choices and words counted before and after; growth with nothing removed (S3); more than one primary action or job on a page (S2); a dead end in an empty, error or missing-permission state (S2).
- `aspect`: a component from outside the project's template without a written reason (S3); two names or two styles for one action (S3; two names for one function across pages fail WCAG 3.2.4); an error page outside the frame of the application (S2).
- `accessibility`: contrast in every state and in both themes (a primary action below AA, S1; any other text or control, S2); a target that fails 2.5.8, which asks 24 px outside the exceptions of that criterion (S2, S1 on a primary action); a touch target under 44 px on a touch device that meets 2.5.8 (S3, the AAA criterion 2.5.5); horizontal page scroll at any width of rule 12 of `interface-quality` (S2); a missing label or a missing visible focus (S2); axe violations by the impact axe gives them (critical S1, serious S2, moderate S3), and at least S2 when the rule is tagged with a WCAG criterion of level A or AA.
- The iron rules of `interface-quality`, each on the lens marked:
  - fidelity, on `aspect` when the breach is in how the page looks and on `clarity` otherwise: a deviation from the designer's document or the approved mockups without a written decision (S2); a block closed without an independent fidelity review (S2); real names of organisations or places in previews, mockups or placeholders (S3); a visible change not shown before and after, or missing from the before/after record (S3);
  - behaviour, on `clarity`: a widget that silently rewrites what the person typed (S2); two contradicting statements on one page (S2); a `data-label` different from its column header (S3); an interactive component never tried along real paths (S3, S2 when a defect is later found on such a path);
  - components: components touching or under 8 px apart (S3) and two components for one need (S3), on `aspect`; a hidden duplicate of the real field (S2), duplicate `id`s that detach a label from its field (S2) and other duplicate `id`s (S3), on `accessibility`;
  - on `accessibility`: a highlighted or selected option, a checked box or another state indicator below 3:1 against its neighbours (S2); content or function lost at 320 px (S2); text clipped, cut mid-word or overlapping at any width (S2 on a name or label the person needs, S3 otherwise); breakage at 200% zoom (S2); focus hidden behind a sticky element, or a focus order different from the visual order (S2); information carried by colour alone (S2); an outcome message that vanishes before it can be read or is not announced (S2); content lost with the text-spacing overrides (S2); states or focus invisible in forced-colours mode, or animation that ignores the prefers-reduced-motion setting (S3); a touched page not checked at every width of rule 12 (S3);
  - taste and restraint, on `aspect` and counted on the touched pages: an element without a task, a colour outside the palette, a text size beyond four or a weight beyond two, a spacing value off the scale of 4 or 8 px, a gradient, a decorative shadow or a decorative animation (S3); red for what neither destroys nor fails, a destructive action without confirmation or undo (S2); a dark theme made by inversion (S3);
  - words and help, on `clarity`: a button named "OK" or with a vague verb, words in capitals or exclamation marks (S3); an error that does not say how to fix it, or an empty state without the next step (S2); help that moves across pages (3.2.6) or data asked twice in one process (3.3.7) (S2);
  - a browser test that cannot go red (S2, on `code`);
  - any breach of an iron rule that no line of these thresholds names: the class that its meaning gives in the table of classes, on `aspect` for rules 5 and 13 to 21 except rules 17 and 19, on `accessibility` for rules 6, 7 and 12 and for a component that the keyboard cannot fully use, and on `clarity` for the others.

## The score

Start from 10 for each lens and apply, in this order:

1. each S1 takes 4 points away and caps the lens at 4;
2. each S2 takes 1.5 points away and caps the lens at 7;
3. each S3 takes 0.5 points away;
4. the floor is 1, and the result is rounded down to the half point.

So 8 means no S1, no S2 and at most four S3. Five S3 give 7.5. A reviewer never adjusts the result for an overall impression: if the number feels wrong, a finding is missing or misclassified.

## Who scores

Scores come from an independent review on the evidence, never from whoever did the work. The review lens, which is `blunt-review` and, on a git range, `blunt-reviewer`, scores `code`, `legacy`, `architecture`, `api` and `docs`. The UX lens of `interface-quality` scores `clarity`, `aspect` and `accessibility` on the real pages: screenshots in both themes at the widths and the zoom of rule 12 of `interface-quality`, measured contrast and targets, the axe result. Each lens re-checks the other's S1 and S2 findings on the evidence before the score stands. The user lens adds findings and never scores. The PM lens of `development-workflow` does not score: it collects the sheets, stops the gate when a lens is below 8, and proposes to the user the fix or a tracked deferral, each with its cost.

## The score sheet

One sheet for each lens in the perimeter. A change under three files that touches no interface and no contract uses one sheet, for the touched lens only.

```
Lens: <id>    Perimeter: <files, pages or routes; commit>
Findings:
  S1 <n> <evidence> -> <action>
  S2 <n> <evidence> -> <action>
  S3 <n> <evidence> -> <action>
Count: S1=<a> S2=<b> S3=<c>    Score: <computed>    Reviewer: <lens>    Re-checked by: <lens>
Not verified: <what could not be observed>
```

## Calibration

The rubric is calibrated at every use, without being asked. When the user's configuration has its own `quality-scoring`, its calibration log is the one written, and this paragraph does not apply. The log is `${CLAUDE_PLUGIN_DATA}/calibration.md`, in the plugin's data folder, which survives updates of the plugin and is deleted when the plugin is uninstalled from the last place it is installed, unless `--keep-data` is passed to the uninstall. Its first line holds the state, `CALIBRATING (k/5)` or `STABLE`, where `k` counts the consecutive applications without a signal. When the file does not exist, create it with the line `CALIBRATING (0/5)`.

While the state is calibrating, the scorer appends one entry at the end of every scoring (project, date, perimeter, scores and signals) and acts on its signals:

- **Disagreement:** two reviewers, or a reviewer and the re-checker, class the same finding differently, or the computed score is more than one point away from the one the reviewer would give at a glance. Write which definition or threshold caused it.
- **Missed defect:** a defect that people found later inside a perimeter that scored 8 or more. Write which class or threshold should have caught it.
- **Noise:** a finding that counted and that nobody would fix, or a threshold breached by code that everyone agrees is fine. Write the threshold.

A signal sets `k` back to 0. A signal that recurs, two entries that point at the same definition, becomes a proposal to the user with the exact change to this rubric and the entries as its evidence; the rubric never changes without the user. An accepted change is written in the log with its date and the reason, and it lives in the user's own instructions, which prevail over this skill, never in the files of the plugin, which an update replaces.

The state becomes `STABLE` after five consecutive applications without a signal and without a change to the rubric, on at least two projects, and the user is told in one line. While it is stable, a scoring adds one line only (project, date, scores), so that a later anomaly has its history. Calibration starts again only on an evident anomaly: a defect of class S1 or S2 found by people inside a perimeter that scored 8 or more, two reviewers two points or more apart on the same lens and the same evidence, or the user saying that a score is wrong. The state then goes back to `CALIBRATING (0/5)`, with the anomaly as its first entry.
