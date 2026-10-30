# Report template

Write the report as `audit.md` in the run folder. Follow this order. Omit a
section only where the template says it may be omitted, and say so in one line.

Write for the owner, who knows the project and did not watch the audit. Plain
sentences. Lead each section with its conclusion.

```markdown
# Harness audit: <project>

**Commit** `<sha>` on `<branch>` · **Date** <date> · **Uncommitted** <clean, or what>
**Scopes read** checkout, machine  (or: checkout only, and why)
**Daily models** <as stated by the owner>
**Run folder** <path>

## Verdict

<Three sentences at most. What kind of harness this is, the one thing most
worth doing, and what to leave alone.>

## What this repository is

<Two or three sentences: who works on it, what it touches, who reviews the
agent's work. Every judgment below is made against this.>

## Harness map

![Harness map](harness-map.svg)

<One sentence: the shape the picture shows, for example "Almost everything has
to be found; nothing guards the Notion write path.">

The picture is the map; the table under it is its text, for readers who cannot
see the image. Design becomes one question per rule: should it be loaded at
launch, found when needed, or enforced?

| Piece | Location | Before | After |
|---|---|---|---|
| <one line per piece> | <path, settings key, or connector name> | <loaded at launch \| found when needed \| enforced \| does not reach> | <only when a plan exists> |

<Values are defined in "The harness map" in lenses.md. Leave out the After
column when no plan exists.>

## The nine lenses

| Lens | Provided by Claude Code itself | Already provided here | Missing or weak | Worth improving now? | Status |
|---|---|---|---|---|---|
| L1 Instructions | | | | | |
| L2 Documents and routing | | | | | |
| L3 Capabilities | | | | | |
| L4 Checks and completion | | | | | |
| L5 Repo-level enforcement | | | | | |
| L6 Agent-level enforcement | | | | | |
| L7 Context economy | | | | | |
| L8 Orchestration fit | | | | | |
| L9 Continuity and maintenance | | | | | |

## What is working (leave alone)

<Named strengths with evidence. An audit that lists only gaps misdescribes
the repository.>

## Rules and what holds them

Scorecard question 4: is anything deterministic left to prose?

| Rule | Stated at | Held by | Class | Deterministic? | Should be held by |
|---|---|---|---|---|---|

Class is one of: **automation** (a test, CI job or script fails), **agent
control** (a permission rule or hook blocks it), **code shape** (true today
only because of how the code is written), **nothing** (prose only),
**judgment** (prose is the right home for it).

A rule is deterministic when its truth can be computed or checked without
judgment: a count, a list, a path, a command, a format, a version, a
forbidden action. Every deterministic rule held by **nothing** or **code
shape** gets a "Should be held by" (a script, a generated file, a test, a CI
step, a permission rule or a hook) and becomes a finding. Facts the prose
states that code could compute (a migration count, a list of commands, a
status repeated in several files) count too: generate them or stop stating
them.

## Documents

<The document table from document-review.md, then the drift checks that found
something. Then the task routing table if routing is a finding.>

## Findings

Ranked by severity, then effort. One block each:

### F1. <title>
**Severity** <critical|high|medium|low> · **Effort** <S|M|L> · **Lens** <L#> · **Scope** <checkout|machine|both> · **Evidence** <observed|executed|historical, list each that applies>

**What was found.** <With `path:line` for each claim.>
**Why it matters.** <The consequence here, not in general.>
**Fix.** <The exact change: a config block, a diff, or the wording.>
**Expected difference.** <What a session does differently afterwards.>
**How to verify.** <A check the owner can run. For a guard: attempt the
forbidden action once and confirm it is refused.>
**Tradeoff.** <What it costs or what could be lost.>
**Model-specific?** <yes or no, and why. If yes, which of the daily models it
is likely to matter for.>
**Needs your ruling.** <Only if the fix depends on a decision that is the
owner's. State the options.>
**Verification.** <confirmed | corrected: what changed | not verified: why>

## What can come out

| Item | Evidence | Why it no longer earns its cost |
|---|---|---|

<If empty, say what was checked.>

## Deliberately not recommended

<Things a checklist would add and this repository does not need, with the
reason. Include the orchestration answer from L8.>

## Seen in passing (not harness)

<Application bugs or code observations noticed on the way. Inspection only.
They do not go into the harness plan.>

## Retrieval

<One line if no candidate. Otherwise the table from retrieval.md.>

## Scorecard

The eight design questions in `scorecard.md`, always all eight, in this order.
Correctness comes first. An unimplemented recommendation has no measured after:
write "proposed".

| # | Question | Before | After | Measured how | What you would notice |
|---|---|---|---|---|---|
| 1 | What is always loaded? | | | | |
| 2 | Can the agent navigate? | | | | |
| 3 | One current answer per question? | | | | |
| 4 | Anything deterministic left to prose? | | | | |
| 5 | Can the agent check its own work? | | | | |
| 6 | Do the guards hold? | | | | |
| 7 | Does memory and state help? | | | | |
| 8 | Fits the daily models and budget? (tool calls per correct answer) | | | | |

## Proposed benchmark tasks

<Two or three, from benchmark-tasks.md, each naming the finding it is aimed
at. Name the daily models they should run on, one comparison per model. Then
the note on what a benchmark cannot show.>

## Verification scope

- **Executed:** <commands run and outcomes, or none>
- **Inspected only:** <checks read and not run>
- **Historical:** <claims taken from documents or notes, not re-verified>
- **Unknown:** <what could not be seen and what would resolve it>
- **Machine scope:** <what was read under it, or that it was off>
- **Findings re-checked:** <which findings and fix blocks went through the
  verification pass, and the result>
- **Claims of absence or adequacy sampled:** <which "no conflicts", "clean",
  "proportionate" or "not needed" statements were checked, and the result>

## Next step

<One line naming the next command.>
```

## findings.json

Write alongside the report, so the plan step does not have to parse prose:

```json
{
  "commit": "<full sha>",
  "scopes": ["checkout", "machine"],
  "daily_models": ["as stated by the owner"],
  "harness_map": [{"piece": "", "location": "", "note": "<= 22 characters", "before": "loaded at launch"}],
  "findings": [
    {"id": "F1", "title": "", "severity": "high", "effort": "S", "lens": "L6",
     "scope": "machine", "kind": "harness", "evidence": "path:line; path:line",
     "fix": "one-line description of the change", "verify": "how to check it",
     "needs_ruling": false, "ruling_question": "", "verification": "confirmed",
     "model_specific": false, "model_specific_why": "a deny rule holds for any model"}
  ],
  "leave_alone": [{"id": "N1", "title": "", "reason": ""}],
  "remove": [{"id": "R1", "title": "", "evidence": ""}],
  "seen_in_passing": [{"title": "", "evidence": ""}],
  "benchmark_tasks": []
}
```

`kind` is `harness`, `code` or `mixed`. Use `code` or `mixed` only when the fix
changes application code, such as adding a test that guards a rule.
