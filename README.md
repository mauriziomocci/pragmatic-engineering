# pragmatic-engineering

[Italiano](README.it.md)

pragmatic-engineering is an engineering method for Claude Code, put in order. It brings working rules to every agent of a session through one import line in your `CLAUDE.md`, and it adds twelve skills that cover the phases and the three lanes of the work, plus one agent, `blunt-reviewer`, that reviews a git range independently and bluntly. Version 0.1.0 is the core of the method: the rules, the skills, the reviewer and a `SessionStart` hook that keeps the rules in place. This version has no mechanical check on merge requests: the review before a merge request is a rule for the model, not a gate.

This page follows the four kinds of documentation of Diataxis (<https://diataxis.fr>), one section for each: a tutorial, how-to guides, an explanation and a reference, with the known limits between the last two. For every part of the method the explanation says what guarantees it: a mechanism, meaning code that runs whatever the model does, or only a rule for the model, meaning text the model is asked to follow and nothing checks.

<!-- section: tutorial -->
## Tutorial: a first guided session

You need Claude Code and a git project to work in. Each step says what you should see; if you see something else, stop there and read the install guide below.

1. Install the plugin as the install guide says. First check that `claude plugin marketplace list` shows `claude-plugins-official`, and add it as the guide says if it is missing; then run the two commands:

   ```
   claude plugin marketplace add mauriziomocci/pragmatic-engineering
   claude plugin install pragmatic-engineering@pragmatic-engineering
   ```

   You should see both commands finish without an error. If the plugin stays disabled and the message says that a dependency is not installed, the install guide explains why and what to do.

2. Start Claude Code in your project. At the top of the session the `SessionStart` hook prints two notes. The first reads "pragmatic-engineering: the rules file was updated; the updated rules apply from the next session."; it appears because the hook has just copied the rules file to the plugin's data folder. The second says that `~/.claude/CLAUDE.md` does not carry two lines yet and prints them: an import line that starts with `@`, and a long line that starts with "If the pragmatic-engineering rules".

3. Add the two lines to `~/.claude/CLAUDE.md`, after a dated copy of the file, as the install guide shows, then quit and start Claude Code again. You should see no notice this time. If the notice comes back, the lines are not written as printed: the hook looks for the import path and for the whole safety line.

4. Ask: "Quote your rule `PE:backup-diff-go`." You should see an answer that says that instruction, settings and memory files change only after a dated backup, a diff and your go. That rule lives in `rules.md` and in nothing else a session loads, not in the safety line and not in a skill, so a right answer shows that the import reached the session. If the model says it has no such rule, the import did not arrive: check the two lines of step 3 and ask again in a new session.

5. Ask for a small change with a test, for example a function with one behaviour. You should see, in this order: the model names the lane (a feature) and says in a few sentences what it is about to do, ending with "is it clear?"; it stops for your written approval of a short spec before the code, because the two heavy gates stay even for small work; it writes the failing test first and runs it; it writes the code; it reviews its own diff following `blunt-review` and closes with a statement that the tests pass or a list of what does not; it stops again for your approval of the result; it never pushes without your go.

6. Commit the work on a branch and say: "Review this branch before I open the merge request." You should see the model launch `blunt-reviewer` with one line, `<merge-base>..HEAD`, where `<merge-base>` is the commit `git merge-base` prints. The reviewer writes its report in `.pe/reviews/`, in a file named `<base7>..<tip7>-round1.md` whose first line is a status line, and its final message ends with five lines: `VERDICT:`, `FINDINGS:`, `COVERAGE:`, `REPORT:` and `THE THING:`. With `VERDICT: changes`, the blocking findings are fixed, committed, and a second review runs on the fixes; the explanation of the review cycle below says how it goes.

<!-- section: how-to -->
## How-to guides

<!-- section: install -->
### Install

Requirements: Claude Code, `python3` 3.9 or later on your path (the hook is a Python script), and git (the reviewer reads git ranges).

This plugin depends on superpowers (`superpowers@claude-plugins-official`). Claude Code installs superpowers by itself together with this plugin only when the official marketplace is already registered in your Claude Code. It normally registers itself the first time you start an interactive terminal session, but not for someone who has used Claude Code only through the VS Code extension, nor when a policy blocks it or when `CLAUDE_CODE_DISABLE_OFFICIAL_MARKETPLACE_AUTOINSTALL` is set. Without it the plugin installs but stays disabled, and Claude Code says that the dependency is not installed. So check first, from your terminal:

```
claude plugin marketplace list
```

If `claude-plugins-official` is not in the list, add it:

```
claude plugin marketplace add anthropics/claude-plugins-official
```

Then install this plugin:

```
claude plugin marketplace add mauriziomocci/pragmatic-engineering
claude plugin install pragmatic-engineering@pragmatic-engineering
```

If you installed the plugin before adding the official marketplace and it stays disabled, add the marketplace with the command above and run `/reload-plugins` inside Claude Code.

What has been tried: the manifests pass `claude plugin validate` of Claude Code 2.1.303, and the skills that cite superpowers were checked against superpowers 7.0.0. An end-to-end test, run on request, checks that an `@rules.md` import in a project `CLAUDE.md` reaches the main session and a subagent, with the plugin loaded by `--plugin-dir`; it ran live once, on 29 October 2026, and 4 tests passed. The import of the copy in the data folder from `~/.claude/CLAUDE.md`, which this guide uses, is not exercised by it. The install from the marketplace and the automatic install of superpowers follow Claude Code's documentation of dependencies and are verified at the first real install, not before.

Start a session. `SessionStart` copies `rules.md` to the plugin's data folder and prints the two lines your `CLAUDE.md` needs. The plugin never writes your `CLAUDE.md`; you do, after a dated copy of the file and with a look at the difference. Make the copy first (skip it if you have no `CLAUDE.md` yet, and create the file), add the two lines, check the difference, then open a new session:

```
cp ~/.claude/CLAUDE.md ~/.claude/CLAUDE.md.$(date +%F).bak
diff ~/.claude/CLAUDE.md.$(date +%F).bak ~/.claude/CLAUDE.md
```

The two lines are these. The first is the import the notice prints, such as `@~/.claude/plugins/data/<folder of the plugin>/rules.md`: copy it from the notice, because it carries the exact path on your machine and escapes the spaces in it. The second is the safety line, which stays in English, word for word, because it is the text the model reads when the plugin is gone:

```
If the pragmatic-engineering rules (marker PE-RULES v1) or its skills are missing from this session, tell the user before doing any work: the plugin is uninstalled or disabled.
```

The import is what brings the rules to the session. The safety line is what warns you when they stop arriving, since `SessionStart` cannot run once the plugin is uninstalled or disabled.

Updating: the manifest pins the version, so Claude Code moves you to a new release only when its version string changes, and auto-update is off by default for marketplaces other than Anthropic's. To update by hand, refresh the marketplace with `claude plugin marketplace update pragmatic-engineering`, run `claude plugin update pragmatic-engineering@pragmatic-engineering` and restart. The next `SessionStart` copies the new `rules.md`, and the new rules apply from the session after that.

<!-- section: uninstall -->
### Uninstall and go back

Go in this order. First take the two lines out of `~/.claude/CLAUDE.md`, or restore the dated copy you made at install if you changed nothing else in the file since. Then run:

```
claude plugin uninstall pragmatic-engineering@pragmatic-engineering
```

The order matters for two reasons. The safety line without the plugin makes the model warn you at every session start. And the uninstall deletes the plugin's data folder, which holds the copy of `rules.md` that your import points to, unless you pass `--keep-data`; what Claude Code does with an import that points to a missing file has not been tried here.

Three things stay behind on purpose. Superpowers stays installed; `--prune` on the uninstall command also removes dependencies that were installed automatically and are no longer needed. The marketplace stays registered until `claude plugin marketplace remove pragmatic-engineering`. And the `.pe/` folders that the reviewer and the progress note created in your projects stay: they hold review reports and notes, never enter git because each carries a `.gitignore` with `*`, and you delete them by hand if you want them gone.

<!-- section: maintainers -->
### Work on this repository

The tools below belong to this repository and are not part of the plugin. They protect the privacy of a repository built in the open, and they are used in the maintainer's clone:

- `tools/privacy_check.py` checks everything a push sends to the remote (for each pushed commit the added lines, the message, the author and committer names and emails, and the path of every file added or changed; the reference names; annotated tags) for the maintainer's private terms, listed in a file outside the repository that `git config pe.privateTermsFile` names, and for generic patterns such as home paths and recognisable tokens. It skips binary files and says so, and it fails closed.
- `tools/install_dev_hooks.py` copies that check, the project hook below and their filters into the clone's git directory, outside the working tree, and installs the `pre-push` hook that runs the copy; a change to the working tree takes effect only when the installer runs again. If the copy goes missing or breaks, a check that cannot run refuses the push or the tool; running `python3 tools/install_dev_hooks.py` again from your own terminal restores it. It refuses to overwrite a `pre-push` hook it did not write, and to install while `core.hooksPath` is set.
- `tools/dev_guard.py` is a Claude Code `PreToolUse` hook, registered in the maintainer's `.claude/settings.local.json` (a file git ignores) with the command `python3 "<copy>/tools/dev_guard.py" || exit 2` and `"onFailure": "block"`. The `|| exit 2` makes every exit other than 0 a block on any Claude Code version, a missing `python3` or a missing copy of the script included. `"onFailure": "block"` also blocks the tool when the hook times out, cannot start or prints output that fails validation; Claude Code reads it from version 2.1.295, and on an earlier version a timed-out hook does not block and the call goes on through the normal permission flow. It keeps an agent from skipping the check or switching hooks off, blocks MCP tools that write straight to a remote and raw API calls that write to pull requests, and checks the text of pull and merge request commands (`gh`, `glab` and MCP tools). It reads that text only where it is written, and blocks what the shell fills in at run time, with the hint to write it to a file first. The exact rules are in the module docstrings of `tools/dev_guard.py` and `lib/pe_guard/filters.py`.

Not covered. The filters read text and defend against an agent's haste, not against a determined bypass. Open, some by design and some not yet closed:

- other `gh` and `glab` commands that write text: releases, issues, gists, labels, repository settings;
- MCP tools that create branches or other objects, write issues, or comment on and review pull requests;
- raw API writes outside pull requests (repository contents, references, GitLab files and commits, a GraphQL commit mutation), and any call by `curl` or another client;
- `core.hooksPath` edited with the file tools (`git config` and `git -c` are blocked);
- `--no-verify` from the maintainer's own terminal;
- the check edited in the working tree, then installed: nothing guards the installer yet;
- files that a `-diff` rule of `.gitattributes` makes git report as binary: skipped, and the skip is listed;
- a term glued to other letters, before or after it (`myterm`, `MYTERM`, `terms`): terms match as whole words in any letter case, and only a non-letter or a capital that starts a new word (`myTerm`) marks the edge, so such forms must be listed too;
- forms the hook cannot see in the command: a call hidden in a script, alias, function or variable, or built inside `sh -c`; a program other than `xargs` that runs `gh` and supplies its text (`find -exec`, `parallel`); a quoted or escaped option name or command word; a folder change by a program other than `cd`, `pushd` or `chdir`; brace expansion and globs; a body file written under another spelling of its name, or by a script that does not name it;
- the `gh` flags that fill a pull request from elsewhere: templates, attachments, an earlier failed run, an editor, the browser, and commit messages, which the pre-push checks;
- sessions where the project hook is not loaded: it runs in the main clone and in worktree sessions started from the Claude desktop app (they read the main checkout's settings), not in a terminal session inside a linked worktree, where the pre-push still runs.

The exact lists of the hidden forms and of the `gh` flags are in the module docstrings of `tools/dev_guard.py` and `lib/pe_guard/filters.py`.

Tests: `python3 -m pytest -q` from the repository root. Requirements: Python 3.9 or later, pytest 7 or later, git 2.32 or later. The end-to-end check of the import starts Claude Code, so the default run leaves it out (tests marked `e2e`); run it on request with `python3 -m pytest -m e2e tests/e2e -v`.

The workflow `.github/workflows/ci.yml` runs the same suite on every push and pull request, on Python 3.9 and on the latest Python, and fails on a red. A second job runs ruff 0.12.8 with the rules C901, PLR0912, PLR0915 and PLR1702, in preview mode and with nesting limited to 3, on the Python files the change touches against the default branch, and fails on any finding. Two kinds of test do not run there: the end-to-end tests, which need Claude Code's credentials, and the check of the pinned superpowers names, which skips itself where superpowers is not installed. Ruff has no rule for functions over 40 lines: they are measured before the commit and in review.

<!-- section: explanation -->
## How it works

The seven parts below each end with a line that says what guarantees the part. In this version four things are mechanical: the `SessionStart` hook, which copies the rules and checks your `CLAUDE.md`; Claude Code's own `@` import, which delivers the rules file as your instructions; the `skills` field of the agent, which makes Claude Code load `blunt-review` and `quality-scoring` into it; and the `disable-model-invocation` field of the skill `autonomous-execution`, which keeps the model from starting it. Everything else is a rule for the model.

<!-- section: explain-lanes -->
### Three lanes

The lane comes from the nature of the work, and `development-workflow` states it. A feature (new behaviour or a structural change) goes through phases and gates. Support and incidents, from the ticket to the fix, put primary evidence before hypotheses and your own recent changes before external causes, with a shorter diagnosis and proposal instead of the full phases, and with a go on the proposal and a go before production. Operations on live systems load `safe-operations` before any command or tool that changes an external system: the active target is verified and stated, the blast radius and the way back are said first, and every run on production asks for its own go. When the lane is not clear, the model asks.

**Guaranteed by:** a rule for the model only (the rules `lanes` and `production-go` in `rules.md`, and the skills `development-workflow` and `safe-operations`). Nothing checks which lane the model picks or that the go was asked.

<!-- section: explain-gates -->
### Phases and gates

A feature goes through seven phases: idea and requirements, spec, plan, tasks, implementation, validation and closure. A phase starts only when the gate before it is closed. There are four gates: two heavy, the spec and the final validation, and two light, the plan and the task list. A heavy gate is a short synthesis, the question "is it clear?" and your written approval; a bare "ok" to a spec nobody read is not approval. A light gate is a quick coherence check. Implementation has no gate but an escalation: an unforeseen case, a wrong assumption or an incoherence with the existing code stops the task and goes back to whoever decides.

Small work (fewer than three files, an obvious fix, a configuration value) condenses the first four phases into a brief analysis, and keeps both heavy gates. The one exception is `autonomous-execution`, which only you can start, by naming it: its internal validation (the full suite and the review by `blunt-reviewer`) replaces the final gate, and your invocation is the go to push the work's branch and open its merge request, never to merge. The gate of the spec has no exception.

A feature uses one chain of tools, never two. By default it is superpowers (`superpowers:brainstorming`, `superpowers:writing-plans`, `superpowers:subagent-driven-development`, with `superpowers:test-driven-development` for every task); spec-kit only when you ask for it, and then `spec-driven-layout` says where its files live. The failing test comes first in both chains.

**Guaranteed by:** a mechanism for one thing: `disable-model-invocation` keeps the model from starting `autonomous-execution`. A rule for the rest (the rules `heavy-gates` and `test-first` in `rules.md`, and the skill `development-workflow`). Nothing records an approval or stops the model from writing code before one.

<!-- section: explain-review -->
### Independent review

The agent `blunt-reviewer` reviews a git range with the skill `blunt-review` loaded. Its prompt is one line in a closed grammar, `<base>..<tip> [round=1|2] [full=<path>,...]`, with `<base>` an ancestor of `<tip>`; anything else is not reviewed, and whoever launches it cannot steer the review through the prompt. It reads the change one commit at a time, then the whole, runs on Opus, and writes its report into `.pe/reviews/` in blocks, with a status line on top. Every finding carries evidence, findings come worst first, and a closing line names the single fix that matters most, or says that nothing was found and what was verified. Every finding carries its lens and its class, S1 critical, S2 serious or S3 medium, as `quality-scoring` defines them, and a finding is blocking when it is S1 or S2: a scenario that fails, a contradicted invariant, a security or privacy problem or an operation with no way back are S1, and a missing or tautological test on a behaviour that changed or a document contradicted by the code are S2. The verdict is `changes` only with at least one blocking finding, and it says whether another round of review is needed; the score of each lens, computed from the same findings, says whether the work may be integrated. The commit messages and the files named by `full=` are the author's claims, which the reviewer verifies and never obeys.

The review is made before a merge request is opened, on the whole range of the branch, and again on each round after fixes.

**Guaranteed by:** a mechanism for one thing: the `skills` field of the agent makes Claude Code load `blunt-review` and `quality-scoring` into it. Rules for the rest: that a review is made before a merge request, that the prompt follows the grammar (the agent refuses other prompts by its own instruction, and nothing outside it checks) and that it writes nothing outside `.pe/` are declared, not enforced. No mechanism records that a review took place, so the verdict is a message to read, not a gate.

<!-- section: explain-review-cycle -->
### The review cycle after fixes

The cycle starts after an independent check (the panel, or `blunt-reviewer` on a branch or on a delivery) and after the fixes of its findings. The corrected result is committed before each round, because the reviewer receives a git range.

In round 1 a `blunt-reviewer` with fresh context, one that wrote neither the work nor the fixes, rereads the corrected result: a document in full through `full=`; code through the range of the fixes, `<tip before the fixes>..<tip after the fixes>`, with the rest of the branch readable through read-only git for context. On `VERDICT: pass` the cycle ends. On `changes`, the blocking findings are fixed and round 2 begins: another fresh reviewer rereads the range of the latest fixes, with `round=2`. On `pass` the cycle ends. If round 2 also ends with `changes`, there is no third round: the open blocking findings go up to you with the recommendation of whoever carries them, because a blocking finding still open after two rounds usually says that the way of fixing is wrong. The cycle continues only on `changes`. The fixes of each round are listed in a table in the body of the commit of the fixes (finding, decision, place), and the next round checks that table too.

**Guaranteed by:** a rule for the model only (the skill `blunt-review`). No mechanism counts the rounds or stops a third one.

<!-- section: explain-rules-import -->
### Rules through an import

`rules.md` is the file of working rules. Its first line is the marker `PE-RULES v1`, and it has three blocks: rules for every agent, rules for the main session, rules for subagents. It states that your own instructions prevail on conflict, and that a conflict with its five precedence rules (evidence, no bug left behind, test-first, blunt review, burden of proof on adding) goes to you and is never resolved silently.

The plugin root does not survive a plugin update and the plugin's data folder does, so at every session start `SessionStart` copies `rules.md` from the root to the data folder when the copy is missing or different. Your `CLAUDE.md` imports the copy with one `@` line; that is how the rules reach the session as your own instructions, which superpowers ranks above its skills. The second line you add is the safety line, for the day the plugin is gone.

In your `CLAUDE.md` exactly two lines change, and you add them yourself: the hook only reads the file and prints what is missing. The rules reach the main session and the subagents that load your `CLAUDE.md`; they do not reach `Explore`, `Plan` and agents defined with `omitClaudeMd: true`. A rules update applies from the next session. An end-to-end test, run on request, gives evidence about Claude Code's import; it is not a mechanism of the plugin and does not run in your session (the install guide says what it covers).

**Guaranteed by:** a mechanism for the delivery: the hook copies and checks, and Claude Code's `@` import brings the file in. A rule for the compliance: the model is asked to follow the rules, and nothing checks that it does.

<!-- section: explain-continuity -->
### Continuity

Work is saved ahead, in three forms, all described by `continuity-note`. The progress note is the state on a few lines (done, in progress, next, open decisions), updated at every milestone and read again after a compaction; it lives in `.pe/progress.md` at the root of the repository, with a `.pe/.gitignore` that contains `*`, unless the project declares its own. The deliverable file of a task given to a subagent is written in blocks and carries a status line on top, `STATUS: IN PROGRESS - done: ...; next: ...`, which the last block replaces with `STATUS: COMPLETE`. The full continuity note is written when a session ends with work in progress or when work passes to another agent, so that a fresh context resumes without replaying the conversation.

**Guaranteed by:** a rule for the model only (the rules `save-ahead` and `status-line` in `rules.md`). Nothing counts the saves, so a compaction loses at most the work done since the last save, and how small that is depends on the model's discipline.

<!-- section: explain-communication -->
### How the plugin talks to you

The model explains briefly and at a high level at four moments: at the start and at the end of a work block, at every architecture choice (the choice, the main alternative discarded and why) and before a heavy gate. Each explanation ends with "is it clear?" in your language, and what you say is unclear is explained again with different words and an example. The answer is awaited only at the two heavy gates and at architecture choices; there is no quiz and no verification question, ever. The tone is frank: no agreeing to please, no flattery, weak reasoning challenged with evidence, risks and opportunity costs named, and a guess about your intent labelled as a guess. The skill `teach` carries the explanations and the method for teaching code; the rules file carries the tone.

**Guaranteed by:** a rule for the model only (the rules `explain`, `no-quiz` and `candour` in `rules.md`, and the skill `teach`). "Is it clear?" does not prove that you understood, and the tone rules reduce the model's tendency to agree, they do not remove it.

<!-- section: limits -->
## Known limits

The limits that describe Claude Code's own behaviour (which agents load `CLAUDE.md`, Cowork, compaction) come from its documentation as read while the plugin was designed. The plugin's tests do not exercise them, apart from the import itself.

- There is no mechanical check on merge requests: the review before one is a rule for the model, and the verdict of `blunt-reviewer` is a message to read, not a gate.
- The rules do not reach `Explore`, `Plan` and agents with `omitClaudeMd: true`, because they travel in your `CLAUDE.md`.
- Cowork skips imports that point outside its working folder, so the rules do not arrive there.
- An update of the rules file applies from the session after the one that copied it.
- Whether a subagent that Claude Code has compacted keeps the imported rules is not verified.
- With the plugin uninstalled or disabled, `SessionStart` does not run, and only the safety line in your `CLAUDE.md` warns you.
- "Is it clear?" does not prove understanding, and the tone rules reduce the model's tendency to agree without removing it.
- Continuity loses at most the work done after the last save, and depends on the model's discipline because nothing counts the saves.
- The grammar of the `blunt-reviewer` prompt and the fact that it writes no file outside `.pe/` are declared in the agent, not enforced.
- Superpowers installs by itself only when the official marketplace is already registered in your Claude Code; otherwise this plugin stays disabled until you add it (see the install guide).
- The version is pinned in the manifest, so an update reaches you only when the version string changes and you ask for it, unless you turn auto-update on.
- If you already have a plugin named superpowers from another marketplace, Claude Code's documentation says that both appear as enabled and that the hooks of one of them are left out; this has not been tried here.
- The plugin was tried on macOS only; the CI runs the repository's tests on Linux.

<!-- section: reference -->
## Reference

There are no commands in this version.

### Skills

Claude Code loads a skill when the task matches its description, unless the table says otherwise.

| Skill | What it does | When it loads |
|---|---|---|
| `engineering-principles` | Understand before implementing, reuse before building, design and placement principles, test discipline, no bug left behind, secure coding, secrets hygiene, writing rules. | Before understanding a requirement, proposing an approach, or writing or changing code, tests or documentation; not for plainly trivial work. |
| `evidence-based-investigation` | Verify before asserting, state the confidence level, rule out hypotheses one by one, scope a defect in four steps, separate verified from inferred. | Investigations, diagnoses and technical answers where a wrong conclusion has a cost; not for design or review. |
| `blunt-review` | How a review is written and when a finding blocks; lenses for design, tests, documentation, infrastructure and diagnosis; the independent review and the review cycle after fixes. | Every review, self-review included. Preloaded in `blunt-reviewer`. |
| `quality-scoring` | A score from 1 to 10 for each lens the work touches, computed from findings classed S1, S2 or S3; who scores which lens; the score sheet; the calibration log in the plugin's data folder. | Every review that feeds the 8/10 gate of phase 6, before work is integrated or released. Preloaded in `blunt-reviewer`. |
| `adversarial-review-panel` | Four lenses that argue against each other, a cross-examination, and one decision. | Decisions where being wrong is expensive: architecture, specs, risky refactors, security, technology choices, data models; not for ordinary reviews. |
| `development-workflow` | The three lanes, seven phases and four gates, one chain per feature, the design in three steps, models by role, instruction layers, closure. | Any work on code, a release, a merge or a closure. |
| `spec-driven-layout` | Where spec-kit keeps its files and how much to write for the weight of the work. | Only when you ask for spec-kit. |
| `autonomous-execution` | Runs an approved spec unattended up to the opening of its merge request, recording the decisions it takes alone. | Only when you invoke it by name; the model never loads it on its own. |
| `teach` | Brief explanations followed by "is it clear?", the six-layer method for teaching code, the state on one screen on resume. | When you ask how code works or to be taught, when a session resumes, before a heavy gate. |
| `continuity-note` | The continuity note, the progress note and the status line of deliverable files. | When work passes to another agent or session, and at every milestone in its short form. |
| `safe-operations` | Verify the target, dry run, say the blast radius and the way back, a separate go for production, never poll, verify at every level. | Before a command or tool that changes an external system. |
| `interface-quality` | The ten principles of a simple interface, the measures before a change (every state, both themes, 375, 768 and 1280 px, WCAG AA measured), the UX study before code, the UX lens and the user lens. | Every change to a user interface, and to the responses, messages and documentation of an API. |

### Agent

`blunt-reviewer`: model Opus; tools Read, Grep, Glob, Bash and Write; preloads `pragmatic-engineering:blunt-review` and `pragmatic-engineering:quality-scoring`. It accepts one line, `<base>..<tip> [round=1|2] [full=<path>,...]`, writes `.pe/reviews/<base7>..<tip7>-round<k>.md` and ends with `VERDICT: pass | changes`, `FINDINGS: <n> (<b> blocking; <lens> S1=<a> S2=<c> S3=<d>; ...)`, `COVERAGE: full | partial`, `REPORT: <path>` and `THE THING: <...>`. The main session launches it before a merge request, for a delivered range, and for each round of the review cycle.

### Hook

`SessionStart`, registered in `hooks/hooks.json` as `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/session_start.py"`, with a timeout of 10 seconds. At every session start it copies `rules.md` to the plugin's data folder when the copy is missing or different, checks that `~/.claude/CLAUDE.md` carries the import of the copy and the safety line, and prints the lines that are missing, to you and to the model with the same text. It never blocks and never fails a session start: a problem becomes a notice. It stays silent when the rules are in place and nothing changed.

### Files

`rules.md` is the working rules file, starting with the marker `PE-RULES v1`. The `.pe/` folder, at the root of a project, holds `reviews/` (the reports of `blunt-reviewer`) and `progress.md` (the progress note), and it never enters git because of its own `.gitignore` with `*`.

<!-- section: license -->
## License

MIT, see [LICENSE](LICENSE). The works this plugin builds on are credited in [NOTICE](NOTICE).
