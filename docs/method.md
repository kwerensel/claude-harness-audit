# The method

You can use this page without the plugin. The plugin automates it and checks
each finding before reporting it.

## The idea in one paragraph

You already have a harness. Claude Code ships one, your repository adds to it
without anyone naming it, and a thin layer on top is written on purpose. An
audit asks three things:
- What is already here?
- Is each rule held by the right mechanism: prose, a setting, a hook, a test or code?
- What can come out?

There is no single best harness. The right one fits your repository, your work
and the models you use. What carries over between repositories is the process:
audit, freeze the criteria, change, measure.

## Start with the harness map

List every piece that shapes a session, and sort each one by **when it reaches
the agent**:

| When | Examples |
|---|---|
| Loaded at launch | The root `CLAUDE.md`, always-on rules, the memory index, skill and subagent descriptions, connector tool lists |
| Found when needed | Documents, path-scoped rules, skills, handoffs |
| Enforced | Deny rules, hooks, CI, tests that guard a rule, code that refuses a forbidden action |
| Never reaches the agent | Files nothing points to, settings in a folder sessions do not start in |

The last row is usually where the surprises are.

## The checklist, highest yield first

1. **Where do sessions start, and what does that load?** Settings and memory
   are keyed to the launch folder. If sessions start in a folder *above* the
   repository, the repository's deny rules do not apply. Its `CLAUDE.md` then
   loads late, if at all.
2. **Do memory notes contradict the instruction file?** One stale note ("keep
   going without waiting") can override a rule in `CLAUDE.md` every time.
3. **Is there one current source for each key question,** and does the entry
   file route to it? Old decision records and handoffs that nothing marks as
   superseded produce confidently wrong answers.
4. **Are counts, versions and lists pointers rather than prose?** Prose copies
   of facts the code holds go stale.
5. **Are guards enforced, not just written down?** Use a deny rule, a hook, or
   a code-level allowlist with a test. Try each forbidden action once and
   confirm it is refused.
6. **Is there one check command,** named where agents will see it?
7. **Is the approval rule split by kind of work?** For example: design and
   requirements wait for the owner's go-ahead; planned code tasks inside an
   approved phase proceed.
8. **Do documents disagree,** and does anything say which one wins? Cite both
   sides by `file:line`. Leave the ruling to the owner.

## Measuring a change (optional)

Measure only if you need evidence that a change helped. Most fixes found by the
checklist can be verified directly.

- **Ask plain questions and request ordinary changes,** the way daily work does.
  Never ask the agent to "find the conflicts" or "what's missing". That makes it
  read everything on purpose, so you measure audit behaviour, not your harness.
  Conflicting guidance still shows up: a stale source leads to a wrong answer.
- **Freeze the tasks, rubrics and hidden checks before building the change.**
- **Make sure each task can fail.** Run your hidden checks against a wrong
  answer too. A task that passes both before and after means something only if
  it could have failed.
- **Grade blind,** with one grader per task across all setups.
- **Rubrics cover only what the prompt asks,** or what the change is meant to
  affect.
- **Correctness first, then tool calls per correct answer.** Every step
  re-sends the conversation, so steps drive tokens. On one project, tool calls
  and input tokens correlated at 0.92.
- **Expect ceiling effects.** On tasks the agent already gets right, a better
  harness can only show losses.
- **Measure guards directly,** never with a benchmark.

## What helped, and what did not

From one project. Treat these as hypotheses for yours.

**Fixed correctness:**
- routing the entry file to the newest decision
- correcting stale memory notes
- starting sessions in the repository folder

"What is currently decided" went from 0 of 9 correct to 2 of 3.
"Waits for approval on requirements work" went from 0 of 6 to 6 of 6.

**Did not improve efficiency:**
- a generated repository index
- status lines at the top of documents
- read-order lists

Agents found the right source quickly. The extra cost came from reading *after*
finding it: a median of about eight more files. A navigation aid cannot fix
that, so the audit now recommends an index only when traces show agents failing
to find a source.

**Cost nothing extra:** a short `CLAUDE.md` core plus path-scoped rule files,
**provided** the core keeps the one rule that answers most questions and the
routing does not tell agents to read a rule file for things already in context.
