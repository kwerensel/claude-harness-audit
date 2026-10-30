---
name: harness-benchmark
description: Compare the same tasks on two harness states of a repository, before and after harness changes, using headless Claude Code in disposable snapshots, and report correctness first and resource use second. Use after implementing a frozen harness plan, when asked to measure, benchmark or compare harness changes.
argument-hint: "[--run <run-folder>] [--before <commit>] [--after <commit>] [--path <repo>]"
disable-model-invocation: true
allowed-tools: "Read Grep Glob Agent Bash(*harness-state*) Bash(*harness-bench*) Bash(git log*) Bash(git status*) Bash(git rev-parse*) Bash(git diff --name-only*) Bash(git -C * log*) Bash(git -C * status*) Bash(git -C * rev-parse*) Bash(git -C * diff --name-only*) Bash(claude --version) Write(~/.harness-audit/**) Edit(~/.harness-audit/**)"
---

# Harness benchmark

Measure whether implemented harness changes help. Arguments: `$ARGUMENTS`

**Running the benchmark uses real usage on the signed-in Claude plan.** Each
task runs twice per repetition, once on each side. Always show the owner the
run count and get a clear yes before starting.

Correctness comes first. A faster wrong answer is a regression.

## Harness states, not commits

A side is a **harness state**: a commit, plus a launch setup (the folder the
session starts in and the files in it), plus the settings layers that load,
plus the memory notes. The model is fixed for the whole comparison. Every
difference between the two sides must be declared: repository files in
`harness_paths`, everything else in `launch`. An undeclared difference makes
the result impossible to attribute.

## Procedure

### 1. Check the plan has not moved

```
"${CLAUDE_SKILL_DIR}/../../bin/harness-state" latest --repo <repo>
"${CLAUDE_SKILL_DIR}/../../bin/harness-state" check --run <run-folder>
```

If the check fails, stop. The criteria changed after they were frozen. Tell the
owner and do not run.

### 2. Define the harness states and the arms

- **Before** is the real before: the audited commit (or the parent of the
  first implementation commit), launched the way the owner's sessions were,
  with the copies in `machine-before/` when the audit froze them.
- **After** is the implementation commit for the group being measured, with
  the files in `machine-after/` when the plan changed machine-level state.

Use the owner's actual implementation. Do not substitute a newly written
candidate. If testing a new idea, label it as an exploratory candidate in
`change_origin`.

Only declared harness files may differ between the two commits. If application
code changed as well, the result cannot be attributed to the harness. For a
`code` or `mixed` item, build a control: the after commit's application code
with the before commit's harness files.

To measure groups separately, run one comparison per group commit.

**Give each layer its own credit.** When repository and machine-level changes
happen together, use at least three arms:

- **A**, the real before.
- **B**, the before with only one layer changed, for example the before
  commit with the machine-level after.
- **C**, the full after.

The runner compares two sides at a time, so each pair of arms is its own
comparison and its own manifest: A against B, and A against C. Runs already
measured for an arm can be reused in a later comparison (see `sides` below).

**Run on the owner's daily models,** from the audit's report header, one
comparison per model. Never run one side on one model and the other side on
another. Each model gets its own manifest and results folder. With more than
one comparison, name each manifest and results folder after its arms and
model, for example `benchmark/manifest-a-c-<model>.json` and
`benchmark/results-a-c-<model>-1`.

### 3. Build the manifest

Start from `templates/benchmark.json` in this plugin and the tasks the audit
drafted in `findings.json`. Write `benchmark/manifest.json` in the run folder.
The template's `launch` starts both sides in a recreated workspace folder,
from the copies in `machine-before/` and `machine-after/`. Change it to match
how the owner's sessions start, or delete it when they start in the
repository and no settings or memory outside it are being compared.

- `harness_paths`: the exact repository files allowed to differ.
- `context_paths`: the instruction files whose size is reported.
- `model` and `reasoning_effort`: explicit, and the same for both sides. One
  of the daily models.
