---
name: engineering-principles
description: Use when understanding a requirement, proposing an approach, or writing or changing code or documentation. Understand before implementing, reuse before building, design and placement principles with the bar of the architecture, delivered API contracts and the client's scenarios, scalability and cost, test discipline on top of superpowers:test-driven-development with isolated sessions, no bug left behind, secure coding, secrets hygiene and writing rules.
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

Give every module one responsibility and separate the concerns: what changes for different reasons lives in different places. Aim for high cohesion inside a module and low coupling between modules. A module hides its decisions behind a small public surface, and others use that surface and nothing behind it.

Judge every choice by one question: is the result easy to change? Anticipate a change only when it is named and probable, and then isolate its impact behind a stable interface. Values that differ between environments live in configuration. Generality built for hypothetical futures is a defect, not a virtue.

State contracts explicitly: preconditions, postconditions and invariants. Check them in the code, and stop immediately in front of an impossible state instead of carrying on with it.

Before creating a model, module, service or any significant component, decide where it belongs; never default to the module you happen to be in. Follow the better existing precedent, and never copy an anti-pattern for the sake of consistency. State the decision in this form: "[component] goes in [location] because [single responsibility, cohesion, direction of dependencies]. Alternatives [X, Y] rejected because [...]. [consumer] uses [domain], not the reverse." When the placement is not trivial, or changes module boundaries such as a new module or a moved model, take it to the user before writing anything. Only a field or a trivial helper with an obvious home skips this.

The bar of the architecture holds for every structure: few parts, clear owners, dependencies pointing one way.

- One direction, with no cycles: the common core, then the domain modules, then presentation, interfaces and commands. No domain module imports from presentation, and no batch job depends on an interface.
- One owner for each concept: each model, rule and invariant has one home module; the others read through its query functions and write through its services.
- Thin edges, deep core: no business rule and no data query in views, templates, serializers or commands.
- Invariants in the data: database constraints, or the single service that writes the data, never a view, a template or a docstring.
- A change stays local: a plan that touches more than three modules, or one change that forces edits in many, justifies the coupling, or the design is wrong.
- What is expensive to reverse (a schema, module boundaries, a public interface, a new dependency) goes through `adversarial-review-panel` first, with a short decision record: the alternatives rejected and the way back.
- In a project with a CI, an import-contract check (layers, forbidden imports, no cycles) fails the pipeline, and so does a test that no view or template queries the data layer.

## Delivered API contracts

A contract is delivered once it is merged, running in an environment, or documented to the developers of a client. A delivered contract never changes shape. The server may change which data it returns, never the shape: no field renamed, removed or added in a response, no new enum value, no new error code, no new status for a request that succeeds today, no new mandatory parameter, no route added or renamed. A new rule is expressed with the fields, values and error codes that already exist, and the server stays tolerant of what clients already send.

A change that seems necessary is announced on a separate line at the top of the message, never inside a list: the route, the field, the value or the status that would change, why, who is affected, and the alternatives that change nothing. It is made only with the user's go given after that notice, never implied by a wider approval and never decided while the user is away. A gross error in the contract itself follows the same path. The one exception is an autonomy profile that opens `contract` (`development-workflow`): until the API's first release or first client, the lenses may change its shape, with its documentation and the test's delivered schema updated in the same commit, and the spec quotes the decision log entry where it would quote the user's permission.

Before a spec that touches an API a client uses, write the scenario table from the client's real code and screens: for each scenario, the exact calls the client makes (method, path, body and order, with the client's `file:line`) and the answer the server must give (the status and the fields that decide). The spec is written against the table, and the live HTTP checks replay it row by row. A row is replayed live as soon as the first task makes it reachable, not at the end. Every question on the contract that the table raises goes to the user in a single pass, never one at a time. Without the client's code, say so and ask for it before the spec.

Every spec and every brief that touches an API states "contract unchanged", or "CONTRACT CHANGE" with the user's permission quoted, and a test compares the shape of the API schema with the delivered one.

## Scalability and cost

