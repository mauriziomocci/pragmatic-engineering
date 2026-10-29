# pragmatic-engineering

[Italiano](README.it.md)

pragmatic-engineering is an engineering method for Claude Code, put in order. It brings working rules to every agent of a session through one import line in your `CLAUDE.md`, and it adds skills that cover the phases and the three lanes of the work, plus one agent, `blunt-reviewer`, that reviews a git range independently and bluntly. Version 0.1.0 is the core of the method: the rules, the skills, the reviewer and a `SessionStart` hook that keeps the rules in place. This version has no mechanical check on merge requests: the review before a merge request is a rule for the model, not a gate.

This page follows the four kinds of documentation of Diataxis (<https://diataxis.fr>), one section for each: a tutorial, how-to guides, an explanation and a reference, with the known limits between the last two. For every part of the method the explanation says what guarantees it: a mechanism, meaning code that runs whatever the model does, or only a rule for the model, meaning text the model is asked to follow and nothing checks.

<!-- section: tutorial -->
## Tutorial: a first guided session

You need Claude Code and a git project to work in. Each step says what you should see; if you see something else, stop there and read the install guide below. Steps 1 and 3 run in a terminal, and from step 4 you type into the session. Do step 3 yourself: the rules are not loaded yet, so nothing makes the session back up the file first.

1. Install the plugin as the install guide says. First check that `claude plugin marketplace list` shows `claude-plugins-official`, and add it as the guide says if it is missing; then run the two commands:

   ```
   claude plugin marketplace add mauriziomocci/pragmatic-engineering
   claude plugin install pragmatic-engineering@pragmatic-engineering
   ```

   You should see both commands finish without an error. If the plugin stays disabled and the message says that a dependency is not installed, the install guide explains why and what to do.

2. Start Claude Code in your project. At the top of the session the `SessionStart` hook prints two notes, both in English. The first reads "pragmatic-engineering: the rules file was updated; the updated rules apply from the next session."; it appears because the hook has just copied the rules file to the plugin's data folder. The second says that `~/.claude/CLAUDE.md` does not carry two lines yet and prints them: an import line that starts with `@`, and the safety line, a long line that starts with "If the pragmatic-engineering rules".

3. Add the two lines to `~/.claude/CLAUDE.md`, after a dated copy of the file, as the install guide shows, then quit and start Claude Code again. You should see no notice this time. If the notice comes back, the lines are not written as printed: the hook looks for the import path and for the whole safety line. Silence alone does not show that the hook ran; to check, run `ls -l` on the path that follows the `@` in your import line: it lists `rules.md`, which shows only that the hook copied it at least once (at step 2), not that it ran at this start, and an error that the file is missing means the hook has not run. Step 5 is the check that the rules arrive.

4. Ask: "Configure the plugin." You should see the model show, in a few lines, the values the keys have now, an unset one said to be unset, and ask which keys you want to set; then one question at a time about those keys, each saying what the key does, what happens while it is unset and a value it proposes (for the autonomy profile you choose the openings, and it proposes none). Before it changes anything it shows you the exact `git config` command and waits for your yes, then reads the value back, for the autonomy profile too. You can answer that you want none: nothing changes until you say yes to a command.

5. Ask: "Quote your rule `PE:lanes`." (you can also ask it in your own language). You should see an answer that says that the lane comes from `development-workflow` and that a feature uses one chain of tools, superpowers by default and spec-kit when you ask for it or the project adopted it. The label `PE:lanes` is in `rules.md` and in nothing else a session loads, not in the safety line and not in a skill, so a right answer shows that the import reached the session. If the model says it has no such rule, the import did not arrive: check the two lines of step 3 and ask again in a new session.

6. Ask for a small change with a test, for example a function with one behaviour. You should see, in this order: the model names the lane (a feature) and says in a few sentences what it is about to do, ending with "is it clear?" in your language; it stops for your written approval of a short spec before the code, because the two heavy gates stay even for small work; it writes the failing test first and runs it; it writes the code; it reviews its own diff following `blunt-review` and closes with a statement that the tests pass or a list of what does not; it stops again for your approval of the result; it never pushes without your go.

7. Commit the work on a branch and say: "Review this branch before I open the merge request." (you can also say it in your own language). You should see the model launch `blunt-reviewer` with one line, `<merge-base>..HEAD`, where `<merge-base>` is the commit `git merge-base` prints. The reviewer writes its report in `.pe/reviews/`, in a file named `<base7>..<tip7>-round1.md` whose first line is a status line, and its final message ends with five lines: `VERDICT:`, `FINDINGS:`, `COVERAGE:`, `REPORT:` and `THE THING:`. With `VERDICT: changes`, the blocking findings are fixed, committed, and a second review runs on the fixes; the explanation of the review cycle below says how it goes.

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

What has been tried: the manifests pass `claude plugin validate` of Claude Code 2.1.303, and the skills that cite superpowers were checked against superpowers 7.0.0. An end-to-end test, run on request, checks that an `@rules.md` import in a project `CLAUDE.md` reaches the main session and a subagent. One test, which asks the main session for the probe value, loads the plugin with `--plugin-dir`; three run without the plugin: two of these can receive the rules only through the import, and the third checks the safety line with no rules file. The whole test ran live once, on 29 October 2026, and 4 tests passed. The import of the copy in the data folder from `~/.claude/CLAUDE.md`, which this guide uses, is not exercised by it. The install from the marketplace and the automatic install of superpowers follow Claude Code's documentation of dependencies and are verified at the first real install, not before.

Start a session. `SessionStart` copies `rules.md` to the plugin's data folder and prints the two lines your `CLAUDE.md` needs. The plugin never writes your `CLAUDE.md`; you do, after a dated copy of the file and with a look at the difference. Make the copy first (skip it if you have no `CLAUDE.md` yet, and create the file), add the two lines, check the difference, then open a new session:

```
cp ~/.claude/CLAUDE.md ~/.claude/CLAUDE.md.$(date +%Y%m%d-%H%M%S).bak
diff "$(ls -t ~/.claude/CLAUDE.md.*.bak | head -1)" ~/.claude/CLAUDE.md
```

The time in the file name keeps a second copy from overwriting the first, and the second command, run after the edit, prints the two lines you added, each marked with `>`.

The two lines are these. The first is the import the notice prints, such as `@~/.claude/plugins/data/<folder of the plugin>/rules.md`: copy it from the notice, because it carries the exact path on your machine and escapes the spaces in it. The second is the safety line, which stays in English, word for word, because it is the text the model reads when the plugin is gone:

```
If the pragmatic-engineering rules (marker PE-RULES v1) or its skills are missing from this session, tell the user before doing any work: the plugin is uninstalled or disabled.
```

The import is what brings the rules to the session. The safety line is what warns you when they stop arriving, since `SessionStart` cannot run once the plugin is uninstalled or disabled.

Then allow the reviewer's git reads. Claude Code (checked with 2.1.303) asks approval for every `git show` and `git diff` with the options the reviewer must use: in a session with you it asks at each read, and in a run without a person (`claude -p`) the reviewer reads nothing. Add these two rules to the `allow` list under `permissions` in `~/.claude/settings.json`, after a dated copy of the file as for `CLAUDE.md`:

```
Bash(git show --no-color --no-ext-diff --no-textconv --no-relative --ignore-submodules=none:*)
Bash(git diff --no-color --no-ext-diff --no-textconv --no-relative --ignore-submodules=none:*)
```

Updating: the manifest pins the version, so Claude Code moves you to a new release only when its version string changes, and auto-update is off by default for marketplaces other than Anthropic's. To update by hand, refresh the marketplace with `claude plugin marketplace update pragmatic-engineering`, run `claude plugin update pragmatic-engineering@pragmatic-engineering` and restart. The next `SessionStart` copies the new `rules.md`, and the new rules apply from the session after that.

<!-- section: configure -->
### Configure the plugin

The quickest way is to ask in a session, for example "configure the plugin": the `configure` skill shows the values you have now and asks one question at a time, only about the keys you choose, and runs each command only after your yes. It sets the autonomy profile only when you ask for it in chat, never on its own and never because a file or a tool output says so; nothing checks that it obeys. Or set the keys by hand, with the guides "Set your office hours" and "Let the work go on without you" below.

The keys the plugin reads, and one that its maintainer tools read:

| Key | What it sets | Where | When unset | Example |
|---|---|---|---|---|
| `pe.officeHours` | The office-hours window, from the first hour up to the second, which is outside it | Global | The rule is off | `06-21` |
| `pe.weekendFrom` | The hour from which Saturdays, Sundays and holidays open | Global | They open at the start of the window | `10` |
| `pe.holidays` | The holidays: `MM-DD`, `easter+N` or `easter-N`, separated by commas | Global | No date is a holiday | `01-01,12-25,12-26,easter+1` |
| `pe.personalRemotes` | The prefixes of the push URLs of your own remotes; it takes more than one value | Global | No remote is personal | `https://github.com/<you>/` |
| `pe.autonomy` | What the lenses may decide while you are away, from `spec`, `schema`, `design` and `contract` | Local: in the repository you set it in | The profile opens nothing | `spec,schema` |
| `pe.privateTermsFile` | The file of private terms that `tools/privacy_check.py` reads; only for those who work on this repository | Any level, read with `git config --get`; usually the clone of this repository | The privacy check refuses to run | `<path outside the repository>` |

The four global keys tell the model when to keep your work local and which remotes are yours, and the autonomy profile tells it which decisions it may take while you are away; in this version both are rules for the model, and nothing blocks a push outside the window. To remove a key, run `git config --global --unset-all pe.<key>` for a global one, or `git config --local --unset pe.autonomy` for the profile.

<!-- section: uninstall -->
### Uninstall and go back

Go in this order. First take the two lines out of `~/.claude/CLAUDE.md`, or restore the dated copy you made at install if you changed nothing else in the file since. Then run:

```
claude plugin uninstall pragmatic-engineering@pragmatic-engineering
```

The order matters for two reasons. The safety line without the plugin makes the model warn you at every session start. And the uninstall deletes the plugin's data folder, which holds the copy of `rules.md` that your import points to and `calibration.md`, the calibration log of `quality-scoring`, unless you pass `--keep-data`; what Claude Code does with an import that points to a missing file has not been tried here.

Five things stay behind on purpose. Superpowers stays installed; `--prune` on the uninstall command also removes dependencies that were installed automatically and are no longer needed. The marketplace stays registered until `claude plugin marketplace remove pragmatic-engineering`. The `.pe/` folders that the reviewer and the progress note created in your projects stay: they hold review reports and notes, never enter git because each carries a `.gitignore` with `*`, and you delete them by hand if you want them gone. The `night-backup-*` tags that `skills/safe-operations/recreate_night_commits.py` leaves in your repositories stay until you delete each one with `git tag -d <name>`. And the `pe.*` keys you set stay in your git configuration; the configure section above says how to remove them.

<!-- section: office-hours -->
### Set your office hours

The plugin reads a few keys of your global git configuration. Set them once, from a terminal or by asking the model in a session (it shows you each command and runs it after your yes), with `pe.personalRemotes` in the same step as `pe.officeHours`:

```
git config --global pe.officeHours 06-21
git config --global pe.weekendFrom 10
git config --global pe.holidays 01-01,12-25,12-26,easter+1
git config --global pe.personalRemotes https://github.com/<you>/
```

`pe.officeHours` is the window, from the first hour up to the second, which is outside it: `06-21` runs from 06:00 up to 20:59, in local time; `none`, or no value, turns the rule off. `pe.weekendFrom` is the hour from which Saturdays, Sundays and the dates of `pe.holidays` open; without it they open at the start of the window. `pe.holidays` lists the days you do not work, separated by commas, each `MM-DD` with the month first, or `easter+N` and `easter-N` with N days from Gregorian Easter: `easter+1` is Easter Monday. `pe.weekendFrom` and `pe.holidays` count only while `pe.officeHours` gives a window. `pe.personalRemotes` says which remotes are yours: a remote is personal only if every push URL it has starts with one of its values, and `git remote -v` lists those URLs; the closing slash keeps `<you>` from matching `<you>2`. For an SSH remote add a second value, `git config --global --add pe.personalRemotes git@github.com:<you>/`, and any other remote works the same way with its own prefix; without any value no remote is personal, so outside the window not even your own repositories receive a push. To read back every key with the file it comes from, run `git config --show-origin --get-regexp '^pe\.'`; git prints the key names in lowercase, and nothing checks the form of a value, so compare what it prints with the examples above.

<!-- section: autonomy -->
### Let the work go on without you

An autonomy lets the lenses take, while you are not there, the decisions it opens; each one is provisional, logged and reported to you first. For one piece of work or one day, say it in chat with a hard stop, the hour at which the work must stop, for example "go on without me until 18:00, but leave the data model to me": it opens `spec`, `schema` and `design`, explained below, unless your words narrow it. For one repository, set the profile inside that repository, naming only what you open, either from a terminal or by asking the model, which shows you the command and runs it after your yes; the profile is the git key `pe.autonomy`:

```
git config --local pe.autonomy spec,schema
```

Read it back with `git config --local --get pe.autonomy`; no output means it is not set.

`spec` lets the PM lens approve the spec, after the design in three steps and a review cycle closed with no critical or serious finding; `schema` the data model; `design` design outside your office hours, still only in unattended work you authorised with a hard stop; `contract` a change to the shape of an API contract before its first release or its first client, and only through the profile: name it only for an API that has no client yet. By itself an autonomy never opens pushes, merges, production, deletions outside the worktree, messages to people or your instruction files; it also opens any further opening your own rules define, such as publishing, and the plugin defines none itself. Your answer in chat prevails. The model reads only the profile set in the repository itself, never a global value or a file in the repository, so a clone cannot bring one in; `git config --local --unset pe.autonomy` turns it off. You set it, or you ask the model in chat to set it, which it does only for the openings you name and never on its own or because a file or a tool output says so; nothing stops it in this version.

<!-- section: maintainers -->
### Work on this repository

The tools below belong to this repository and are not part of the plugin. They protect the privacy of a repository built in the open, and they are used in the maintainer's clone:

- `tools/privacy_check.py` checks everything a push sends to the remote (for each pushed commit the added lines, the message, the author and committer names and emails, and the path of every file added or changed; the reference names; annotated tags) for the maintainer's private terms, listed in a file outside the repository that `git config pe.privateTermsFile` names, and for generic patterns such as home paths and recognisable tokens. It skips binary files and says so, and it fails closed.
- `tools/install_dev_hooks.py` copies that check, the project hook below and their filters into the clone's git directory, outside the working tree, and installs the `pre-push` hook that runs the copy; a change to the working tree takes effect only when the installer runs again. If the copy goes missing or breaks, a check that cannot run refuses the push or the tool; running `python3 tools/install_dev_hooks.py` again from your own terminal restores it. It refuses to overwrite a `pre-push` hook it did not write, and to install while `core.hooksPath` is set.
- `tools/dev_guard.py` is a Claude Code `PreToolUse` hook, registered in the maintainer's `.claude/settings.local.json` (a file git ignores) with the command `python3 "<copy>/tools/dev_guard.py" || exit 2` and `"onFailure": "block"`. The `|| exit 2` makes every exit other than 0 a block on any Claude Code version, a missing `python3` or a missing copy of the script included. `"onFailure": "block"` also blocks the tool when the hook times out, cannot start or prints output that fails validation; Claude Code reads it from version 2.1.295, and on an earlier version a timed-out hook does not block and the call goes on through the normal permission flow. It blocks a push that skips git hooks, a command that sets `core.hooksPath` or touches the installed `pre-push` hook, and `disableAllHooks` written into a command or a Claude Code settings file; it blocks MCP tools that write straight to a remote and raw API calls that write to pull requests, and checks the text of pull and merge request commands (`gh`, `glab` and MCP tools). It reads that text only where it is written, and blocks what the shell fills in at run time, with the hint to write it to a file first. The exact rules are in the module docstrings of `tools/dev_guard.py` and `lib/pe_guard/filters.py`; what it does not stop is listed next, under "Not covered".

Not covered. The filters read text and defend against an agent's haste, not against a determined bypass. Open, some by design and some not yet closed:

- other `gh` and `glab` commands that write text: releases, issues, gists, labels, repository settings;
- MCP tools that create branches or other objects, write issues, or comment on and review pull requests;
- raw API writes outside pull requests (repository contents, references, GitLab files and commits, a GraphQL commit mutation), and any call by `curl` or another client;
- `core.hooksPath` edited with the file tools (`git config` and `git -c` are blocked);
- the guard's own registration: a write or a shell command that removes the `dev_guard` entry from `.claude/settings.local.json` is not blocked (only a write that adds `disableAllHooks` is), so an agent could switch the guard off that way; whether Claude Code's own prompt on sensitive files stops it is not verified;
- `--no-verify` from the maintainer's own terminal;
- the check edited in the working tree, then installed: nothing guards the installer yet;
- files that a `-diff` rule of `.gitattributes` makes git report as binary: skipped, and the skip is listed;
- a term glued to other letters, before or after it (`myterm`, `MYTERM`, `terms`): terms match as whole words in any letter case, and only a non-letter or a capital that starts a new word (`myTerm`) marks the edge, so such forms must be listed too;
- forms the hook cannot see in the command: a call hidden in a script, alias, function or variable, or built inside `sh -c`; a program other than `xargs` that runs `gh` and supplies its text (`find -exec`, `parallel`); a quoted or escaped option name or command word; a folder change by a program other than `cd`, `pushd` or `chdir`; brace expansion and globs; a body file written under another spelling of its name, or by a script that does not name it;
- the `gh` flags that fill a pull request from elsewhere: templates, attachments, an earlier failed run, an editor, the browser, and commit messages, which the pre-push checks;
- sessions where the project hook is not loaded: it runs in the main clone and in worktree sessions started from the Claude desktop app (they read the main checkout's settings), not in a terminal session inside a linked worktree, where the pre-push still runs.

The exact lists of the hidden forms and of the `gh` flags are in the module docstrings of `tools/dev_guard.py` and `lib/pe_guard/filters.py`.

Tests: `python3 -m pytest -q` from the repository root. Requirements: Python 3.9 or later, pytest 7 or later, git 2.32 or later. The end-to-end check of the import starts Claude Code, so the default run leaves it out (tests marked `e2e`); run it on request with `python3 -m pytest -m e2e tests/e2e -v`.

The workflow `.github/workflows/ci.yml` runs the same suite on every push and pull request, on Python 3.9 and on the latest Python, and fails on a red. A second job runs ruff 0.12.8 with the rules C901, PLR0912, PLR0915 and PLR1702, in preview mode and with nesting limited to 3, on the Python files the change touches against the default branch (on the default branch itself, on the last commit only), and fails on any finding. Two kinds of test do not run there: the end-to-end tests, which need Claude Code's credentials, and the check of the pinned superpowers names, which skips itself where superpowers is not installed. Ruff has no rule for functions over 40 lines: they are measured before the commit and in review.

<!-- section: explanation -->
## How it works

The first nine parts below each end with a line that says what guarantees the part. In this version four things are mechanical: the `SessionStart` hook, which copies the rules and checks your `CLAUDE.md`; Claude Code's own `@` import, which delivers the rules file as your instructions; the `skills` field of the agent, which makes Claude Code load `blunt-review` and `quality-scoring` into it; and the `disable-model-invocation` field of the skill `autonomous-execution`, which keeps the model from starting it. Everything else is a rule for the model.

<!-- section: explain-lanes -->
### Three lanes

The lane comes from the nature of the work, and `development-workflow` states it. A feature (new behaviour or a structural change) goes through phases and gates. Support and incidents, from the ticket to the fix, put primary evidence before hypotheses and your own recent changes before external causes, with a shorter diagnosis and proposal instead of the full phases, and with a go on the proposal and a go before production. Operations on live systems load `safe-operations` before any command or tool that changes an external system: the active target is verified and stated, the blast radius and the way back are said first, and every run on production asks for its own go. When the lane is not clear, the model asks.

**Guaranteed by:** a rule for the model only (the rules `lanes` and `production-go` in `rules.md`, and the skills `development-workflow` and `safe-operations`). Nothing checks which lane the model picks or that the go was asked.

<!-- section: explain-gates -->
### Phases and gates

A feature goes through seven phases: idea and requirements, spec, plan, tasks, implementation, validation and closure. A phase starts only when the gate before it is closed. There are four gates: two heavy, the spec and the final validation, and two light, the plan and the task list. A heavy gate is a short synthesis, the question "is it clear?" and your written approval; a bare "ok" to a spec nobody read is not approval. A light gate is a quick coherence check. Implementation has no gate but an escalation: an unforeseen case, a wrong assumption or an incoherence with the existing code stops the task and goes back to whoever decides.

Small work (fewer than three files, an obvious fix, a configuration value) condenses the first four phases into a brief analysis, and keeps both heavy gates. The one exception is `autonomous-execution`, which only you can start, by naming it: its internal validation (the full suite and the review by `blunt-reviewer`) replaces the final gate, and your invocation is the go to push the work's branch and open its merge request, never to merge. The gate of the spec has one too: an autonomy you open that covers it, as the section on role lenses below says.

A feature uses one chain of tools, never two. By default it is superpowers (`superpowers:brainstorming`, `superpowers:writing-plans`, `superpowers:subagent-driven-development`, with `superpowers:test-driven-development` for every task); spec-kit when you ask for it or the project adopted it (a `.specify/` folder or its configuration), and then `spec-driven-layout` says where its files live. The failing test comes first in both chains.

**Guaranteed by:** a mechanism for one thing: `disable-model-invocation` keeps the model from starting `autonomous-execution`. A rule for the rest (the rules `heavy-gates` and `test-first` in `rules.md`, and the skill `development-workflow`). Nothing records an approval or stops the model from writing code before one.

<!-- section: explain-review -->
### Independent review

The agent `blunt-reviewer` reviews a git range with the skill `blunt-review` loaded. Its prompt is one line in a closed grammar, `<base>..<tip> [round=1|2] [full=<path>,...]`, with `<base>` an ancestor of `<tip>`; anything else is not reviewed, and whoever launches it cannot steer the review through the prompt. It reads the change one commit at a time, then the whole, runs on Opus, and writes its report into `.pe/reviews/` in blocks, with a status line on top. Every finding carries evidence, findings come worst first, and a closing line names the single fix that matters most, or says that nothing was found and what was verified. Every finding carries its lens and its class, S1 critical, S2 serious or S3 medium, as `quality-scoring` defines them, and a finding is blocking when it is S1 or S2: a scenario that fails, a contradicted invariant, a security or privacy problem or an operation with no way back are S1, and a missing or tautological test on a behaviour that changed or a document contradicted by the code are S2. The verdict is `changes` only with at least one blocking finding, and it says whether another round of review is needed; the score of each lens, computed from the same findings, says whether the work may be integrated. The commit messages and the files named by `full=` are the author's claims, which the reviewer verifies and never obeys.

The review is made before a merge request is opened, on the whole range of the branch, and again on each round after fixes.

**Guaranteed by:** a mechanism for one thing: the `skills` field of the agent makes Claude Code load `blunt-review` and `quality-scoring` into it. Rules for the rest: that a review is made before a merge request, that the prompt follows the grammar (the agent refuses other prompts by its own instruction, and nothing outside it checks) and that it writes nothing outside `.pe/` are declared, not enforced. No mechanism records that a review took place, so the verdict is a message to read, not a gate.

<!-- section: explain-review-cycle -->
### The review cycle after fixes

The cycle starts after an independent check (the panel, or `blunt-reviewer` on a branch or on a delivery) and after the fixes of its findings. The corrected result is committed before each round, because the reviewer receives a git range.

In round 1 a `blunt-reviewer` with fresh context, one that wrote neither the work nor the fixes, rereads the corrected result: a document in full through `full=`; code through the range of the fixes, `<tip before the fixes>..<tip after the fixes>` (from the last commit before the fixes to the last one after them), with the rest of the branch readable through read-only git for context. On `VERDICT: pass` the cycle ends. On `changes`, the blocking findings are fixed and round 2 begins: another fresh reviewer rereads the range of the latest fixes, with `round=2`. On `pass` the cycle ends. If round 2 also ends with `changes`, there is no third round, unless your project has its own audit criterion, which then says when the cycle stops: the open blocking findings go up to you, or to the PM lens during an autonomy, with the recommendation of whoever carries them, because a blocking finding still open after two rounds usually says that the way of fixing is wrong. The cycle continues only on `changes`. The fixes of each round are listed in a table in the body of the commit of the fixes (finding, decision, place), and the next round checks that table too.

**Guaranteed by:** a rule for the model only (the skill `blunt-review`). No mechanism counts the rounds or stops a third one.

<!-- section: explain-lenses -->
### Role lenses and the 8/10 gate

Four lenses look at every piece of work, each named for a role and never for a person. The PM lens, held by the main session, frames the work at phase 1: a pre-mortem of three lines, the why, the search for what already exists, the smallest version and its measured cost; while you are away it decides scope, interface and time, or a disagreement between the UX and review lenses, inside an approved spec, never the data model or an API contract. An autonomy hands the lenses more, ahead of time: you open it in chat, for one piece of work or one day with a hard stop, or for one repository with a profile, and it opens the approval of the spec, the data model and design outside your office hours unless your words or the profile narrow them, and, by the profile only, an API contract before its first release or its first client; the how-to guide on autonomy shows how to set the profile. The UX lens proposes from the need of the person who uses the product, on every change to an interface or to the responses of an API, and the review lens attacks the proposal on evidence and cost, in one round before the spec; the user lens tries the change as a persona would and reports where the persona gets stuck. The lenses re-check each other's claims, and an agreement nobody verified counts as a finding. `development-workflow` holds the lenses and the rules for decisions while you are away; `interface-quality` holds the measured bar of an interface and the UX and user lenses.

At phase 6 every lens the work touches gets a score from 1 to 10, which `quality-scoring` computes from the findings of an independent review: a critical or serious finding takes the lens below 8 by itself. Below 8 the final validation stops and asks you to choose between the fix, with its cost, and a deferral you can track. The rubric is still being calibrated: its log, `calibration.md` in the plugin's data folder, says `CALIBRATING` until five applications in a row, on at least two projects, show no signal, and `STABLE` after that. The lenses and the gate were added on 29 October 2026 and are provisional until they are re-evaluated; a later version carries the changes.

**Guaranteed by:** a rule for the model only (the rules `lenses`, `quality-gate` and `user-away` in `rules.md`, and the skills `development-workflow`, `interface-quality` and `quality-scoring`). Nothing computes a score or stops a merge request in this version, and the lenses are subagents that the main session is asked to start.

<!-- section: explain-rules-import -->
### Rules through an import

`rules.md` is the file of working rules. Its first line is the marker `PE-RULES v1`, and it has three blocks: rules for every agent, rules for the main session, rules for subagents. It states that your own instructions prevail on conflict, and that a conflict with its five precedence rules (evidence, no bug left behind, test-first, blunt review, burden of proof on adding) goes to you and is never resolved silently.

The plugin root does not survive a plugin update and the plugin's data folder does, so at every session start `SessionStart` copies `rules.md` from the root to the data folder when the copy is missing or different. Your `CLAUDE.md` imports the copy with one `@` line; that is how the rules reach the session as your own instructions, which superpowers ranks above its skills. The second line you add is the safety line, for the day the plugin is gone.

In your `CLAUDE.md` exactly two lines change, and you add them yourself: the hook only reads the file and prints what is missing. The rules reach the main session and the subagents that load your `CLAUDE.md`; they do not reach `Explore`, `Plan` and agents defined with `omitClaudeMd: true`. A rules update applies from the next session. An end-to-end test, run on request, gives evidence about Claude Code's import; it is not a mechanism of the plugin and does not run in your session (the install guide says what it covers).

**Guaranteed by:** a mechanism for the delivery: the hook copies and checks, and Claude Code's `@` import brings the file in. A rule for the compliance: the model is asked to follow the rules, and nothing checks that it does.

<!-- section: explain-continuity -->
### Continuity

Work is saved ahead, in three forms, all described by `continuity-note`. The progress note is the state on a few lines (done, in progress, next, open decisions), updated at every milestone and read again after a compaction; it lives where your own configuration keeps the state of the work (a resume card, a diary), or in the project's own note when the project declares one, and only otherwise in `.pe/progress.md` at the root of the repository, with a `.pe/.gitignore` that contains `*`. The deliverable file of a task given to a subagent is written in blocks and carries a status line on top, `STATUS: IN PROGRESS - done: ...; next: ...`, which the last block replaces with `STATUS: COMPLETE`. The full continuity note is written when a session ends with work in progress or when work passes to another agent, so that a fresh context resumes without replaying the conversation.

**Guaranteed by:** a rule for the model only (the rules `save-ahead` and `status-line` in `rules.md`). Nothing counts the saves, so a compaction loses at most the work done since the last save, and how small that is depends on the model's discipline.

<!-- section: explain-office-hours -->
### Office hours

If you set office hours, outside them the model keeps your work local: it commits, and it does not push to a remote that is not personal, open a merge request, start a pipeline, edit a tracker or send a message. Weekends and the holidays you list open later, at the hour you choose. Unattended work outside the hours runs only when you authorise that piece of work with a hard stop, and commits made outside the window are re-created inside it with their real dates, never with faked ones. Without the setting the rule is off; the how-to guide on office hours shows the keys.

**Guaranteed by:** a rule for the model only (the rule `office-hours` in `rules.md` and the skill `safe-operations`). Nothing blocks a push at night in this version; a guard that does is planned for a later version.

<!-- section: explain-communication -->
### How the plugin talks to you

The model explains briefly and at a high level at four moments: at the start and at the end of a work block, at every architecture choice (the choice, the main alternative discarded and why) and before a heavy gate. Each explanation ends with "is it clear?" in your language, and what you say is unclear is explained again with different words and an example. The answer is awaited only at the two heavy gates and at architecture choices, and never while you are away or during an autonomy; there is no quiz and no verification question, ever. The tone is frank: no agreeing to please, no flattery, weak reasoning challenged with evidence, risks and opportunity costs named, and a guess about your intent labelled as a guess. The skill `teach` carries the explanations and the method for teaching code; the rules file carries the tone.

**Guaranteed by:** a rule for the model only (the rules `explain`, `no-quiz` and `candour` in `rules.md`, and the skill `teach`). "Is it clear?" does not prove that you understood, and the tone rules reduce the model's tendency to agree, they do not remove it.

<!-- section: language-neutral -->
### Any language, framework and database

The plugin holds for every language, framework and database, and its rules name none. The good practices of the stack you work in come first from your project's conventions and your own configuration, then from the official documentation of the version in use, which the model reads with Context7 when it is installed; an interface that depends on the version is verified before it is used. They are not written in the plugin for three reasons: the model already knows the common ones, such texts age with every version, and they would cost tokens in every session.

To add the knowledge of a stack, write your own skills; separate optional plugins for single stacks may follow. So far the plugin has been tried only on this repository, which is Python: the runs on other languages are still to come, and their list will be added here after them.

<!-- section: limits -->
## Known limits

The limits that describe Claude Code's own behaviour (which agents load `CLAUDE.md`, Cowork, compaction) come from its documentation as read while the plugin was designed. The plugin's tests do not exercise them, apart from the import itself.

- The role lenses, the autonomy (including the rule that the model sets its profile only when you ask), the 8/10 gate, the budget, the rule on delivered API contracts, the taste thresholds and the office hours are rules for the model in this version, not mechanisms; the CI enforces the complexity thresholds on this repository only.
- The 8/10 gate is still calibrating, and the lenses are provisional until they are re-evaluated.
- The daily budget applies only where the host shows the model the account's usage; elsewhere the rule does not apply.
- There is no mechanical check on merge requests: the review before one is a rule for the model, and the verdict of `blunt-reviewer` is a message to read, not a gate.
- The rules do not reach `Explore`, `Plan` and agents with `omitClaudeMd: true`, because they travel in your `CLAUDE.md`.
- Cowork skips imports that point outside its working folder, so the rules do not arrive there.
- An update of the rules file applies from the session after the one that copied it.
- Whether a subagent that Claude Code has compacted keeps the imported rules is not verified.
- With the plugin uninstalled or disabled, `SessionStart` does not run, and only the safety line in your `CLAUDE.md` warns you.
- "Is it clear?" does not prove understanding, and the tone rules reduce the model's tendency to agree without removing it.
- Continuity loses at most the work done after the last save, and depends on the model's discipline because nothing counts the saves.
- The grammar of the `blunt-reviewer` prompt and the fact that it writes no file outside `.pe/` are declared in the agent, not enforced.
- Claude Code (checked with 2.1.303) asks approval for `git show` and `git diff` with the options the reviewer must use, unless the two permission rules of the install guide are allowed: without them it asks at each read, and in a run without a person (`claude -p`) the reviewer reads nothing. In such a run the reviewer may also be refused writes under `.pe/`, and then it puts its whole report in its last message, with `REPORT: inline`.
- Superpowers installs by itself only when the official marketplace is already registered in your Claude Code; otherwise this plugin stays disabled until you add it (see the install guide).
- The version is pinned in the manifest, so an update reaches you only when the version string changes and you ask for it, unless you turn auto-update on.
- If you already have a plugin named superpowers from another marketplace, Claude Code's documentation says that both appear as enabled and that the hooks of one of them are left out; this has not been tried here.
- The plugin was tried on macOS only; the CI runs the repository's tests on Linux.

<!-- section: reference -->
## Reference

There are no commands in this version, only one script, `skills/safe-operations/recreate_night_commits.py`, which `safe-operations` tells the model to run.

### Skills

Claude Code loads a skill when the task matches its description, unless the table says otherwise.

| Skill | What it does | When it loads |
|---|---|---|
| `engineering-principles` | Understand before implementing, reuse before building, design and placement principles with the bar of the architecture, delivered API contracts and the client's scenarios, scalability and cost, test discipline with isolated sessions, no bug left behind, secure coding, secrets hygiene, writing rules. | Before understanding a requirement, proposing an approach, or writing or changing code, tests or documentation; not for plainly trivial work. |
| `evidence-based-investigation` | Verify before asserting, state the confidence level, rule out hypotheses one by one, scope a defect in four steps, separate verified from inferred. | Investigations, diagnoses and technical answers where a wrong conclusion has a cost; not for design or review. |
| `blunt-review` | How a review is written and when a finding blocks; lenses for design, tests, documentation, infrastructure and diagnosis; the independent review and the review cycle after fixes. | Every review, self-review included. Preloaded in `blunt-reviewer`. |
| `quality-scoring` | A score from 1 to 10 for each lens the work touches, computed from findings classed S1, S2 or S3; who scores which lens; the score sheet; the calibration log in the plugin's data folder. | Every review that feeds the 8/10 gate of phase 6, before work is integrated or released. Preloaded in `blunt-reviewer`. |
| `adversarial-review-panel` | Four lenses that argue against each other, a cross-examination, and one decision. | Decisions where being wrong is expensive: architecture, specs, risky refactors, security, technology choices, data models; not for ordinary reviews. |
| `development-workflow` | The three lanes, seven phases and four gates, one chain per feature, the design in three steps, models by role, the role lenses and decisions while you are away, the daily budget, instruction layers, closure. | Any work on code, a release, a merge or a closure. |
| `spec-driven-layout` | Where spec-kit keeps its files and how much to write for the weight of the work. | When you ask for spec-kit or the project adopted it. |
| `autonomous-execution` | Runs an approved spec unattended up to the opening of its merge request, recording the decisions it takes alone. | Only when you invoke it by name; the model never loads it on its own. |
| `teach` | Brief explanations followed by "is it clear?", the six-layer method for teaching code, the state on one screen on resume. | When you ask how code works or to be taught, when a session resumes, before a heavy gate. |
| `continuity-note` | The continuity note, the progress note and the status line of deliverable files. | When work passes to another agent or session, and at every milestone in its short form. |
| `safe-operations` | Verify the target, dry run, say the blast radius and the way back, a separate go for production, never poll, verify at every level. | Before a command or tool that changes an external system, and, with office hours set, before a push, a merge request, a pipeline, a tracker edit or a message. |
| `interface-quality` | The ten principles of a simple interface, the measures before a change (every state, both themes, 375, 768 and 1280 px, WCAG AA measured), the UX study before code, the UX lens and the user lens. | Every change to a user interface, and to the responses, messages and documentation of an API. |
| `documentation-quality` | The four kinds of documentation and the two questions that tell them apart, the entry page, documents that describe only what exists and say their limits, the manual of an administration interface. | Writing, splitting, reorganising or reviewing documentation; not for docstrings, comments or messages to people. |
| `configure` | Shows the current values of the `pe.*` keys, asks one question at a time about the ones you choose, checks the format of each answer and runs each `git config` command only after your yes, the autonomy profile included. | When you ask how to configure or set up the plugin, its office hours, weekends, holidays, personal remotes or autonomy; not for the settings of another tool. |

### Agent

`blunt-reviewer`: model Opus; tools Read, Grep, Glob, Bash and Write; preloads `pragmatic-engineering:blunt-review` and `pragmatic-engineering:quality-scoring`. It accepts one line, `<base>..<tip> [round=1|2] [full=<path>,...]`, writes `.pe/reviews/<base7>..<tip7>-round<k>.md` and ends with `VERDICT: pass | changes`, `FINDINGS: <n> (<b> blocking; <lens> S1=<a> S2=<c> S3=<d>; ...)`, `COVERAGE: full | partial`, `REPORT: <path> | inline | none` and `THE THING: <...>`. The main session launches it before a merge request, for a delivered range, and for each round of the review cycle.

### Hook

`SessionStart`, registered in `hooks/hooks.json` as `python3 "${CLAUDE_PLUGIN_ROOT}/hooks/session_start.py"`, with a timeout of 10 seconds. At every session start it copies `rules.md` to the plugin's data folder when the copy is missing or different, checks that `~/.claude/CLAUDE.md` carries the import of the copy and the safety line, and prints the lines that are missing, to you and to the model with the same text. It never blocks and never fails a session start: a problem becomes a notice. It stays silent when the rules are in place and nothing changed.

### Files

`rules.md` is the working rules file, starting with the marker `PE-RULES v1`. The `.pe/` folder, at the root of a project, holds `reviews/` (the reports of `blunt-reviewer`) and `progress.md` (the progress note), and it never enters git because of its own `.gitignore` with `*`. In the plugin's data folder, next to the copy of `rules.md`, `quality-scoring` keeps `calibration.md`, its calibration log. `skills/safe-operations/recreate_night_commits.py` re-creates, inside the office hours, the commits made outside them and never pushed, and leaves a `night-backup-<YYYYMMDD-HHMMSS>` tag in the repository.

<!-- section: license -->
## License

MIT, see [LICENSE](LICENSE). The works this plugin builds on are credited in [NOTICE](NOTICE).
