---
name: spec-driven-layout
description: Use only when the user asks for spec-kit. Where spec-kit keeps its files (specs/NNN-slug/ at the repository root, constitution and templates under .specify/), which command serves each phase, how much to materialise for the weight of the work, and how the constitution ranks among the instruction layers.
---

# spec-driven-layout

`development-workflow` says when each artifact is produced. This skill says where the artifacts live on disk, and how many of them a piece of work needs.

## When to use

Load it only when the user asks for spec-kit. A feature uses one chain of tools (`development-workflow`). Without the request, the superpowers chain is used and this skill stays unloaded.

## Where spec-kit keeps its files

In spec-kit 0.8.9 the specs of the features live in `specs/NNN-slug/` at the root of the repository, not under `.specify/`. The constitution is `.specify/memory/constitution.md`, and the templates are in `.specify/templates/`.

```
.specify/
    memory/
        constitution.md
    templates/
        spec-template.md
        plan-template.md
        tasks-template.md
specs/
    NNN-slug/
        spec.md
        plan.md
        tasks.md
        research.md      (optional)
        quickstart.md    (optional)
```

There is one folder per feature. Folders are numbered in order (`001-`, `002-`) and carry a slug in kebab-case.

## Commands by phase

- Phases 1-2, idea, requirements and spec: `speckit-specify`, then `speckit-clarify`.
- Phase 3, plan: `speckit-plan`.
- Phase 4, tasks: `speckit-tasks`.
- Phase 5, implementation: `speckit-implement`.

These names were tried with spec-kit 0.8.9, and names change between versions. If the project has a different version, check the installed names before using them.

## Phases and artifacts

| Phase | Artifact | Gate |
|---|---|---|
| 1 Idea and requirements | Chat only. Clarifications are captured in `spec.md`. | none |
| 2 Spec | `spec.md` | heavy |
| 3 Plan | `plan.md`, plus `research.md` if an investigation is needed | light |
| 4 Tasks | `tasks.md` | light |
| 5 Implementation | Updates to `tasks.md`: each task's box goes from `- [ ]` to `- [x]` | none |
| 6 Validation | A final checkpoint section in `tasks.md`, and the review of phase 6 | heavy |
| 7 Closure | Closure as `development-workflow` says, with no merge, tag or copy of memory prescribed | none |

## How much to materialise

Not every piece of work needs the full set of artifacts. What is written to files scales with the weight of the work.

| Work type | Mandatory artifacts | Optional artifacts |
|---|---|---|
| Feature: three files or more, new behaviour, architectural decisions | `spec.md`, `plan.md`, `tasks.md` | `research.md`, `quickstart.md` |
| Extensive refactor | `plan.md`, `tasks.md` | `spec.md`, if a contract changes |
| Fix touching three files or more, or with a regression risk | `tasks.md` | `plan.md`, if the cause is not obvious |
| Trivial fix, one-shot script, configuration tweak | none: chat only, with a spoken heavy gate | none |

The heavy gates of phases 2 and 6 stay whatever is materialised. Only the files scale.

## Constitution precedence

The constitution is the project's configuration. Among the instruction layers of `development-workflow` it prevails over the user's personal configuration and over the plugin's default rules, for stack, commands and conventions. The user's explicit request prevails over it. A conflict with the five precedence rules goes to the user, never resolved silently. Where the constitution is silent on a topic, the lower layers apply. A project without a constitution runs without any spec-kit convention.

## Templates

If `.specify/templates/` holds project-local templates (`spec-template.md`, `plan-template.md`, `tasks-template.md`), they are used when the artifacts are written. Otherwise the artifacts follow the structure that the phases imply.