No query on the path of a request may grow with the data. N+1 is a defect in every form, including the hidden ones inside a serializer or a loop of calls: fetch related data in a bounded number of queries, aggregate in the data store rather than in a loop, and bound the size of every result. Heavy work runs in batches, not inside a request. A loop over external calls has its cost (calls, latency, price) stated before it is written. A cache needs a deterministic key and an explicit invalidation. Indexes are verified under load, never assumed.

## Tests

The red-green cycle is the one of `superpowers:test-driven-development`: write the test, see it fail for the right reason, then write the code that turns it green. This skill does not repeat it. It adds the following.

- Break the work into atomic tasks first, each one concrete and each with a checkbox: not "implement feature X" but "create file X with class Y containing method Z that does W, with tests T1-T3". Run them one at a time, in order, without batching or skipping ahead. Only genuinely trivial work, such as a typo, a mechanical rename, an obvious configuration value or a documentation change, skips the test-first rule, and it must be obviously trivial.
- A test that cannot fail is not a test: no tautologies, and no assertion that only checks the mock the test set up. Cover the boundaries and the edge cases, and assert the exact expected value, not merely that something came back.
- Where the code has invariants, add property-based tests: state the invariant (sorting twice gives what sorting once gives) and let a generator search for the input that breaks it.
- Before every commit, run the tests of the touched area, with zero failures; the module's suite once for each block of work; and the whole suite once on the integrated branch, with the pipeline's pre-checks, before the push, in the same environment as the CI when the project has one, so the CI never runs a known red. A step of the CI is proven with the real command it runs. A red found after the push has cost the whole team.
- Isolated sessions: each session or subagent has its own preview host (such as `<name>.localhost`, because cookies belong to a host), database, cache index, ports and test user, which the project's configuration provides. It stops only what it started, by name, never with a blanket stop of every container, a whole compose project or a kill by pattern. A brief to a session that starts servers, tests or previews names its resources. Independent work that runs in parallel and needs its own context, other than a lens or a review, which stays the subagent its skill names, starts as a subagent in its own git worktree while the user is away or an autonomy is open, because a new session or a chip waits for a click nobody gives; otherwise it starts in this order: a new session through the desktop app's `start_session` tool, when the session has it; otherwise a `spawn_task` chip the user opens with one click; otherwise a subagent in its own git worktree. Each gets its own resources as above; the first two are tools of the host, not of the plugin, which cannot add them. Worktrees of one repository share the stash and git's memory of resolutions (rerere), so parallel work is parked with a `wip:` commit, never with a stash.
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
- Identifiers are always in English, whatever the language of the project's prose. That covers classes, functions, methods, variables, parameters, attributes, constants, tests and test classes, fixtures, modules and files, template keys, form fields, internal data keys and branch names. Prose keeps the project's language: comments, docstrings, logs, error messages shown to people, labels, help texts, every user-facing string and the documentation.
- A name that mixes languages is forbidden. Identifiers already written in another language are renamed only when that code is rewritten anyway, never in a sweeping rename. A domain term with no English equivalent stays as it is, as a proper noun, and the docstring explains it.
- Documentation changes in the same commit as the code: docstrings, API specifications, and the README when architecture, workflow, configuration or operations change.
- How documentation is divided into kinds, what a document may claim, and the manual of an administration interface live in `documentation-quality`.
- The answer to a technical FAQ starts from the fact, then names the entities involved, gives the path in the form `file::function`, adds one concrete case and points to the source.
- For the language, framework, database and libraries in use, the project's conventions and the user's configuration come first, then the official documentation of the version in use, read with Context7 when it is installed instead of from memory; an interface that depends on the version is verified before it is used.

## Further reading

- *The Pragmatic Programmer* (David Thomas, Andrew Hunt; 20th anniversary edition): habits of a working programmer, from reversibility to crashing early.
- *Fundamentals of Software Engineering* (Carlo Ghezzi, Mehdi Jazayeri, Dino Mandrioli): the principles behind modularity, abstraction and the cost of change.

Both are recommended reading and not sources of text: nothing above is copied from them.