- `launch` (optional): how each side starts, under `before` and `after`.
  Leave it out and every session starts in the repository root with the
  snapshot's project settings and no memory notes. Each side's setup has:
  - `start`: `repo` starts in the repository root. `parent` starts in a
    recreated workspace folder that holds the repository snapshot as a
    subfolder.
  - `parent_name`: with `parent`, the repository's folder name inside the
    workspace. It defaults to the repository's own folder name, which is what
    `@<repo>/CLAUDE.md` imports and `./<repo>/` paths in rules expect.
  - `parent_files`: with `parent`, a map from a path in the workspace folder to
    a source file, for example
    `".claude/settings.local.json": "../machine-before/launch-folder/.claude/settings.local.json"`.
    It may not write inside the repository folder.
  - `memory`: a folder of memory notes, such as `../machine-before/memory`.
    Each run gets its own copy, and auto memory is pointed at it with the
    `autoMemoryDirectory` setting. Anything the agent writes there is kept in
    that run's `memory-after/` and never reaches the source folder.

  Relative paths are read from the manifest's folder. Every launch file is
  scanned for credential-shaped strings and refused if it holds one. Its
  checksum goes into the results. A side with a launch setup loads project
  and local settings; a side without one loads project settings only. User
  settings and connectors never load. So if one side has a launch setup, give
  the other side one too, so the only differences are the declared ones.
- A task's `sides` (optional): `["before"]` or `["after"]` runs only that
  side. Use it only to reuse runs already measured for the other side, with
  the same harness state, task, model and effort. Say in `environment_notes`
  where the reused runs are.
- A task's `closing` (optional): replaces the last sentence of the prompt,
  which is "Do not modify any files." for orientation tasks and "Make the
  requested change and report checks actually run." for coding tasks. Use it
  only when that sentence would itself give away the answer. The rest of the
  prompt's limits stay.
- A task's `key_sources` (optional): the repository files that answer it.
  The agent never sees them. `harness-bench reading` uses them to time the
  first key source a run opened. Give them only when reading is measured.
- `repetitions`: 1 is preliminary. Use 3 or more to see variation.
- Keep at least one task with a `gap` naming the finding it is aimed at.
- Each rubric criterion covers only what the prompt asks for or what the
  harness change is meant to change. Remove any other criterion before the
  run, not after.
- Acceptance commands live outside the snapshot and are never shown to the
  agent. Inspect every setup and acceptance command before running.

Tracked files are copied into each snapshot even if they hold secrets. Do not
benchmark a commit with committed credentials.

### 4. Validate and confirm

```
"${CLAUDE_SKILL_DIR}/../../bin/harness-bench" validate --manifest <run-folder>/benchmark/manifest.json
```

Show the owner: the two harness states and every declared difference
between them, the model, the tasks, the number of runs, and any warnings.
Wait for a clear yes.

### 5. Run, in batches

Claude Code stops a background command after 2 hours. A long chain of runs
can pass that, and the run in progress is lost. So run in batches of at most
100 minutes, each as its own background command:

```
"${CLAUDE_SKILL_DIR}/../../bin/harness-bench" run --manifest <run-folder>/benchmark/manifest.json --output <run-folder>/benchmark/results-1 --max-minutes 100
```

When the time is up, the runner starts no new run. The time is up once the
minutes used plus the longest run so far would pass the limit. It exits with
code 3 and says how many runs are left. Start the next batch with the same
command plus `--resume`, and repeat until it exits with 0:

```
"${CLAUDE_SKILL_DIR}/../../bin/harness-bench" run --manifest <run-folder>/benchmark/manifest.json --output <run-folder>/benchmark/results-1 --max-minutes 100 --resume
```

`--resume` runs only what `results.json` does not record yet, in the same
order. It refuses if the manifest or the `claude` version has changed since
the folder was started. A run that never finished, whether cut off,
interrupted, or failed before any tool call, is run again, and its folder is
moved to `incomplete/`. One run can take up to `timeout_seconds` beyond the
limit, plus its acceptance checks, so keep `--max-minutes` plus that under
120.

For the first batch, the output folder must not already exist. Use a new
number for a new comparison. The
runner works in disposable snapshots, loads only the snapshot's own settings
and the declared launch files and memory copy, loads no connectors, and never
touches the source checkout, the real launch folder or the real memory notes.

Check `claude --version` first. If the model in the manifest needs a newer
version, the first run fails at once and the runner stops.

### 6. Review against the fixed rubric

Grade blind when you can. Build packets that hide which side each run came
from:

```
"${CLAUDE_SKILL_DIR}/../../bin/harness-bench" packets --out <run-folder>/benchmark/grading-1 --seed <N> <run-folder>/benchmark/results-1:before=A,after=B [--answer-key <file>] [--checkout <read-only checkout>] [--reading]
```

