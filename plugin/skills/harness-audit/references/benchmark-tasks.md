# Drafting benchmark tasks

The audit proposes tasks. It never runs them. Running is a separate step that
uses real usage and needs the owner's go-ahead.

A recommendation is a hypothesis until a matched before-and-after run supports
it. The first measurement in this project's history showed an audit's own
recommendation raising the cost of a coding task. That is why tasks are drafted
here, while the evidence is fresh, and frozen before anything is implemented.

## Draft two or three tasks

- **Find the working context.** For a real upcoming task, find the right
  implementation, the constraints that govern it, and the checks that apply.
- **A small change.** A representative change with an acceptance check the
  agent never sees.
- **Continuity,** when the repository relies on handoffs. A plain question a
  real session would ask, whose correct answer depends on the newest decision
  (for example, "what is in scope for the next phase?").

Write every task the way daily work is asked: a plain question or a change
request. Never ask the agent to find conflicts, gaps or what is missing. Those
prompts make the agent read everything on purpose, so they measure audit
behaviour, not the harness, and they overstate wasted reading (about 62% of
reading was unneeded on such tasks in the 2026-10 dashboard measurement,
against 16% on a plain lookup). Conflicting guidance is still the audit's
business: the document review finds it (`document-review.md`), and a task
catches it when a stale source leads to a wrong answer.

## Rules

- **Aim at least one task at a confirmed finding,** and say which in a `gap`
  field. At least one task must be able to fail on the "before" side. A pass
  on both sides means something only if the task could have failed: then it
  shows the harness was already strong for that task. A task that cannot
  fail shows nothing, and leaves only resource use to compare, where one run
  is noise.
- **Aim tasks at machine-level findings too,** not only repository findings.
  A stale memory note, a launch folder whose settings do not apply, or a
  parent-folder rule can each be tested: the benchmark can start a session
  from a recreated launch folder with given settings and memory notes. Use
  the copies in `machine-before/` for the "before".
- **Name the daily models** the tasks should run on. Each model gets its own
  comparison.
- Tailor tasks to this repository's actual work. Do not reuse examples.
- Fix the success criteria now. Do not reveal file locations in the prompt.
- Define the discovery milestone in advance: exactly which implementation,
  contract and check must be found.
- Coding tasks need an acceptance command kept outside the snapshot, testing
  the new behaviour and the behaviour that must be preserved. The audit only
  describes what that check must assert. The benchmark step writes and
  validates the script, so leave `acceptance` empty in the draft.
- Add a rubric for what commands cannot establish: asked before acting where
  the rules require it, kept the change minimal, cited the governing rule.
- Every rubric criterion covers either something the prompt asks for or
  something the harness change is meant to change. A criterion outside both
  grades the agent on a question it was never asked, and its result says
  nothing about the harness.
- Stale or superseded sources cited as current count against the answer.

## What a benchmark cannot show

Say this in the report next to the tasks.

- It cannot show the value of a guard. A deny rule or a blocking hook matters
  on the rare bad day. A normal task will show it as zero benefit or as cost.
  Check guards directly instead: attempt the forbidden action once in a
  session and confirm it is refused.
- One run per side is preliminary. Cache state is not controlled.
- Lower tokens or time count only alongside correct outcomes. More context or
  more checking can be worth its cost.

## Shape

Draft each task in the manifest's shape so the benchmark step can use it
without rewriting:

```json
{
  "id": "lowercase-slug",
  "kind": "orientation",
  "scenario": "fresh",
  "gap": "F4: no allowlist on the only write path",
  "prompt": "What the agent is asked, with no answer locations",
  "rubric": ["One checkable criterion per line"],
  "discovery_milestone": "Exactly what must be found for discovery to count",
  "acceptance": [],
  "allowed_edit_paths": []
}
```

`kind` is `orientation` or `coding`. `scenario` is `fresh` or `continuity`; a
continuity task also needs identical `handoff` text for both sides.
