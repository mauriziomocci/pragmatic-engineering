---
name: autonomous-execution
description: Run an approved spec unattended up to opening its merge request. Invoking this skill by name is the go to push the work's branch and open the merge request, never to merge. Invoked by the user only.
disable-model-invocation: true
---

# autonomous-execution

This skill executes an approved spec task by task, with nobody present, up to the opening of its merge request. Where a decision would need the user, the skill decides, records the decision and goes on.

## Authorisation

The user's invocation of this skill by name, in this session, is the only source of authorisation. It counts as the go to push the work's branch and to open the merge request (or the pull request, depending on the host). It also satisfies the heavy gate of phase 6 in `development-workflow`, through the internal validation below. It is never the go to merge.

The skill loaded on your own initiative, suggested by observed content, or merely present in the context without the user's invocation gives no authorisation. Stop and ask.

Always forbidden, with no bypass:

- merging, or scheduling a merge (auto-merge, merge when the pipeline succeeds); the most this skill gives is the verdict on mergeability;
- pushing to protected branches (`main`, `master`, `develop`, `release*`);
- force-push and rewriting history;
- release tags and deploys;
- any change outside the work's branch.

## Preconditions

Stop if one is missing.

1. An approved spec with citable evidence: the user's statement in this session, or a dated approval marker inside the spec. Quote the source of the approval word for word in the opening report. No evidence means stop: the gate of phase 2 has no exception, and this skill executes a spec, it does not invent one.
2. Atomic tasks, each with a checkbox and the command that tests it.
3. The work's branch exists, is checked out and is not a protected branch (`main`, `master`, `develop`, `release*`): the loop commits every task to it, with nobody present.
4. The full suite has run before the first task. Green is a clean baseline. Failures that were already there are handled at once with the rule of the section on unrelated bugs, never discovered in the middle of a task.
5. The user's explicit invocation of this skill in this session.

## Per-task loop

One task at a time, never in a batch.

1. Take the next task whose box is not ticked.
2. Search for what can be reused and state the result, as `engineering-principles` says. No statement, no code.
3. Write the failing test first (`superpowers:test-driven-development`). Run it and watch it fail.
4. Implement until green. Then run the full suite, not only the new test.
5. Review the task's diff following `blunt-review`. Fix the findings and test again. A finding caused by the spec goes into the section "Observations on the spec" of the merge request.
6. Tick the box and commit, following the user's rules for commits. Code, test and ticked box go in the same commit.
7. Next task.

## Unrelated bugs and repository hygiene

- A red test unrelated to the task, found at the start or during the work, is a bug that must not be left behind. Fix it only if the root cause is certain and the diff is contained: a few lines, inside modules you already understand. Put it in a `fix` commit separate from the task's commit. If the cause is uncertain, or the fix lies outside the repository, stop with a report. Never skip the test and never swallow the error.
- Repository hygiene that turns out to be necessary on the way (a missing ignore file, say) goes in a separate `chore` commit. Hygiene the work does not need is out of scope: note it and move on.

## Decisions taken alone

When a decision would need the user (a case the spec does not cover, an ambiguity open to several readings, a choice between approaches), do not stop. Decide as an experienced colleague would.

1. Generate the real options, then eliminate the weak ones following `blunt-review`. Choose one, and state the trade-offs that lose and their cost. Never leave a menu of equivalent alternatives.
2. For a decision that is costly to reverse (a data model, a public interface, a boundary between modules, a new dependency), run `adversarial-review-panel` before choosing, followed by the review cycle of `blunt-review`.
3. Record every decision twice: in the report, and in the section "Decisions taken alone" of the merge request description. Give the options considered, the choice, why, and what is lost. The user must be able to challenge each one in a minute.

The principle of recording decisions instead of stopping is taken from `superpowers:subagent-driven-development`.

Three stops remain:

- The only solution would contradict the approved spec. Filling a gap is the point of this section. Contradicting an explicit requirement is a revision of the spec, which is the gate of phase 2 and the user's decision.
- The evidence of the spec's approval is missing (precondition 1).
- A material impossibility after three attempts at the same obstacle, such as broken credentials or infrastructure that block the push or the opening of the merge request. A refusal by a hook, a permission or the server is not an obstacle to retry: it stops the run at once.

