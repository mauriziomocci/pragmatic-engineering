---
name: configure
description: Use when the user asks how to configure or set up the plugin, or asks about its office hours, weekends, holidays, personal remotes or autonomy profile. It shows the current values, then asks one question at a time and sets what the user chooses.
---

# configure

This skill guides the user through the plugin's own settings, six git configuration keys named `pe.*`. It answers first, then asks the questions, in the language the user writes in.

## When to use

- The user asks how to configure or set up the plugin, or how to set its office hours, weekend hour, holidays, personal remotes or autonomy profile.
- Not for the settings of another tool, and not for an installation problem: the install guide of the README covers that.

## The keys

- `pe.officeHours`, global: the window `HH-HH`, the second hour outside it (`06-21` is 06:00 to 20:59); unset or `none`, the rule is off.
- `pe.weekendFrom`, global: the hour `HH` from which Saturdays, Sundays and holidays open; unset, they open at the start of the window.
- `pe.holidays`, global: a comma list of `MM-DD`, `easter+N` and `easter-N`; unset, no date is a holiday.
- `pe.personalRemotes`, global, several values (`--add` adds one): push-URL prefixes; unset, no remote is personal.
- `pe.autonomy`, local to one repository: a comma list among `spec`, `schema`, `design` and `contract`; unset, nothing is opened.
- `pe.privateTermsFile`: only for the maintainers of this repository.

## The flow

1. Read the current values: `git config --show-origin --get-all pe.<key>` for each global key, which reads the merged configuration as the rules do and prints the file of each value, and, inside a repository, `git config --local --get pe.autonomy`. Show the state in a few lines, with the file each value comes from (for a key with one value, the last line is the one the rules read), and ask which keys the user wants to set unless they already said.
2. Ask one question at a time, only about the keys the user wants, and wait for the answer before the next one. For each key say what it does and what happens while it is unset, and propose a value.
3. Check the answer against the format of its key. On a wrong one, say why and ask again.
4. Show the exact command, with `--global` for a global key even when step 1 found its value in another file. For a global key, run it only after the user's explicit yes to that command, then read the value back with the command of step 1. For `pe.autonomy`, never run it: show it for the user's own terminal, because only the user sets the profile. For `pe.privateTermsFile`, point to the README section for maintainers and stop.
5. At the end, list the configured values in a few lines and ask "is it clear?", as `teach` says.

## What configure never does

This skill never changes a key the user did not ask about, never writes a configuration file directly and never runs a command the user has not seen.

## Where the rest lives

What each opening of `pe.autonomy` means lives in `development-workflow`; the office-hours rule lives in `safe-operations`.
