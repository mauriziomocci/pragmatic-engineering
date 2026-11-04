---
name: interface-quality
description: Use for every change to a user interface, and to the responses, messages and documentation of an API. The ten principles of a simple interface, the twenty-two iron rules that hold before a change is proposed (fidelity to the designer's document and mockups, every state in both themes, widths from 320 to 1440 px and 200% zoom, WCAG 2.2 AA measured, keyboard and screen reader, taste and restraint, scripted screenshots and axe), the UX study approved before code, and the UX lens and the user lens that judge the change.
---

# interface-quality

This skill holds the bar of a good interface, measured, and the two lenses that judge it: the UX lens, which proposes from the need of the person who uses the product, and the user lens, which tries the change as that person would. The review lens lives in `blunt-review`; the scores of all of them follow `quality-scoring`.

## When to use

- Before a change to a user interface is proposed, committed or integrated: a page, a component, a navigation, a message shown to people.
- On a server, before the spec of a change to the responses, bodies, error messages or documentation of an API: for the developer of a client, the API is the interface.

Every brief to a session that touches an interface carries the bar of this skill.

## Simplicity first

The default answer to "one more element on this page?" is no: the person wants the shortest path to the task. Ten principles, which apply the established practice of usability (fewer choices per screen, recognition over recall) and are checked in every review of an interface like the thresholds of code:

1. One page, one job, one primary action.
2. Pages are grouped by the topics the person recognises, with tasks as secondary entry points; never by data table, internal name or organisation chart.
3. One name for each thing, the same on every page, in the plain language of the person who uses it.
4. Progressive disclosure: defaults instead of choices, details on request.
5. No repeated information on a page, and no text that explains the obvious.
6. Components come first from the project's interface template, used as they are, except the spacing and fusion that rule 5 forbids; a new component only where the template has none, with the reason written. The project's configuration names the template. Principles may come from other design systems, never their components inside the project's template.
7. Every state of a page (empty, error, loading, read-only, missing permission) says what to do next: no dead ends, and no link to a page where the action is impossible.
8. The review counts the elements, choices and words of the touched page and names what to remove; a page that grew without removing anything is a finding.
9. Navigation and menus are ordered by importance or by natural groups, never alphabetically, except an index from A to Z.
10. Structure first, then navigation: the content page first, then the lists, and the home or overview page last.

## Iron rules

Every proposal, review and score of an interface, dashboards and front ends alike, holds these rules before a change is proposed, committed or integrated; a breach is a finding, classed by `quality-scoring`: by name where its thresholds name the breach, by the meaning of the three classes otherwise. Rules 1 to 12 and 22 are on fidelity, measurement and accessibility, rules 13 to 21 on taste and restraint. Both themes means light and dark, and every measure is taken, never judged by eye. A project with one theme measures the theme it has, and rule 20 applies once it has a dark one.

1. **The designer's document decides.** Each page follows the designer's document and the approved mockups point by point; a deviation is a defect unless a written decision in the spec or the decision log gives its reason, and an addition the document does not ask for is said. Each block of work closes with a fidelity review, page by page, by someone who did not build it.
2. **Mockups before templates.** When the interface has to be invented, with no precise sketch from the designer, screenshots of the page as it is and mockups built from the real page's HTML, both made by a script, go to the ticket or a shared document before the real templates, after a fidelity review against the source by someone who did not draw them; no theme component the document did not ask for.
3. **Before and after, shown.** Every visible change is shown to the user in a browser the session drives, on an isolated preview, with how it was, how it is and what changes for whoever uses it, and goes in the project's before/after record with screenshots in both themes made by a script.
4. **Generic demo data.** Previews, screenshots, mockups and placeholders carry invented names and example.com, never real organisations, public bodies or places.
5. **Components never touch.** A field and its button, buttons side by side, filters and chips, a badge and its text, row and form actions: at least 8 px apart, never fused into one control by the theme, measured on every page in both themes at the widths of rule 12, with a browser test that fails when two touch again.
6. **Every state measured, both themes.** Every touched component (menu item, button, link, field, table row) at rest, hover, focus, pressed or active, open menu, disabled and error: text at least 4.5:1; large text, focus rings and non-text indicators (a highlighted or selected option, a checked box) at least 3:1, on the real background of that state. Colours only from the theme's tokens, and under an override of the dark theme the proof that the new rule wins. The designer's palette stays: WCAG 1.4.11 asks no 3:1 for the border of a button its text identifies.
7. **Touch targets of 44 px on touch devices.** One shared rule under `@media (pointer: coarse)`, with the mouse layout unchanged and pinned by tests; 44 px is the AAA criterion 2.5.5, and AA (2.5.8) asks for 24 px.
8. **One shared component per need.** One date and time picker, one searchable select, one collapsible section, one character counter for the whole product, initialised once; the real field keeps its `id`, label and `aria-describedby`, with no hidden duplicate of it; full use by keyboard; accessible names in the person's words.
9. **Never rewrite in silence what the person typed.** A widget that clamps, rounds or rewrites typed input is a defect: the server rejects a value out of range with its message under the field.
10. **Try it as a person would, not only by script.** Each interactive component is also used step by step in a browser the session drives, along real paths: open, type, close with Esc, reopen, paste, choose with Enter. Automated tests miss what a person does next, and each defect found that way gets a test written red first.
11. **Unique `id`s and one name for each thing.** No duplicate `id` on a page, so that each label points to its own field; a column's `data-label` equals its header; one action has one name and one way on every page; a page never says two contradicting things.
12. **Accessible at every width and zoom.** Each touched page, in both themes, at 320 px (WCAG 1.4.10 reflow, equal to 1280 px at 400% zoom), 375, 768, 1024, 1280 and 1440 px, and at 200% zoom (1.4.4): no horizontal scroll except a data table inside its own box; no text clipped, truncated or overlapping, labels on maps and charts and long names included (wrap, or abbreviate with the full text available, never cut mid-word); no content or function lost; tables readable as stacked cards. Also: the text spacing of 1.4.12 (line height 1.5, letters 0.12em, words 0.16em, paragraphs 2em) without loss; portrait and landscape (1.3.4); focus never hidden by a sticky header, footer or overlay (2.4.11) and in the visual order at every width; mouse targets of at least 24 px (2.5.8); the prefers-reduced-motion setting respected; nothing carried by colour alone (1.4.1); borders, focus and states visible in forced-colours mode; the page language and each control's name, role and state exposed to screen readers, checked with axe and with a spot check by a screen reader, such as VoiceOver or NVDA, on the main path.
13. **Every element earns its place.** Each element answers "which task does it serve?", or it goes: no decoration, ornamental icons, boxes inside boxes or text explaining the obvious. Minimal, not bare: what a task needs stays.
14. **Colour only for meaning.** Colour marks the primary action, states and errors, nothing else: no gradients, decorative shadows or colour to liven things up; red only for what destroys or fails; at most one accent colour per view besides the state colours.
15. **Fixed scales, never values made up on the spot.** Spacing in multiples of 4 or 8 px from the tokens; at most 4 text sizes and 2 weights per page; one scale of corner radii and one of elevation; edges aligned on one grid.
16. **Clear hierarchy.** One primary button per view, a button and never a bare link, next to the related buttons; destructive actions secondary, with confirmation or undo; text aligned left, lines of prose within 60 to 80 characters; numbers aligned right in tables, units in the header.
17. **Words that say the outcome.** A button names what happens ("Save notification", never "OK"); sentence case, no exclamation marks, no words in capitals; an error says what happened and how to fix it; an empty state says what to do next.
18. **Proportionate feedback.** Every action answers at once, and after one second a loading signal appears; outcome messages stay until they can be read (2.2.1) and are announced to screen readers without interrupting; no decorative animation, nothing that moves by itself.
19. **Cognitive accessibility (WCAG 2.2).** Plain language for people with little confidence in digital tools; help in the same place on every page (3.2.6); no data typed twice (3.3.7); sign-in without puzzles (3.3.8); confirmation or undo for what cannot be undone (3.3.4).
20. **The dark theme is designed, not inverted.** Lighter surfaces mark elevation instead of shadows; no pure black or pure white; desaturated accents; every state measured on its own.
21. **Taste is measured.** On each touched page the review counts colours outside the palette, text sizes, spacing values off the scale, primary actions and elements without a task, besides the counts of principle 8; each kind of excess is one finding, with its pages listed, so taste is a number and not an opinion.
22. **Proof travels with the change.** Screenshots made by a script in both themes at the widths of rule 12, axe with no contrast or label violation, and browser tests that can go red: a test that accepts the theme's always-present default is not a test.

The plugin prescribes axe and does not ship it. Nor does it ship the browser to drive, the script for the screenshots or the browser tests: the project provides them. In a project with a CI, axe runs there on the main pages in both themes and fails the pipeline on contrast and labelling; until it does, it runs locally and its result is reported.

## The UX study

Every new or changed page has a UX study approved before its code. The UX lens prepares it and the project's designer signs it, where the project has one, and otherwise the user approves it: the study prepares the approval and never replaces it. Small details follow the signed study; product choices go to the user.

## APIs are an interface

On a server the API is the experience of the developer who builds the client. On responses and bodies, the names and the meaning of values, the messages shown to people, the consistency across routes and what the client's developer understands from the documentation, the UX lens has its say before the spec, always inside the rule on delivered contracts of `engineering-principles`: a delivered contract never changes shape. So the UX lens works on texts, descriptions and choices among existing values.

## The round of the lenses

A skill of the user's configuration that covers these lenses is loaded first. On every change to an interface or to an API, except a trivial text fix, one round, before the spec:

1. Before proposing, the UX lens measures what the change touches as it is: every touched state and its contrast in both themes, and the widths and the zoom of rule 12; for an API, the routes as they answer today.
2. The UX lens proposes from the need of the person who uses the product. It runs as a subagent on Opus, briefed with this skill, the touched pages or routes and the person's task. When the user's configuration names its own agent for this lens, that agent runs it.
3. The review lens (`blunt-review`) attacks on evidence, cost, the simpler alternative and the impact on code and architecture.
4. The user lens walks the main task of the touched pages, or the client's flow for an API, and its findings reach the UX lens with the attack.
5. The UX lens answers or changes the proposal.
6. Then the decision: on the person's need the UX lens prevails, on correctness, evidence and the quality of the code the review lens prevails. A disagreement that survives goes to the user, or to the PM lens under an autonomy that opens `spec` (`development-workflow`), and to the project's designer where there is one, with both positions.

Neither lens agrees by default. Each re-checks the other's claims on the screenshots, the measurements and the code before accepting them, and an agreement without an independent check is a finding. The UX lens scores clarity, aspect and accessibility with `quality-scoring`.

## The user lens

The user lens tries the change as the person who will use it, and it never decides: it reports findings, with no vote and no score. It runs as a subagent on Sonnet, never Haiku. When the user's configuration names its own agent for this lens or its own file of personas, those are used instead. It takes at most three personas from the project's file of personas, chosen for the need, and one real task at a time; it works from the screenshots, never from the code, and at every step it answers four questions as the persona:

1. Do I know what to do here to move towards my goal?
2. Do I see the control that does it, where I would look for it?
3. Do the label and the icon tell me, in my words, that it is the right one?
4. After acting, do I understand that it worked, or what went wrong and what to do now?

A "no" or a hesitation is a finding, with the step, the page and the screenshot or `file:line`; in doubt, assume the persona does not understand. Until the project has the script for the screenshots, the findings carry the label "from templates, not seen on screen", and building that script is a tracked task. On an API the persona is the developer of the client, who works from the documentation alone and reports where they would not know what to call, what to send, what comes back or which error to expect.
