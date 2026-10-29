---
name: engineering-principles
description: Use when understanding a requirement, proposing an approach, or writing or changing code or documentation. Understand before implementing, reuse before building, design and placement principles, scalability and cost, test discipline on top of superpowers:test-driven-development, no bug left behind, secure coding, secrets hygiene and writing rules.
---

# engineering-principles

This skill carries the principles with which code and documentation are written and changed. Tone and the way work is reviewed live in `blunt-review`.

## When to use

Load it before understanding a requirement, proposing an approach, or writing or changing code, tests or documentation: that is almost all engineering work. The only work that skips it is work that is plainly trivial, such as a typo, a mechanical rename or an obvious configuration value. The exception has to be obvious, not convenient: if it takes an argument to call the work trivial, it is not trivial.

## Understand and reuse

Before any code, whether a fix, a feature or a structural change, understand how the existing system works, why it works that way and what already exists. Fixing a symptom without its cause produces layers of workarounds, so find the cause first. Read a file before modifying it, and prefer editing an existing file to creating a new one.

Before writing any non-trivial function, service, query helper, utility, class or component, search for what already does the job. Search in this order, cheapest first:

1. The reuse catalog or the documentation of the services, if the project keeps one.
2. A targeted search on the concept, reading the signatures of what comes back.
3. An exploration sub-agent, only when the first two leave a real doubt.

Never answer from memory, and never scan the whole codebase. Then state the result in one line: "Searched [where] for [what]. Found [X]: will reuse or extend. / Found nothing: building new." Without that statement there is no code. Only obviously trivial code, such as one-off glue or a throwaway script, skips it.

The order of preference is fixed: reuse what exists; when it is close but imperfect, extend or refactor it and never write a parallel twin; write new code only when nothing fits. If reuse would need a refactor larger than the task, stop and give the user the duplication risk and the two options; the user decides.

One source holds for knowledge as well as for code: documentation, configuration and schemas are stated once, and everything else points to that place.

## Design

Give every module one responsibility and separate the concerns: what changes for different reasons lives in different places. Aim for high cohesion inside a module and low coupling between modules. A module hides its decisions behind a small public surface, and others use that surface and nothing behind it. Dependencies point one way, from the consumer toward the domain, never the reverse: a batch job does not depend on a presentation module.

Judge every choice by one question: is the result easy to change? Anticipate a change only when it is named and probable, and then isolate its impact behind a stable interface. Values that differ between environments live in configuration. Generality built for hypothetical futures is a defect, not a virtue.

State contracts explicitly: preconditions, postconditions and invariants. Check them in the code, and stop immediately in front of an impossible state instead of carrying on with it.

Before creating a model, module, service or any significant component, decide where it belongs; never default to the module you happen to be in. Follow the better existing precedent, and never copy an anti-pattern for the sake of consistency. State the decision in this form: "[component] goes in [location] because [single responsibility, cohesion, direction of dependencies]. Alternatives [X, Y] rejected because [...]. [consumer] uses [domain], not the reverse." When the placement changes module boundaries, such as a new module or a moved model, take it to the user before writing anything. Only a field or a trivial helper with an obvious home skips this.

## Scalability and cost

No query on the path of a request may grow with the data. N+1 is a defect in every form, including the hidden ones inside a serializer or a loop of calls: fetch related data in a bounded number of queries, aggregate in the data store rather than in a loop, and bound the size of every result. Heavy work runs in batches, not inside a request. A loop over external calls has its cost (calls, latency, price) stated before it is written. A cache needs a deterministic key and an explicit invalidation; a cache without invalidation is a bug waiting. Indexes are verified under load, never assumed.

## Tests

The red-green cycle is the one of `superpowers:test-driven-development`: write the test, see it fail for the right reason, then write the code that turns it green. This skill does not repeat it. It adds the following.

