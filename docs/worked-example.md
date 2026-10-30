# Worked example: a solo developer's web app

One full cycle: audit, plan, fixes and measurement, run in autumn 2026. The
project is a personal web app with a database backend, a background worker and
a Notion integration. One developer works on it with Claude Code, and the
harness had grown over several months of phased work.

## The audit

The audit made 54 claims about the harness. Every one was checked blind against
the files, and none was wrong. The findings that mattered most were outside the
repository:

- **Sessions started one folder above the repository.** So the repository's
  deny rules did not apply, and its `CLAUDE.md` loaded late.
- **A memory note said to keep going through build phases without waiting.**
  It contradicted `CLAUDE.md`, which said requirements work waits for the
  owner's go-ahead. The note won every time.
- **The parent folder's settings held stale one-off allow rules,** including a
  broad one for arbitrary one-line scripts.

Inside the repository:
- **The newest decision record was not linked from anywhere.** Agents answered
  "what is decided now?" from an older plan.
- **Documents disagreed on scope and stack,** with nothing saying which won.
- **A rule said the app may write only to a sandbox workspace,** but nothing in
  the code enforced it.

## The plan

The owner made ten rulings: which document governs current scope, when to wait
for approval, and what the Notion integration may touch. The checklist was then
frozen before any change was made.

## The fixes

**Repository:**
- The entry file routes each key question to its one current source.
- Superseded documents are marked as superseded.
- The sandbox-only rule is enforced in code, with a test.
- One check command runs everything.
- A short `CLAUDE.md` core, with the integration rules in a path-scoped rule file.

**Outside the repository:**
- Sessions start in the repository folder.
- The memory notes are corrected and copied to the repository's memory folder.
- The parent folder's allow rules are trimmed.

## What the measurement showed

These figures come from several rounds of before-and-after runs, the largest
being 108 runs graded blind.

| Question | Before | After |
|---|---|---|
| "What is currently decided?" correct | 0 of 9 | 2 of 3 |
| Waits for approval on requirements work | 0 of 6 | 6 of 6 |
| Correctness on plain questions and build tasks | already high | held |
| Reading per correct answer | | no real change |

The correctness gains came from sources that disagreed being reduced to one
current source. Efficiency did not move. Agents found the right file at once,
then kept reading. A generated index and per-document status lines were both
tried and dropped.

## What to take from it

- Look outside the repository first: the launch folder, memory and parent
  settings.
- Fix conflicting sources before anything else.
- Do not expect document changes to cut reading costs.
