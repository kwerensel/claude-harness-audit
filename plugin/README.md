# Harness audit for Claude Code

Three commands that take a repository from "how well is the agent set up
here?" to a measured answer about whether the fixes helped.

| Command | What it does | Changes the repository? |
|---|---|---|
| `/harness-audit:harness-audit` | Reads the repository and its surroundings, reports a status per lens, concrete fixes, and proposed benchmark tasks | No |
| `/harness-audit:harness-plan` | Turns the findings into a checklist with acceptance criteria, records your rulings, and freezes it | No |
| `/harness-audit:harness-benchmark` | Runs the same tasks before and after your changes in disposable snapshots and reports correctness first | No. Uses real usage |

Everything the commands write goes to `~/.harness-audit/runs/<repo>/<date>-<commit>/`.
Each step reads the previous step's files from there, so nothing is pasted
between sessions.

## The idea

You already have a harness. Claude Code ships one, your repository adds to it
without anyone naming it, and a thin layer on top is written on purpose. The
audit asks three questions: what is already here, is each rule held by the
right mechanism, and what can come out. See `HARNESS-MODEL.md`.

It does not score. Each of nine lenses gets a status: under-built,
proportionate, over-built, or not assessed. Numbers appear only for things
that were counted or measured.

There is no single best harness. The best one fits the repository, the work,
and the model that does the work. What carries over from one repository to
the next is the process: audit, freeze the criteria, change, measure.

## A harness is more than the repository

Everything that shapes a session is part of the harness: the commit, the
folder the session starts in, every settings layer, memory notes, connectors,
and the model. The kit calls one combination of these a **harness state**, and
the benchmark compares two harness states, not two commits.

Something outside the repository is not a problem in itself. Secrets,
personal working rules and account-level connectors often belong outside. The
audit asks two questions of every piece: is its location deliberate, and does
every session get it reliably? Starting sessions in the repository and
starting them in a workspace folder above it are both valid, if the choice is
deliberate.

## Two kinds of model

- **The models that run the kit.** The kit's author recommends which model
  runs each step: audit, plan, implementation, grading.
- **Your daily models.** The models you use in this repository day to day.
  The audit asks you for them. The harness exists to serve them, so findings
  say whether they are model-specific, and the benchmark runs on them, one
  comparison per model.

## Reading a benchmark result

| What you see | What it likely means | What to do |
|---|---|---|
| Both sides pass | Your harness was already good enough for that task and model, if the task could have failed | Keep the change only if it has another value, such as a guard or easier upkeep. Otherwise take it out |
| Both sides fail | The change missed the real cause | Look at the finding again, and check the task and rubric |
| After is worse | The change costs more than it helps for this model | Revise or revert it |
| The difference is small | Too few runs to tell | Run more, or record it as unresolved |
| The change is a guard | A benchmark cannot show it | Try the forbidden action once and confirm it is refused |

Reassess when you switch or upgrade models, when the repository changes a
lot, when a result was unresolved, and now and then to catch drift.

## Two scopes

- **Checkout:** what is inside the repository folder.
- **Machine:** the folders sessions were launched from, settings outside the
  repository, memory notes, attached connectors. On by default, because for
  Claude Code much of the effective harness lives here. It reads key names,
  permission rules and counts. It never reads values, secret files or
  conversation text. Turn it off with `--no-machine`, or use `--public` for a
  report you intend to share.

## Use it

Try it without installing anything:

```bash
claude --plugin-dir /path/to/this/plugin
```

Then, inside the repository you want audited, run `/harness-audit:harness-audit`.

The benchmark step needs a signed-in command-line Claude recent enough for the
model named in the manifest, and Python 3.11 or newer. It has no other
dependencies.

## Layout

```
plugin/
├── .claude-plugin/plugin.json
├── HARNESS-MODEL.md              the three-layer argument
├── agents/finding-verifier.md    read-only checker used by the audit and benchmark
├── bin/                          launchers for the two Python tools
├── harness_bench/
│   ├── cli.py                    before/after runner (validate, run in resumable batches, report)
│   ├── grading.py                blind grading packets (packets) and files read per run and document (reading)
│   └── state.py                  run folders, the plan freeze, the machine-level copy
├── skills/
│   ├── harness-audit/            SKILL.md, references/, scripts/collect.sh
│   ├── harness-plan/
│   └── harness-benchmark/
├── templates/                    plan.json and benchmark.json starting points
└── tests/                        62 tests; run: python3 -m unittest discover -s tests
```

## Where it came from

- The lenses, the rules table, the "what can come out" pass and the concrete
  fix blocks come from the Claude package of 2026-09-09.
- The evidence labels, the document review, the routing table, the frozen
  checklist and the benchmark come from the agent-harness-audit kit. The
  runner is a port of the kit's at commit `4cc820e` and keeps its manifest and
  results formats, so either tool can read the other's results.
- Machine scope, the split between repo-level and agent-level enforcement, and
  the narrowed verification pass come from a head-to-head trial of the two
  designs on 2026-09-30.

## Limits

- The audit verifies facts. Whether a finding is worth acting on is a
  judgment, and the benchmark tests only some of them.
- A benchmark cannot show the value of a guard. Check guards directly.
- Product facts in `skills/harness-audit/references/surface-map.md` carry the
  date they were last checked. Claude Code changes quickly.