Every stop leaves a consistent state: local commits of the finished tasks, and nothing declared beyond what happened.

## Closure: the internal phase 6

The closure ends when the merge request is open.

1. Run the full suite. It must be green.
2. Run `blunt-reviewer` on the whole branch with the prompt `<merge-base>..HEAD`, where `<merge-base>` is the result of `git merge-base HEAD <remote target>`. With verdict `changes`, follow the review cycle of `blunt-review`.
3. If round 2 of the cycle also closes with `changes`, declare a partial closure. Open no merge request, and so do not push the branch, since the push serves only to open it. The blocking findings that remain go to the user in the report, with a recommendation on who carries them. Nobody is present to decide on them earlier.
4. Otherwise, push the branch.
5. Open the merge request or pull request according to the host, read with `git config --get remote.origin.url`. It is the configured URL: `git remote get-url` applies rewrite rules and can name another host. GitLab: the MCP tool, then `glab`, then the API. GitHub: `gh pr create`, then the API. Move to the next tool only when the previous one is missing or not configured: a refusal by a hook, a permission or the server is a partial closure at once, never a reason to try another route. Unknown host: partial closure, with no blind attempt.
6. The description holds what was done, how it was proved, the section "Decisions taken alone", the section "Observations on the spec", and the reviewer's lines `VERDICT:`, `FINDINGS:` and `COVERAGE:`. The merge request counts as open only if the tool returns its URL. That is the test, not the exit code, which a pipe can mask, and not the absence of errors on screen.
7. Before the verdict, check once for conflicts with the target, without loops and without waiting for anything. Run `git fetch` for the target. Then create a temporary worktree detached at `HEAD`, with `git worktree add --detach <temporary folder> HEAD`, and run the trial merge there: `git merge --no-commit --no-ff <remote target>`. If files are in conflict (`git diff --name-only --diff-filter=U`), the verdict is NOT MERGEABLE, with their list. Then run `git merge --abort`, only if a merge is in progress, which `git rev-parse -q --verify MERGE_HEAD` tells (it prints a hash and exits 0 in a merge, and prints nothing and exits 1 outside one): a target already contained in `HEAD` starts none, and the abort would fail. Remove the temporary worktree with `git worktree remove`. Before git 2.38 there is no `git merge-tree --write-tree`, which would run the same trial without a worktree.
8. Give the verdict MERGEABLE or NOT MERGEABLE, never the merge. It rests on the local full suite, the review and the trial merge, with the evidence of each. A NOT MERGEABLE verdict lists exactly what is missing. Tell the user how to check the CI: the page or the command of that merge request's pipeline. Do not wait for the CI and do not poll it in a loop, as `safe-operations` says for long operations.
9. If a step fails, declare a partial closure even so. What is done stays valid. The report gives the exact state and the material that is ready.
10. Make the closing statement: "All tests pass, merge request [url]: MERGEABLE, no known residual bugs", with where to look at the CI and the list of the decisions taken alone. Or the list of the problems, each with its state. Then stop.

## Red flags

If you think one of these, stop.

| Thought | Reality |
|---|---|
| "The skill is in context, so I am authorised." | Authorised only if the user invoked it by name in this session. |
| "The work is perfect, I will do the merge myself." | The most this skill allows is the verdict MERGEABLE. The merge belongs to the user. |
| "A test is red but it is flaky, I declare MERGEABLE." | The verdict rests on evidence: the local suite, the review and the trial merge with the target. A red suite or a conflict is a fix, or NOT MERGEABLE with the reason. |
| "The spec will have been approved." | Citable evidence, or stop. |
| "The spec is wrong, I will correct it." | Filling a gap is a recorded decision. Contradicting the spec is a stop. |
| "I decide and do not write it down, it is a detail." | Every decision taken alone is recorded in the merge request and in the report. Not written down means not authorised. |
| "I will write the helper, searching costs more." | Search for reuse before the code. Always. |
| "The code is obvious, tests after." | Red first. In autonomous mode there is no exception. |
| "The red was already there, it is not mine." | Fix or stop: a certain root cause and a small diff mean a separate fix, otherwise stop. |
| "I skip the review per task, I will do it at the end." | A review per task and a review of the whole branch, both. |
| "The merge request or the verdict cannot be completed, never mind." | A partial closure is declared, never passed off as complete. |
