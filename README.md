# pragmatic-engineering

[Italiano](README.it.md)

pragmatic-engineering is an engineering method for Claude Code, put in order. It brings working rules to every agent of a session through one import line in your `CLAUDE.md`, and it adds skills that cover the phases and the three lanes of the work, plus one agent, `blunt-reviewer`, that reviews a git range independently and bluntly. Version 0.1.0 is the core of the method: the rules, the skills, the reviewer and a `SessionStart` hook that keeps the rules in place. This version has no mechanical check on merge requests: the review before a merge request is a rule for the model, not a gate.

This page follows the four kinds of documentation of Diataxis (<https://diataxis.fr>), one section for each: a tutorial, how-to guides, an explanation and a reference, with the known limits between the last two. For every part of the method the explanation says what guarantees it: a mechanism, meaning code that runs whatever the model does, or only a rule for the model, meaning text the model is asked to follow and nothing checks.

This page is written for one person who installs the plugin on their own machine. The plugin keeps its state there, in its data folder, in your git configuration and in the `.pe/` folders that git ignores, so by itself it shares nothing between the people of a team; the skills do not say yet who gives the written approval of a gate when a team works together.

**Contents**

- [Tutorial: a first guided session](#tutorial-a-first-guided-session)
- [How-to guides](#how-to-guides)
  - [Install](#install)
  - [Configure the plugin](#configure-the-plugin)
  - [Uninstall and go back](#uninstall-and-go-back)
  - [Set your office hours](#set-your-office-hours)
  - [Let the work go on without you](#let-the-work-go-on-without-you)
  - [Work on this repository](#work-on-this-repository)
- [How it works](#how-it-works)
  - [Three lanes](#three-lanes)
  - [Phases and gates](#phases-and-gates)
  - [Independent review](#independent-review)
  - [The review cycle after fixes](#the-review-cycle-after-fixes)
  - [Role lenses and the 8/10 gate](#role-lenses-and-the-810-gate)
    - [The four lenses](#the-four-lenses)
    - [How the lenses work together](#how-the-lenses-work-together)
    - [How a score is given](#how-a-score-is-given)
    - [The gate](#the-gate)
  - [The life cycle of a piece of work, in three modes](#the-life-cycle-of-a-piece-of-work-in-three-modes)
    - [Normal mode](#normal-mode)
    - [Day autonomy](#day-autonomy)
    - [Night autonomy](#night-autonomy)
    - [The three modes side by side](#the-three-modes-side-by-side)
  - [Rules through an import](#rules-through-an-import)
  - [Working habits](#working-habits)
  - [Continuity](#continuity)
  - [Office hours](#office-hours)
  - [How the plugin talks to you](#how-the-plugin-talks-to-you)
  - [Any language, framework and database](#any-language-framework-and-database)
- [Known limits](#known-limits)
- [Reference](#reference)
  - [Skills](#skills)
  - [Agent](#agent)
  - [Hook](#hook)
  - [Files](#files)
- [License](#license)

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

6. Ask for a small change with a test, for example a function with one behaviour. You should see, in this order: the model names the lane (a feature) and says in a few sentences what it is about to do, ending with "is it clear?" in your language; it writes a short frame of the work, which is the PM lens at work: a pre-mortem of three lines, the why, the reuse statement and the smallest version; it stops for your written approval of a short spec before the code, because the two heavy gates stay even for small work; it writes the failing test first and runs it; it writes the code; it reviews its own diff following `blunt-review` and closes with a statement that the tests pass or a list of what does not; it stops again for your approval of the result; it never pushes without your go.

7. Commit the work on a branch and say: "Review this branch before I open the merge request." (you can also say it in your own language). You should see the model launch `blunt-reviewer` with one line, `<merge-base>..HEAD`, where `<merge-base>` is the commit `git merge-base` prints. The reviewer writes its report in `.pe/reviews/`, in a file named `<base7>..<tip7>-round1.md` whose first line is a status line, and its final message ends with five lines: `VERDICT:`, `FINDINGS:`, `COVERAGE:`, `REPORT:` and `THE THING:`, where `FINDINGS:` counts the findings by lens and by class, for example `code S1=0 S2=0 S3=1`. With `VERDICT: changes`, the blocking findings are fixed, committed, and a second review runs on the fixes; the explanation of the review cycle below says how it goes.

<!-- section: how-to -->
## How-to guides

<!-- section: install -->
### Install

Requirements: Claude Code, `python3` 3.9 or later on your path (the hook is a Python script), and git (the reviewer reads git ranges). The reviewer and the UX lens run on Opus and the user lens on Sonnet, so the account you use must be able to run both.

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

Ten of the parts below each end with a line that says what guarantees the part; two have none: the life cycle in three modes, because it only follows the others, and the note on languages and frameworks, which only says where good practices come from. In this version four things are mechanical: the `SessionStart` hook, which copies the rules and checks your `CLAUDE.md`; Claude Code's own `@` import, which delivers the rules file as your instructions; the `skills` field of the agent, which makes Claude Code load `blunt-review` and `quality-scoring` into it; and the `disable-model-invocation` field of the skill `autonomous-execution`, which keeps the model from starting it. Everything else is a rule for the model.

<!-- section: explain-lanes -->
### Three lanes

The lane comes from the nature of the work, and `development-workflow` states it. A feature (new behaviour or a structural change) goes through phases and gates. Support and incidents, from the ticket to the fix, put primary evidence before hypotheses and your own recent changes before external causes, with a shorter diagnosis and proposal instead of the full phases, and with a go on the proposal and a go before production. Operations on live systems load `safe-operations` before any command or tool that changes an external system: the active target is verified and stated, the blast radius and the way back are said first, and every run on production asks for its own go. A dry run is read before the real command where one exists, a long operation such as a rollout or a pipeline is never watched in a loop, and afterwards each level is verified in turn (the process ran, the service answers, the answer carries the right data, the person sees what was meant), with the levels not checked reported as unchecked. An action with visible effects on third parties, such as customers, is decided by whoever owns it: the model reports who is affected and what each option costs, and does not send, refund or notify on its own initiative. When the lane is not clear, the model asks.

**Guaranteed by:** a rule for the model only (the rules `lanes` and `production-go` in `rules.md`, and the skills `development-workflow` and `safe-operations`). Nothing checks which lane the model picks or that the go was asked.

<!-- section: explain-gates -->
### Phases and gates

A feature goes through seven phases: idea and requirements, spec, plan, tasks, implementation, validation and closure. A phase starts only when the gate before it is closed. There are four gates: two heavy, the spec and the final validation, and two light, the plan and the task list. A heavy gate is a short synthesis, the question "is it clear?" and your written approval; a bare "ok" to a spec nobody read is not approval. A light gate is a quick coherence check. Implementation has no gate but an escalation: an unforeseen case, a wrong assumption or an incoherence with the existing code stops the task and goes back to whoever decides.

Before any design document is written (a spec, an architecture proposal, a data model or an interface contract), the design takes three steps, none skipped: a complete proposal, a first self-review that hunts for what is wrong with it, and a second self-review of the fixes of the first, after which the consolidated design is written. A self-review that removes nothing from the first proposal did not happen. A decision that is costly to reverse also goes through `adversarial-review-panel`, described under independent review. Before going deep, the model builds a tracer bullet, a thin slice that runs end to end through every layer and then stays and grows, unlike a spike, a throwaway prototype that answers one question. The tasks of the plan are atomic, each with a checkbox, run one at a time and in order, each with its failing test first. Models follow the role: Opus for judgment, design and review, Sonnet for a fully specified task, never Haiku, with high effort for transactions, security, permissions and migrations, while the session itself keeps the model you chose. Orders to a subagent are few and complete, naming the files, the isolated resources and the shape of the report; a subagent that reports it is blocked gets more context, a more capable model or a smaller task, never the same retry; and a new instruction from you in the middle of an execution suspends the plan until it is reconciled with the instruction.

Small work (fewer than three files, an obvious fix, a configuration value) condenses the first four phases into a brief analysis, and keeps both heavy gates. The final gate has one exception, `autonomous-execution`, which only you can start, by naming it: its internal validation (the full suite and the review by `blunt-reviewer`) replaces the final gate, and your invocation is the go to push the work's branch and open its merge request, never to merge. The gate of the spec has one too: an autonomy you open that covers it, as the section on role lenses below says. Outside that exception, publishing, meaning a push, a merge request or a merge, follows your own rules and needs your explicit go, and no protection is bypassed.

`autonomous-execution` runs an approved spec task by task, each with its failing test first and a review of its diff. It starts only with an approved spec whose approval it can quote, atomic tasks, a branch that is not protected and a full suite run before the first task. Where a decision would need you, it decides, records the decision in its report and in the description of the merge request, in a section called "Decisions taken alone", and goes on; it has three stops: the only solution would contradict the spec, the evidence of the spec's approval is missing, or three attempts at the same material obstacle have failed. It closes with the full suite, a review of the whole branch by `blunt-reviewer` and a trial merge against the target, and gives the verdict MERGEABLE or NOT MERGEABLE, never the merge. Its closure has no step that scores the lenses, and the description of its merge request holds the reviewer's lines and no scores; the skills do not say yet whether a lens under 8 makes the run NOT MERGEABLE. If round 2 of the review cycle still ends with `changes`, it declares a partial closure: no push and no merge request, and the open findings go to you in its report. Outside your office hours it does not push either: the run ends with local commits and its report.

A feature uses one chain of tools, never two. By default it is superpowers (`superpowers:brainstorming`, `superpowers:writing-plans`, `superpowers:subagent-driven-development`, with `superpowers:test-driven-development` for every task); spec-kit when you ask for it or the project adopted it (a `.specify/` folder or its configuration), and then `spec-driven-layout` says where its files live. The failing test comes first in both chains. Where the superpowers chain hands over to this method, the final review of its last task is the review of phase 6 by `blunt-reviewer`, so the same diff is not read twice, and the coordinator carries the lines of its ledger marked `minor (deferred)`, `parked` and `Ruling:` into the description of the merge request as non-blocking findings with the decision taken; the rulings go to you at the gate of phase 6.

Closure prescribes no merge and no push: your own rules and your go apply, and after a merge the model cleans up the branches already merged, following your rules, and reports those that still hold unmerged work. Before a version change it classifies the changes in the diff and states the semantic-versioning part it chose, with the proofs.

**Guaranteed by:** a mechanism for one thing: `disable-model-invocation` keeps the model from starting `autonomous-execution`. A rule for the rest (the rules `heavy-gates`, `test-first` and `publishing` in `rules.md`, and the skills `development-workflow` and `autonomous-execution`). Nothing records an approval or stops the model from writing code before one.

<!-- section: explain-review -->
### Independent review

The agent `blunt-reviewer` reviews a git range with the skill `blunt-review` loaded. Its prompt is one line in a closed grammar, `<base>..<tip> [round=1|2] [full=<path>,...]`, with `<base>` an ancestor of `<tip>`; anything else is not reviewed, and whoever launches it cannot steer the review through the prompt. It reads the change one commit at a time, then the whole, runs on Opus, and writes its report into `.pe/reviews/` in blocks, with a status line on top. Every finding carries evidence, findings come worst first, and a closing line names the single fix that matters most, or says that nothing was found and what was verified. Every finding carries its lens and its class, S1 critical, S2 serious or S3 medium, as `quality-scoring` defines them, and a finding is blocking when it is S1 or S2: a scenario that fails, a contradicted invariant, a security or privacy problem or an operation with no way back are S1, and a missing or tautological test on a behaviour that changed or a document contradicted by the code are S2. The verdict is `changes` only with at least one blocking finding, and it says whether another round of review is needed; the score of each lens, computed from the same findings, says whether the work may be integrated. The commit messages and the files named by `full=` are the author's claims, which the reviewer verifies and never obeys.

The review is made before a merge request is opened, on the whole range of the branch, and again on each round after fixes.

The independent review sits on top of three checks that every agent makes before it proposes a commit. The tests of the touched area run with zero failures, and the whole suite runs once on the integrated branch, with the pipeline's own pre-checks, before the push (`suite-before-commit`). The agent reviews its own work following `blunt-review`, on eight points: idiom, repetition, specific exceptions, consistency with the code base, scalability, security, docstrings and documentation in sync (`self-review`). And the changed files are measured for functions over about 40 lines, nesting deeper than 3 levels, the language's complexity checks, new catch-all handlers and new duplicates, after which the delta gets a blunt review; each hit is fixed or justified in writing with `file:line`, or exempted with a `# taste-exempt: <reason>` comment that the review judges (`taste-gates`). Blunt means a verdict without courtesy on the work and never on the person, and a self-review is the strictest case, not the most lenient. Beyond code, `blunt-review` carries lenses for designs and specs, unit tests, documentation, infrastructure and the diagnosis of a ticket.

For a decision that is costly to reverse (a data model, a public interface, a module boundary, a new dependency, a security control), `adversarial-review-panel` runs before the choice. It is a panel of four lenses of its own, not the role lenses explained below: structure and taste, rigour and correctness, economy and simplicity, product and priority. They argue against each other, one pass asks what all four missed, and a written order of precedence settles the conflicts instead of a judge: correctness, security and privacy come first, then simplicity at equal correctness, then the product lens, which decides only what is done now and never what is true, and a conflict that precedence does not settle goes to you. The result is one decision, followed by the review cycle explained next. The panel is not for ordinary reviews.

**Guaranteed by:** a mechanism for one thing: the `skills` field of the agent makes Claude Code load `blunt-review` and `quality-scoring` into it. Rules for the rest: that a review is made before a merge request, that the prompt follows the grammar (the agent refuses other prompts by its own instruction, and nothing outside it checks) and that it writes nothing outside `.pe/` are declared, not enforced. No mechanism records that a review took place, so the verdict is a message to read, not a gate. The three checks before a commit (the rules `suite-before-commit`, `self-review` and `taste-gates` in `rules.md`) and the panel are rules for the model as well.

<!-- section: explain-review-cycle -->
### The review cycle after fixes

The cycle starts after an independent check (the panel, or `blunt-reviewer` on a branch or on a delivery) and after the fixes of its findings. The corrected result is committed before each round, because the reviewer receives a git range.

In round 1 a `blunt-reviewer` with fresh context, one that wrote neither the work nor the fixes, rereads the corrected result: a document in full through `full=`; code through the range of the fixes, `<tip before the fixes>..<tip after the fixes>` (from the last commit before the fixes to the last one after them), with the rest of the branch readable through read-only git for context. On `VERDICT: pass` the cycle ends. On `changes`, the blocking findings are fixed and round 2 begins: another fresh reviewer rereads the range of the latest fixes, with `round=2`. On `pass` the cycle ends. If round 2 also ends with `changes`, there is no third round, unless your project has its own audit criterion, a stop rule written in its own instructions or configuration and never inferred from another document, which then says when the cycle stops: the open blocking findings go up to you, or to the PM lens during an autonomy, with the recommendation of whoever carries them, because a blocking finding still open after two rounds usually says that the way of fixing is wrong. The cycle continues only on `changes`. The fixes of each round are listed in a table in the body of the commit of the fixes (finding, decision, place), and the next round checks that table too.

**Guaranteed by:** a rule for the model only (the skill `blunt-review`). No mechanism counts the rounds or stops a third one.

<!-- section: explain-lenses -->
### Role lenses and the 8/10 gate

Four lenses look at every piece of work. Each is named for a role and never for a person, because each one borrows a way of working and nobody's voice. The first three, the PM, UX and review lenses, frame, propose and attack. The fourth, the user lens, only tries the work as a person would. The lenses and the gate were added on 29 October 2026 and are provisional until they are re-evaluated; a later version carries the changes. The four subsections below say who the lenses are, how they work together, how a score is given and what the gate does.

<!-- section: lenses-roles -->
#### The four lenses

The PM lens (PM stands for project manager) asks why the work is done and how small it can be. The main session holds it, on the model you chose for the session. At phase 1 of every feature, condensed or not, it writes a frame: a pre-mortem of three lines (the work is imagined already failed, and each way it can fail is written with what prevents it), the why (what for, for whom, what happens if it is not done, how you will know it is done), the reuse statement (where the model searched, for what, and what it found), the smallest version and its measured cost. After that it mediates when the other lenses ask for more than the frame holds, keeps the daily budget and holds the 8/10 gate. Constraints of your company come only from you, and every cut of scope is a proposal to you.

The UX lens (UX stands for user experience) proposes from the need of the person who uses the product. It runs as a subagent on Opus, briefed with `interface-quality`, on every change to an interface and on the responses, messages and documentation of an API, where the person is the developer of the client. It delivers a proposal, and it holds the change to the bar of that skill: ten principles of a simple interface, the first of which is one page, one job, one primary action, with "one more element on this page?" answered no by default (the others ask for pages grouped by the topics the person recognises, one name for each thing, defaults instead of choices, no repeated information, the components of the project's template first, a next step in every page state, a count of elements to remove, menus ordered by importance and structure before navigation); and measures taken in both themes, light and dark, at widths of 375, 768 and 1280 px, with contrast checked against WCAG AA in every state and never by eye, touch targets of at least 44 px, and keyboard and screen reader checked. For a new or changed page the proposal is a UX study that the project's designer, or you where there is none, approves before the code is written.

The review lens attacks the proposal on evidence, cost, the simpler alternative and the impact on code and architecture, and later judges the finished work. It is the skill `blunt-review`, and on a git range it is the agent `blunt-reviewer`, which runs on Opus. It delivers findings, each with its evidence, its lens and its class, and the scores of the lenses it covers.

The user lens tries the change as the person who will use it, and it never decides. It runs as a subagent on Sonnet, never on Haiku, takes at most three personas from the project's file of personas, chosen for the need (the skills do not say where that file lives, what it holds or what happens when the project has none), and works on one real task at a time from the screenshots, never from the code; until the project has a script that makes them, its findings carry the label "from templates, not seen on screen". At every step it answers four questions as the persona: do I know what to do here, do I see the control that does it, does its label tell me in my words that it is the right one, and after acting do I understand that it worked or what to do now? A no, or a hesitation, is a finding. On an API the persona is the developer of the client, who has only the documentation. It delivers findings only, with no vote and no score. When your configuration names its own agents for these lenses, those agents run them. The detail is in `development-workflow` for the PM lens, in `interface-quality` for the UX and user lenses and in `blunt-review` for the review lens.

<!-- section: lenses-together -->
#### How the lenses work together

On a change to an interface or to the responses of an API, other than a trivial text fix, the lenses take one round before the spec, in this order: the PM lens has already framed the work, the UX lens proposes, the review lens attacks, the UX lens answers or changes the proposal, and then comes the decision. A round on a question that is not trivial and that changes nothing of the first proposal is flagged as possible theatre. No lens agrees by default: each re-checks the other's claims against the screenshots, the measurements and the code before accepting them, and an agreement written without an independent check counts as a finding, because a claim of another lens is never evidence until someone has seen what was checked. The user lens takes no part in the decision: it adds findings and never votes or scores.

In the decision the UX lens prevails on what serves the person who uses the product, and the review lens on correctness, evidence and the quality of the code; on scope, time and cost the PM lens mediates and proposes, and you decide. Some things are never traded: evidence, known defects, test first, tests, guards, validation, error handling, bug fixes and the bars of taste and architecture. When time or tokens run short, scope is cut and quality is not, and there the review lens prevails without needing to convince anyone. A disagreement that survives the round before the spec goes to you, or to the PM lens under an autonomy that opens `spec`, and to the project's designer where there is one, with both positions written down; the skills do not define yet when a disagreement survives. One that comes up later, inside an approved spec, goes to the PM lens whenever you are away, with no autonomy needed, as the next paragraph says.

While you are away, which means that you said so or, with office hours set, that a blocking question got no answer for 30 minutes inside the window, and only in work you started, the decisions are split. The review lens decides a technical case. The PM lens decides scope, interface, time, or a disagreement between the UX and review lenses inside an approved spec, in one sentence with the reason, after hearing both and weighing five costs: tokens, time, quality, working behaviour, and the satisfaction of customer and end user. Without an autonomy the data model and an API contract are not decided in your absence: a provisional proposal is written on a local branch, the tasks that depend on it are parked and the others go on; outside your office hours only technical decisions are taken. Production, shared systems, deletions outside the worktree, merges into protected branches, irreversible actions and changed requirements always wait for you. An autonomy, set as the how-to guide on autonomy explains, hands the lenses more of this ahead of time: the approval of the spec, the data model, design outside your office hours and, by the profile only, an API contract that has no client yet.

Every decision taken this way is provisional, is reported to you first and goes in the decision log, one entry for each: who decided, the positions, the costs and the state (confirmed, overturned or pending). The log is the one your configuration or the project names, and otherwise the progress note. Defects are marked by origin, found by a lens or found later by people, and a decision taken again is marked as such, because the calibration of the scores counts missed defects from there. The detail is in `development-workflow` for the decisions while you are away and in `interface-quality` for the round of the UX and review lenses.

<!-- section: lenses-score -->
#### How a score is given

A score is computed from classified findings and is never chosen, so that two reviewers who start from the same evidence reach the same score within half a point. Eight things can get a score (`quality-scoring` calls each of them a lens too, besides the four role lenses), each with a short id: new code (`code`), old code that the work touches (`legacy`), architecture (`architecture`), APIs (`api`) and documentation (`docs`), which the review lens scores; and interface clarity (`clarity`), interface aspect (`aspect`) and accessibility, measured (`accessibility`), which the UX lens scores on the real pages, with screenshots in both themes at 375, 768 and 1280 px, measured contrast and touch targets, and the result of axe, an accessibility checker. Only the lenses the work touches get a score, and old code is scored only on what the work touches. Before reviewing, whoever scores writes this perimeter: the lenses in scope, with their files or git range, pages and widths, and routes. The PM lens does not score, it collects the scores, and the user lens adds findings and never scores.

Every finding carries `file:line`, a measured number or the name of a screenshot, and the action to take. One finding is one root cause: the same pattern in twelve places is one finding with its places listed, so splitting or merging findings cannot move the score. The breach of a mechanical threshold, such as a function over 40 lines, is a finding too. Each finding gets one of three classes, and in doubt the more severe one holds until the second reviewer lowers it with evidence. S1, critical, means wrong or unsafe for a user, a piece of data or a service: for example a scenario that fails, or a write without a permission check. S2, serious, means that it holds today and breaks with normal use or with growth: for example a missing or tautological test (a test that cannot fail) on a behaviour that changed, or a document contradicted by the code, such as an instruction that no longer works, which `quality-scoring` classes S2 and not S1. S3, medium, means debt with no wrong behaviour: for example a function over 40 lines with no written reason, or a drifted count in a document whose instructions still work. Preferences of style or wording are listed and do not count.

Each lens starts from 10: each S1 takes away 4 points and caps the lens at 4, each S2 takes away 1.5 points and caps it at 7, each S3 takes away 0.5 points, the lowest score is 1 and the result is rounded down to the half point, so 8 means no S1, no S2 and at most four S3. The steps apply in the order written, S1 first, then S2, then S3, whatever the order of the report. For example, a lens with one S2 and one S3 scores 6.5, because the S2 takes 10 down to 8.5, its cap brings that to 7, and then the S3 takes 0.5 away; with the S3 first the same two findings would give 7, which is why the order is fixed. `quality-scoring` does not say yet what the cap does with two findings of the same class (two S2 give 7 if the cap comes after both and 5.5 if it comes after each), so the example above keeps one of each. One serious finding takes a lens below 8 by itself. Five S3 and nothing else give 7.5. A reviewer never corrects the result for an overall impression: if the number feels wrong, a finding is missing or has the wrong class. The scores come from an independent review, never from whoever did the work, and the other lens re-checks the S1 and S2 findings of the first on the evidence before a score stands. One score sheet for each lens in the perimeter records the lens, the perimeter, the findings by class, the count, the score, who reviewed and who re-checked, and what could not be verified; a change under three files that touches no interface and no contract uses a single sheet.

The rubric is itself still being calibrated, at every use and without being asked. Its log is `calibration.md` in the plugin's data folder, which survives updates of the plugin. The first line of the log holds the state: `CALIBRATING`, followed by k/5 where k counts the consecutive uses without a signal, or `STABLE`. A signal is one of three things: a disagreement (two reviewers class the same finding differently, or the computed score is more than one point from the one the reviewer would give at a glance), a missed defect (people found a defect later inside a perimeter that scored 8 or more) or noise (a finding that counted and that nobody would fix). A signal sets k back to 0, and a signal that recurs becomes a proposal to you with the exact change to the rubric and the log entries as evidence: the rubric never changes without you. After five consecutive uses without a signal, on at least two projects, the state becomes `STABLE` and you are told in one line; from then on a scoring adds one line only, and calibration starts again only on an evident anomaly. The detail is in `quality-scoring`.

<!-- section: lenses-gate -->
#### The gate

The gate applies at phase 6, before the work is integrated or released: every lens the work touches must score at least 8. The scores come from the `FINDINGS:` line of `blunt-reviewer` and from the sheets of the UX lens, and the gate reads them and not only the verdict, because a verdict `pass` can sit beside a lens at 7.5. `quality-scoring` does not say yet whether a finding that a later round saw fixed still counts in the score, nor which round's `FINDINGS:` line the gate reads. Below 8 the final validation stops and asks whether to fix or to defer: the PM lens proposes the fix or a deferral you can track (an issue, a TODO with a reference or a task, never a defect simply left), each with its cost, and you choose. Choosing the deferral is the go to ship the work with a deferred defect, and that go stays with you: during an autonomy the PM lens may only park an open blocking finding or propose a deferral to you. The description of the merge request carries the scores and the reviewer's lines `VERDICT:`, `FINDINGS:` and `COVERAGE:`, declared as the reviewer's own, because no mechanism records them in this version. The gate is a rule for the model: nothing in this version computes a score or stops a merge request. The detail is in `development-workflow` (phase 6 and the merge request), in `quality-scoring` and in `blunt-review`.

**Guaranteed by:** a rule for the model only (the rules `lenses`, `quality-gate` and `user-away` in `rules.md`, and the skills `development-workflow`, `interface-quality` and `quality-scoring`). Nothing computes a score or stops a merge request in this version, and the lenses other than the PM lens are subagents that the main session is asked to start.

<!-- section: lifecycle -->
### The life cycle of a piece of work, in three modes

The same small job goes through the whole cycle three times, so that the differences sit side by side: a button on the page of a monthly report that downloads the table as a CSV file (a plain text file of rows that a spreadsheet opens). The job changes an interface and needs tests, so it meets the lenses as well as the gates. The gates are numbered by their phase: gate 2 approves the spec and gate 6 approves the final validation. Each step names the skill that holds its detail, and the parts of this explanation say what guarantees it; this part has no guarantee line of its own, because it only follows the others. Everything here is a rule for the model, except that `autonomous-execution` can only be started by you.

#### Normal mode

Normal mode is the name for work without an autonomy: you supervise it, and you approve the spec at gate 2 and the final validation at gate 6. Nothing has to be switched on; it is what you get until you open an autonomy. The nine steps below are the whole cycle of the feature lane, and the other two modes change only who decides some of them.

1. **The request.** You write in chat: "Add a button to the monthly report page that downloads the table as a CSV file." The model names the lane, here a feature because it is new behaviour, and asks if the lane is not clear (`development-workflow`).
2. **Phase 1, idea and requirements, with no gate.** The PM lens writes its frame: a pre-mortem of three lines, for example that the file does not match the rows the page shows, that a large report makes the request slow, and that someone who may not see the page can download its data, each with what prevents it; the why; the reuse statement, for example "searched the report view and its tests for what builds the rows of the table, found the function that does it, will reuse it for the export"; and the smallest version, one button that downloads what the page shows, with its measured cost and not an invented one (`development-workflow`, `engineering-principles`).
3. **Phase 2, the design and the spec.** Because the job changes an interface, the UX lens proposes where the button goes and what its label says, the review lens attacks the proposal on evidence and cost, the UX lens answers, and then the decision is taken, before the spec is written (`interface-quality`). The design takes its three steps: a complete proposal, a first self-review that hunts for what is wrong with it, and a second self-review of the fixes of the first. Only then is the spec written, by default in `docs/superpowers/specs/` (`development-workflow`). A decision that is costly to reverse would also go through `adversarial-review-panel`; this job has none.
4. **Gate 2, heavy.** The model gives you a short synthesis, asks "is it clear?" in your language and waits. You approve in writing; a bare "ok" to a spec nobody read is not approval. Until you do, nothing else starts.
5. **Phases 3 and 4, the plan and the tasks, with two light gates.** The plan breaks the work into atomic tasks, each with a checkbox, a failing test written first and the file it names (`engineering-principles`):

   ```
   - [ ] Task 1: in tests/test_report_export.py, a test that asks for the export and expects the rows of the page (it fails: the export does not exist); then in reports/export.py, the function that writes those rows as CSV, reusing the one that builds them.
   - [ ] Task 2: in tests/test_report_export.py, a test that a user who may not see the page gets no file; then the permission check on the export.
   - [ ] Task 3: in tests/test_report_page.py, a test that the page shows the button; then the button, with its label.
   ```

   Each light gate is a quick coherence check, and after the last one the whole list is read once more with fresh eyes before any code (`development-workflow`).
6. **Phase 5, implementation, with no gate but an escalation.** The tasks run one at a time, in order. For each one the failing test is written and seen failing, then the code, then the tests of the touched area, then a review of the diff following `blunt-review`, and only then is the box ticked (`superpowers:test-driven-development`). With the default chain, `superpowers:subagent-driven-development` gives each fully specified task to an implementer subagent on Sonnet, with an order that names the files, the resources isolated for it and the shape of its report. Independent work that can run in parallel and needs a context of its own starts, in this order, as a new session through the desktop app when it has that tool, as a `spawn_task` chip, a suggestion that you open with one click, or as a subagent in its own git worktree; each gets its own preview host, database, cache index and ports, so that two of them never share a resource (`engineering-principles`). If a case comes up that the spec does not cover, for example that the report can hold thousands of rows and the spec says nothing about the size of the file, the task stops and the question comes to you: the executor invents nothing, and the spec or the plan is revised before the work resumes (`development-workflow`).
7. **Phase 6, validation.** The full suite runs, and no claim of success is made without the output of the command (`superpowers:verification-before-completion`). `blunt-reviewer` reviews the whole range of the branch, and with the verdict `changes` the review cycle runs on the fixes (`blunt-review`). Each lens the job touches gets a score from `quality-scoring`: here the new code (`code`), the old report code it touches (`legacy`), the route of the export with its permission check (`api`) and the three interface lenses (`clarity`, `aspect`, `accessibility`), measured on the real page in both themes. Suppose the review finds one minor problem in the new code, an S3: 10 minus 0.5 gives 9.5, and with no other finding every lens is at least 8 and the gate passes. Had one lens come out below 8, the validation would stop and ask you "fix or defer?", with the cost of each. The description of the merge request, prepared now, carries the scores and the reviewer's lines.
8. **Gate 6, heavy.** Again a short synthesis, "is it clear?" and your written approval. The merge request is opened only after the review and this gate, and a push, a merge request or a merge needs your explicit go (the rule `publishing`).
9. **Phase 7, closure.** `superpowers:finishing-a-development-branch` runs only after gate 6, and it prescribes no merge and no push: your own rules and your go apply, so nothing merges by itself. After you merge, the model cleans up the branches already merged and reports those that still hold unmerged work, writes the continuity note and proposes the rules that the lessons suggest, without applying them (`development-workflow`, `continuity-note`).

#### Day autonomy

You open it in chat, for this piece of work and with a hard stop: "go on without me until 18:00, but leave the data model to me." That opens the approval of the spec (`spec`) and design outside your office hours (`design`, which does nothing inside them), and your words keep the data model (`schema`) out. For a whole repository you would set the profile `pe.autonomy` instead, which stays until you unset it; the how-to guide on autonomy shows both. The steps are those of normal mode, and what changes is who decides; where the autonomy opens `spec`, a review cycle on the spec also comes before gate 2.

What passes to the lenses is this. At gate 2 the PM lens approves the spec in your place, but only after the design in three steps and a review cycle that closed on `pass` (`blunt-review`); the approval goes in the decision log with who decided, the positions and the costs. If round 2 of the cycle still ends with `changes`, the gate stays closed, and the PM lens may only park the open findings or propose a deferral to you. In phase 5 a technical case that the spec does not cover is decided by the review lens, and a question of scope or interface, here whether the file holds the rows of the page or of the whole report, by the PM lens, in one sentence with the reason, after hearing the other lenses and weighing five costs: tokens, time, quality, working behaviour and the satisfaction of the customer and the end user (`development-workflow`). Were the export to need a new column in the database, that would be the data model, which your words kept out: a provisional proposal would wait on a local branch, the tasks that depend on it would be parked, and the others would go on. Independent work that can run in parallel starts at once as a subagent in its own git worktree, because a new session or a `spawn_task` chip would wait for a click that nobody gives.

What does not pass, whatever you said, is an API contract (only the profile can open `contract`, and only for an API with no client yet: were the export also offered to a mobile app through a new route, that would wait for you), merges, production, shared systems, deletions outside the worktree, messages to people, irreversible actions, a change to what you asked for, and your instruction files. The plugin defines no opening for publishing, so nothing is pushed without your go unless your own rules define one. An autonomy does not open gate 6: the work comes to it ready and waits for you there. The suite has run, `blunt-reviewer` has reviewed the branch, the scores are computed and the description is prepared; with a lens below 8 the PM lens could only park the finding or propose a deferral to you. The one way to go further without you is `autonomous-execution`, which only you can start, by naming it: it runs an approved spec task by task, its own validation replaces gate 6, and your invocation is the go to push the branch and open the merge request, never to merge. It is a way of running the tasks, not a fourth mode.

When you are back, the first thing you read is the list of provisional decisions: one entry each in the decision log, with who decided, the positions, the costs and the state, which stays pending until you confirm or overturn it. Your answer in chat always prevails.

#### Night autonomy

Night autonomy is the same autonomy with one thing more, your authorisation to work unattended outside your office hours (`pe.officeHours`, for example `06-21`, which makes the night run from 21:00 to 05:59; without the key the rule is off). You give it in chat for this piece of work, with a start and a hard stop: "work on the export from 22:00 and stop at 06:00." A chat autonomy that covers the night is that authorisation; a profile never is.

With the spec approved and the tasks written, the model follows them to the letter, one task at a time and test first. An unforeseen technical case is decided by the review lens, provisionally and in writing; a case that would change the spec, an interface or the data model, such as a request to add a spreadsheet export too, is parked, and the independent tasks go on. If your autonomy opens `design`, the letter and the parking are lifted, and the lenses decide as they do by day. The project's remote is a company's, not a personal one (`pe.personalRemotes` says which are yours), so outside the window the model saves its work only as local commits: no push, no merge request, no pipeline, no edit of a tracker, no message (`safe-operations`). Even with a go given during the day, some things never happen at night: merges into shared branches, writes to clusters or cloud accounts, deletions outside the worktree, irreversible actions, messages to people and anything that needs credentials not already configured. A push to a remote that is personal is not held back by the window, but publishing still needs your go. Before the work starts, the model asks the host to keep the machine awake.

At the hard stop every session commits locally at a clean point and stops. When the window opens, one report comes first: what was done and with what confidence level, what was parked and why, the provisional decisions, the commits to re-create, the budget used and the tracker updates to make. Then the model re-creates the commits of the night, which were never pushed, inside the window and with their real dates, never faked ones, by running the script `recreate_night_commits.py` of `safe-operations` with `<base>`, the last commit already pushed or the branch point of a branch never pushed (unless your own rules name a re-creation procedure, which then applies). The script refuses to start outside the window or on a commit that is already on a remote branch, tags the tip `night-backup-<YYYYMMDD-HHMMSS>`, rebases in a temporary worktree and runs four checks: the files are exactly those of the tag, the number of commits is the same, the messages are the same, and both dates of every commit fall inside the window. Only when all four pass does the branch move; at the first failure it stops and the branch stays as it was. The dates are checked again on the integrated branch before its push, and once it is pushed you delete the tag with `git tag -d`. From there the work stands where it stands by day: at gate 6, which is yours, with the push and the merge request waiting for your go.

#### The three modes side by side

| | Normal mode | Day autonomy | Night autonomy |
|---|---|---|---|
| Who approves the spec (gate 2) | You, in writing | The PM lens, if the autonomy opens `spec` and the review cycle closed on `pass`; otherwise you | Approved before the night starts; as by day only if the autonomy opens `design` |
| Who decides while you are away | You are there; if you step away, the review lens decides technical cases and the PM lens scope and interface inside an approved spec | The same, and the lenses also decide what the autonomy opens (`spec`, `schema`, `design`) | The review lens decides technical cases, provisionally; what would change the spec, an interface or the data model is parked unless `design` is open |
| What may be pushed | Only with your go, and nothing to a remote that is not personal outside your office hours; a merge is always yours | Nothing without your go; the plugin opens no push, only an opening your own rules define does | Nothing to a remote that is not personal: local commits only, re-created in the morning; to a personal remote, only with your go |
| When the work stops | At each heavy gate until you approve, and with the closure, which merges nothing | At the hard stop you gave, or at gate 6 | At the hard stop, at a clean point, with the report first |

In all three modes the daily budget also applies where the host shows the usage: the work stops at a clean point when the next block would cross the ceiling of the day.

<!-- section: explain-rules-import -->
### Rules through an import

`rules.md` is the file of working rules. Its first line is the marker `PE-RULES v1`, and it has three blocks: rules for every agent, rules for the main session, rules for subagents. It states that your own instructions prevail on conflict, and that a conflict with its five precedence rules, which rank in this order (evidence, no bug left behind, test-first, blunt review, burden of proof on adding), goes to you and is never resolved silently. When instructions disagree, this order decides: your explicit request, then your project's configuration (for stack, commands, conventions and the language of prose, such as the project's instruction file or the constitution of spec-kit), then your personal configuration, then the default rules of the plugin. If the project declares neither its test command nor the language of its prose, the model asks and offers to write it down.

The plugin root does not survive a plugin update and the plugin's data folder does, so at every session start `SessionStart` copies `rules.md` from the root to the data folder when the copy is missing or different. Your `CLAUDE.md` imports the copy with one `@` line; that is how the rules reach the session as your own instructions, which superpowers ranks above its skills. The second line you add is the safety line, for the day the plugin is gone.

In your `CLAUDE.md` exactly two lines change, and you add them yourself: the hook only reads the file and prints what is missing. The rules reach the main session and the subagents that load your `CLAUDE.md`; they do not reach `Explore`, `Plan` and agents defined with `omitClaudeMd: true`. A rules update applies from the next session. An end-to-end test, run on request, gives evidence about Claude Code's import; it is not a mechanism of the plugin and does not run in your session (the install guide says what it covers).

The same care binds the model: it changes an instruction, settings or memory file only after a dated copy, a diff and your go, and a lesson, such as a rejected mistake or a recurring trap, becomes a proposed rule with the layer where it should live (your project's instruction file, your personal configuration or the project's memory), never a rule applied without your explicit request. The block for subagents is short: the deliverable file is written in blocks with a status line, as the section on continuity says; conflicts and missing decisions go back to the coordinating session; a subagent never pushes, opens a merge request or merges; and it modifies no instruction, settings or memory file unless its task says so.

**Guaranteed by:** a mechanism for the delivery: the hook copies and checks, and Claude Code's `@` import brings the file in. A rule for the compliance (the rules `precedence`, `backup-diff-go`, `escalate`, `no-publishing` and `no-config-edits` in `rules.md`): the model is asked to follow the rules, and nothing checks that it does.

<!-- section: explain-working-rules -->
### Working habits

The rules for every agent shape each step of the work, and the skill named for each habit holds the detail. Before any code, an agent understands how the existing system works and why, reads a file before it changes it, does only what was asked, edits before it creates, writes no documentation file unless asked, asks when a requirement is ambiguous or two approaches are valid, and uses no emoji (`scope`). It states a claim only after verifying it, says how sure it is with one of three labels, which are verified in the real environment, tests passing and deployed with the real-environment check still pending, and unit tests only, and it re-checks the claim of another agent or lens instead of taking it as evidence (`evidence`). A bug is never closed at the first problem found: the agent says what the fix resolves and what it does not. An investigation reads the inputs, computes each number from two independent sources, rules out at least two alternative explanations and separates what is verified from what is inferred, and a correction of code or data first lists every path that writes the state, uses the distinction the system already encodes, anchors notes to names and not to line numbers, and delimits the population to correct before it writes the fix; `evidence-based-investigation` holds the method.

Before new code, the agent searches for what already does the job, cheapest search first, and states the result in the reuse statement: where it searched, for what, and whether it found something to reuse or extend or found nothing; without that statement there is no code (`reuse`). Whoever adds code, a dependency, a rule, an option or a part of a spec proves that it is needed, and the question that settles it is what breaks if it is deleted; tests, guards, validation and error handling are the exception, and "less code" is never a reason to drop them (`burden-of-proof`). The bar of `engineering-principles` for design is short: a component's place is decided and stated before it is created, dependencies point one way, an invariant lives in the data and not in a view or a docstring, no query on the path of a request grows with the data, every input is validated at the boundary and permissions are checked before every operation.

Every bug, failing test or issue met is fixed in the same session, even when the work did not cause it, unless the fix needs a much wider scope, and then you choose between doing it now and a tracked task; every block of work closes with one of two exact statements, "All tests pass, no known residual bugs" or the list of the issues met, resolved and deferred with your authorisation (`no-bug-left`). Identifiers are in English whatever the language of the project's prose (`english-identifiers`), and documentation changes in the same commit as the code (`docs-same-commit`). `documentation-quality` says how documentation is divided and what it may claim: four kinds, a tutorial, a how-to guide, a reference and an explanation, told apart by whether the page guides what the reader does or what the reader knows and whether the reader is learning or working; a document describes only what exists today and says what a control does not cover; and the manual for the daily users of an administration interface keeps its text once, in Markdown, with screenshots generated by a script.

A delivered API contract, one that is merged, running in an environment or documented to the developers of a client, never changes shape: no field, enum value, error code, status for a request that succeeds today, mandatory parameter or route is added, renamed or removed. A change that seems needed is announced on a separate line at the top of the message and made only with your go given after that notice, and the one exception is a profile that opens `contract` for an API with no client yet. A spec that touches an API says "contract unchanged" or "CONTRACT CHANGE", is written against the scenarios of the client's real code, and a test compares the schema shape with the delivered one (`api-contract`). Each session and subagent uses its own preview host, database, cache index, ports and test user, and stops only what it started, by name (`isolated-sessions`). Secrets never go into files, memory, notes, logs or commit messages, and a secret pasted in the chat is never stored: you are warned to revoke it (`secrets`).

Where the host shows the model the account's usage, the main session also keeps a daily budget. At the first block of the day the allowance is what remains of 85% of the weekly limit after the share already used, divided by the days left to the weekly reset, today included, and the ceiling of the day is the weekly share at that moment plus the allowance. The usage is checked at every block, and the work stops at a clean point when the next block would cross the ceiling. The other 15% of the weekly limit is a reserve for a production incident, and crossing the ceiling or touching the reserve needs your go in chat for that day (`budget`). Where the host does not show the usage, the rule does not apply.

**Guaranteed by:** a rule for the model only (the rules `scope`, `evidence`, `reuse`, `burden-of-proof`, `no-bug-left`, `english-identifiers`, `docs-same-commit`, `api-contract`, `isolated-sessions`, `secrets` and `budget` in `rules.md`, and the skills `engineering-principles`, `evidence-based-investigation`, `documentation-quality` and `development-workflow`). Nothing checks any of them in this version, and the budget works only where the host exposes the usage.

<!-- section: explain-continuity -->
### Continuity

Work is saved ahead, in three forms, all described by `continuity-note`. The progress note is the state on a few lines (done, in progress, next, open decisions), updated at every milestone and read again after a compaction; it lives where your own configuration keeps the state of the work (a resume card, a diary), or in the project's own note when the project declares one, and only otherwise in `.pe/progress.md` at the root of the repository, with a `.pe/.gitignore` that contains `*`. The deliverable file of a task given to a subagent is written in blocks and carries a status line on top, `STATUS: IN PROGRESS - done: ...; next: ...`, which the last block replaces with `STATUS: COMPLETE`. The full continuity note is written when a session ends with work in progress or when work passes to another agent, so that a fresh context resumes without replaying the conversation. The full note leads with the goal and the current state, marks what was verified and what is only assumed, and goes on with the next steps, the key decisions and their reasons, the traps, the files and how to verify; it never carries a secret, only where a credential lives.

The coordinating session hands over to a new session at the first clean point of a new day, or when its context passes 300,000 tokens, read where the host shows it. The handover is explicit: the old session writes the continuity note and the line `handover to <name> at <time>` in the progress note and takes no action from then on, and the new one sends nothing before it has read that line. Every time written in a note, a log or a report is read with `date` or from git, never estimated.

**Guaranteed by:** a rule for the model only (the rules `save-ahead` and `status-line` in `rules.md`). Nothing counts the saves, so a compaction loses at most the work done since the last save, and how small that is depends on the model's discipline.

<!-- section: explain-office-hours -->
### Office hours

If you set office hours, outside them the model keeps your work local: it commits, and it does not push to a remote that is not personal, open a merge request, start a pipeline, edit a tracker or send a message. Weekends and the holidays you list open later, at the hour you choose. Unattended work outside the hours runs only when you authorise that piece of work with a hard stop, and commits made outside the window are re-created inside its weekday hours, even when the re-creation happens on a weekend morning, with their real dates, never with faked ones. Without the setting the rule is off; the how-to guide on office hours shows the keys.

Unattended work follows the approved spec and tasks to the letter, one task at a time and test first; a technical case nobody foresaw is decided provisionally by the review lens, and a case that would change the spec, an interface or the data model is parked while the independent tasks go on. Even with a go given during the day, some things never happen outside the window: merges into shared branches, writes to clusters or cloud accounts, deletions outside the worktree, irreversible actions, messages to people and anything that needs credentials not already configured. At the hard stop every session commits locally at a clean point and stops, and when the window opens one report comes first: what was done and with what confidence level, what was parked and why, the provisional decisions, the commits to re-create, the budget used and the tracker updates to make. Before long unattended work the model asks the host to keep the machine awake. An autonomy that opens `design` lifts the letter and the parking, but not the need of an authorisation with a hard stop, and a profile alone is never that authorisation.

**Guaranteed by:** a rule for the model only (the rule `office-hours` in `rules.md` and the skill `safe-operations`). Nothing blocks a push at night in this version; a guard that does is planned for a later version.

<!-- section: explain-communication -->
### How the plugin talks to you

The model explains briefly and at a high level at four moments: at the start and at the end of a work block (a feature, a decision or a delivery, never a single task), at every architecture choice (the choice, the main alternative discarded and why) and before a heavy gate. Each explanation ends with "is it clear?" in your language, and what you say is unclear is explained again with different words and an example. The answer is awaited only at the two heavy gates and at architecture choices, and never while you are away or during an autonomy; there is no quiz and no verification question, ever. The tone is frank: no agreeing to please, no flattery, weak reasoning challenged with evidence, risks and opportunity costs named, and a guess about your intent labelled as a guess. Your own ideas are proposals to validate, not instructions to record: the model tests each against feasibility, cost, sequence and risk and says first where it does not convince, then records it with those caveats. The skill `teach` carries the explanations and the method for teaching code; the rules file carries the tone.

When you ask to be taught some code, the method has six layers, in this order: the problem the code solves, the path through the code written as `file::function`, the choices and the discarded alternatives, a concrete case followed from start to end, the limits, and a command or test you can run to check it yourself; a layer with nothing to say gets one honest line saying so. When a session resumes, the model shows the state on one screen, taken from the continuity note or the progress note, and asks "is it clear?".

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

There are no commands in this version and, besides the `SessionStart` hook described below, only one script, `skills/safe-operations/recreate_night_commits.py`, which `safe-operations` tells the model to run.

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

`rules.md` is the working rules file, starting with the marker `PE-RULES v1`. The `.pe/` folder, at the root of a project, holds `reviews/` (the reports of `blunt-reviewer`) and `progress.md` (the progress note), and it never enters git because of its own `.gitignore` with `*`. In the plugin's data folder, next to the copy of `rules.md`, `quality-scoring` keeps `calibration.md`, its calibration log. `skills/safe-operations/recreate_night_commits.py` re-creates, inside the office hours, the commits made outside them and never pushed, and leaves a `night-backup-<YYYYMMDD-HHMMSS>` tag in the repository. To run it by hand: `python3 <the folder of safe-operations>/recreate_night_commits.py <base>`, from any directory of the repository. The `<base>` is the last commit already pushed or the branch point of a branch never pushed.

<!-- section: license -->
## License

MIT, see [LICENSE](LICENSE). The works this plugin builds on are credited in [NOTICE](NOTICE).