Each further `RESULTS_DIR:side=ARM` adds another results folder, so arms from
several comparisons can be graded together. Every run becomes `runs/R01`,
`runs/R02` and so on, in shuffled order. Each holds `meta.json` (task, rubric,
files opened, files changed, check results), `final.txt`, `tool-calls.txt`,
the patch and new files. Paths that would reveal the setup are rewritten.
`GRADER-INSTRUCTIONS.md` and `by-task.json` tell each grader what to read and
what to write. The key that maps packets to arms is written beside the folder
as `grading-1-KEY.json`, never inside it. The command lists any file that
still holds text that could reveal a setup, and exits with 1 when there is
one. Fix that before grading. `--leak <text>` adds a term to look for, such as
an arm's branch name.

`tool-calls.txt` shows the calls a run made and which files it opened. It
does not show what any file returned. A grader who needs to know what a file
says reads it in the checkout.

Add `--reading` only when reading is being measured. Graders then also label
every opened file as needed or not needed. Afterwards:

```
"${CLAUDE_SKILL_DIR}/../../bin/harness-bench" reading --packets <run-folder>/benchmark/grading-1 --output <run-folder>/benchmark/reading-1.json [--sources <file>] [--stale <prefix>]
```

The output has, for each run: files opened, memory notes opened, stale files,
calls and seconds to the first key source, and characters read, split into
needed, not needed and unlabelled. For each document, it has the same totals
across runs, so a document that costs reading without paying it back stands
out. Key sources come from each task's `key_sources`, or from `--sources`, a
JSON file mapping task IDs to paths, which overrides them. `--stale _history/`
counts files under that prefix as stale unless they are key sources. Without
labels, `reading --results <results folder> ...` gives the counts only.

Whether grading is blind or not, each run ends with one review entry per
rubric criterion in its `reviews` in `results.json`. With packets, use the key
to copy each grader's reviews to the right run:

```json
{"criterion": 0, "passed": true, "evidence": "final.txt names the handler; source confirms it."}
```

Use the `finding-verifier` subagent or a fresh context for this, not the
context that implemented the change. Label the review as agent-assisted in
`environment_notes`. It is not independent human validation. Do not change a
rubric after seeing results. Missing reviews count as unverified.

Where a discovery milestone was defined, find the earliest trace event that
establishes all of it and record the time and call count.

### 7. Report and interpret

```
"${CLAUDE_SKILL_DIR}/../../bin/harness-bench" report --results <run-folder>/benchmark/results-1/results.json --output <run-folder>/benchmark/report-1.md
```

Write the interpretation into `results.json` under `interpretation`, then
regenerate. Rules for the interpretation:

- State pass counts for both sides before any resource figure.
- Keep failed and unverified runs visible.
- Report total, cached and uncached input separately. Cached input is part of
  total input.
- Lead the efficiency figures with tool calls per correct answer: steps drive
  tokens, and steps are what the harness design controls (`scorecard.md` in
  the audit skill). For retrieval tasks, also report calls and seconds until
  the run first opened the correct source, and whether it opened a stale one.
- Map each result to its row in the eight-question scorecard and update that
  row's After column, marking it measured.
- One run per side is preliminary. Cache state was not controlled. Do not
  infer cost savings or "more reasoning capacity".
- If the new design costs more, say what changed in its trace and what observed
  benefit justifies the cost. If none was observed, call the tradeoff
  unresolved.
- A recommendation can be revised or rejected after measurement. Say so when
  the evidence points that way.
- Guards are not measured here. Say which were checked directly and how.

Interpret every result with this table:

| What the benchmark shows | What it likely means | Next step |
|---|---|---|
| Before passes, after passes | The harness was already strong for that task and model, provided the task could have failed | Keep the change only if it has another value, such as a guard or easier upkeep. Otherwise remove it as dead weight |
| Both sides fail | The change did not address the real cause, or the diagnosis was wrong | Re-examine that finding. Check the task and rubric are sound |
| After is worse | The change costs more than it helps for this model | Revise or revert |
| Differences within the noise | Too few runs to tell | More repetitions before deciding, or record it as unresolved |
| The change is a guard | A benchmark cannot show it | Check it directly |

When before fails and after passes, the change helped on that task and
model: keep it. A result holds for the model it was run on. Say which model, and do not carry
it over to another.

Reply with the pass counts, the main differences, what the owner can expect in
everyday work, and what remains unmeasured.

## When to reassess

Run the audit and the comparison again:

- when the owner switches or upgrades a daily model,
- when the repository changes a lot,
- when a result was recorded as unresolved,
- and on a light schedule, such as every few months, to catch drift.