- Break the work into atomic tasks first, each one concrete and each with a checkbox: not "implement feature X" but "create file X with class Y containing method Z that does W, with tests T1-T3". Run them one at a time, in order, without batching or skipping ahead. Only genuinely trivial work, such as a typo or a mechanical rename, skips the test-first rule, and it must be obviously trivial.
- A test that cannot fail is not a test: no tautologies, and no assertion that only checks the mock the test set up. Cover the boundaries and the edge cases, and assert the exact expected value, not merely that something came back.
- Where the code has invariants, add property-based tests: state the invariant (sorting twice gives what sorting once gives) and let a generator search for the input that breaks it.
- Before every commit, run the suite that the project's configuration declares, with zero failures, and in the same environment as the CI when the project has one. A red found after the push has cost the whole team.
- Tests use the same database engine as production.
- No test is skipped without a traceable reason (an issue or a TODO with a reference), and no expected-failure marker is used to hide a red.

## No bug left behind

Every bug, failing test or issue met during a session is fixed in that same session, even when the current work did not cause it: stop, diagnose the real cause, fix it. Unresolved issues pile up silently.

- A fix that needs a much wider scope (a large refactor, an architecture change, an unrelated module) is escalated to the user with the choice of doing it now or in a dedicated task. The user decides. A deferral is tracked in an issue, a TODO with a reference or a task, and is never just left behind.
- A session never closes with failing tests, ignored warnings or a known bug that nobody has written down.
- Four shortcuts are forbidden as ways to hide a problem: a skipped test without a traceable reason, an exception caught and swallowed, a "fix later" comment, and a failing assertion removed.
- Every block of work closes with one of two statements, written exactly: "All tests pass, no known residual bugs", or "The following issues were encountered during the session: [list]. Resolved: [list]. Deferred with explicit authorization: [list with reference]."
- Never accept "it works and I do not know why". A correction that works by chance is not a correction: keep going until the cause is explained, or say plainly that it is not understood.

## Secure coding

- Queries and commands are never composed by concatenating input: use parameters and argument lists.
- Secrets never reach a log.
- Every input is validated at the trust boundary, where data enters from a user, another system, a file or a tool.
- Permissions are checked before every operation, not only at the door.
- Public interfaces have rate limits.
- Least privilege: each process, token and account gets only the access its job needs.
- For tools that an agent can call, authorization comes in tiers. Reading is free. Writing needs a session that expires. An irreversible operation needs a confirmation for that single operation, given outside the channel of the agent, so that the agent cannot give it to itself. Every parameter the operator must supply is declared in the interface of the tool, never guessed.

## Secrets hygiene

A secret (a key, token, password or certificate) never goes into a versioned file, an instruction file, a memory, a note, a log or a commit message. Document where the credential lives and how to use it, never its value. A secret pasted into the chat is not saved anywhere: warn the user and suggest revoking it.

## Writing

- Comments and docstrings say why: the non-obvious decision, the constraint, the trade-off. They never say what the code plainly does, and obvious code, idioms and boilerplate carry none.
- Identifiers are always in English, whatever the language of the project's prose. That covers classes, functions, methods, variables, parameters, constants, tests and test classes, fixtures, modules and files, template keys, form fields, internal data keys and branch names. Prose keeps the project's language: comments, docstrings, logs, error messages shown to people, labels, help texts, every user-facing string and the documentation.
- A name that mixes languages is forbidden. Identifiers already written in another language are renamed only when that code is rewritten anyway, never in a sweeping rename. A domain term with no English equivalent stays as it is, as a proper noun, and the docstring explains it.
- Documentation changes in the same commit as the code: docstrings, API specifications, and the README when architecture, workflow, configuration or operations change.
- Documentation is divided by type following Diataxis (https://diataxis.fr): tutorials, how-to guides, reference and explanation, one type per page. One exception is declared, the entry page: the README, which for someone arriving lines up the first session, the guides, the explanation and the reference, each in its own section. This skill carries no text of the framework.
- The answer to a technical FAQ starts from the fact, then names the entities involved, gives the path in the form `file::function`, adds one concrete case and points to the source.
- For the documentation of an external library, use Context7 when it is installed, instead of memory.

## Further reading

- *The Pragmatic Programmer* (David Thomas, Andrew Hunt; 20th anniversary edition): habits of a working programmer, from reversibility to crashing early.
- *Fundamentals of Software Engineering* (Carlo Ghezzi, Mehdi Jazayeri, Dino Mandrioli): the principles behind modularity, abstraction and the cost of change.

Both are recommended reading and not sources of text: nothing above is copied from them.
