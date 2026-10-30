---
name: harness-audit
description: Read-only audit of the support around the coding agent in this repository - instruction files, documents and routing, checks, repo-level and agent-level enforcement, connectors, memory, and where sessions are launched from. Produces an evidence-backed report with a status per lens, concrete fixes, and proposed benchmark tasks, saved outside the repository. Use when asked to audit, review or assess the harness, the Claude setup, CLAUDE.md, the .claude folder, or "how well is Claude set up here".
argument-hint: "[--models <daily models>] [--no-machine] [--public] [--lens L1..L9] [--path <repo>]"
disable-model-invocation: true
allowed-tools: "Read Grep Glob Agent Bash(bash *collect.sh*) Bash(*harness-state*) Bash(git log*) Bash(git status*) Bash(git shortlog*) Bash(git check-ignore*) Bash(git ls-files*) Bash(git rev-parse*) Bash(git -C * log*) Bash(git -C * status*) Bash(git -C * shortlog*) Bash(git -C * check-ignore*) Bash(git -C * ls-files*) Bash(git -C * rev-parse*) Bash(wc *) Bash(ls *) Write(~/.harness-audit/**) Edit(~/.harness-audit/**)"
---

# Harness audit

Audit the harness of the repository in the current folder, or the one given
with `--path`. Arguments: `$ARGUMENTS`

- `--models` names the models the owner uses here day to day. Asked for if
  missing.
- `--no-machine` reads only what is inside the repository.
- `--public` produces a report safe to share. It implies `--no-machine`.
- `--lens L6` audits one lens only.
- `--path <repo>` audits a repository other than the current folder.

**This audit changes nothing in the repository.** It writes its report to a run
folder outside the repository. Fixes are proposed in the report. The owner
applies them, or asks for that in a separate step.

## Read these first

In this skill's `references/` folder:

1. `evidence-rules.md`: what may be read and how findings may be stated. Read
   it before anything else.
2. `lenses.md`: the nine lenses and the status each one gets, the harness
   map, how to judge what lies outside the repository, and the daily models.
3. `document-review.md`: the document and routing review. Always runs.
4. `surface-map.md`: where Claude Code configuration lives and how it behaves.
   The only source for product claims.
5. `report-template.md`: the shape of the output.
6. `scorecard.md`: the eight design questions every report ends with.

Two more are loaded only when triggered: `retrieval.md` and `workflow-fit.md`.
Each states its own trigger. `benchmark-tasks.md` is read at step 8.

## Procedure

### 1. Scope and run folder

Find the repository root and get the run folder:

```
"${CLAUDE_SKILL_DIR}/../../bin/harness-state" dir --repo <repo>
```

It prints a path under `~/.harness-audit/runs/`. Everything the audit writes
goes there. Record the commit, the branch, and anything uncommitted. State
which scopes are on.

**Ask for the daily models.** Which model or models the owner uses in this
repository for everyday work. This is required. If `--models` or the
conversation does not say, ask before going on. The harness exists to serve
these models, not the model running the audit. Record them in the report's
header and in `findings.json`.

With machine scope on, step 2 also freezes the machine-level "before".

### 2. Inventory (never skip)

```
bash "${CLAUDE_SKILL_DIR}/scripts/collect.sh" [--no-machine] <repo> < /dev/null
```

Save the output as `inventory.txt` in the run folder. It is read-only, never
opens secret files, and prints key names and counts for anything outside the
repository, never values or conversation text.

With machine scope on, also list the connector tools visible in this session
(tools named `mcp__...`). No file shows these. Do not call any of them.

**Freeze the machine-level "before"** whenever machine scope is on, as soon
as the inventory shows where sessions start and which memory folder loads.
Once the owner changes a settings file or a memory note, the real "before" is
gone and cannot be measured against later. Run:

```
"${CLAUDE_SKILL_DIR}/../../bin/harness-state" machine-before --run <run-folder> --launch-folder <folder sessions start in> --memory <memory folder>
```

It copies the launch folder's `CLAUDE.md`, `CLAUDE.local.md` and
`.claude/settings*.json`, and the memory notes, into `machine-before/` in the
run folder, with checksums in `machine-before/checksums.json`. If sessions
start in the repository itself, pass the repository: its uncommitted local
files are still captured. Leave out `--memory` if no memory folder loads.

The command scans each file for credential-shaped strings first and never
copies a file that holds one. It lists that file as skipped, by path only. It
prints no file contents. The copies are for the benchmark; the audit may read
them only as far as it may read the originals. Report anything skipped: that
file cannot be part of a measured "before".

If the script will not run, do the inventory by hand from `surface-map.md` and
say so. Mark any lens you did not inspect as not assessed.

### 3. Read what the inventory points to

**Start the document review first, in its own context.** Launch the
`document-reviewer` subagent with the repository path, the inventory output,
the scopes in use, and the paths of `document-review.md` and
`evidence-rules.md`. Its result becomes the report's Documents section and
lens L2, and its drift findings become findings. Do not restate a document as
clean unless the reviewer read it in full. If subagents are unavailable, do the
document review yourself before anything else, and say it was not separate.

While it runs, read in full: every instruction file, every rule file, each
skill and subagent definition, the hooks and permission rules, hook scripts,
the CI workflow, and the package or build files.

Under machine scope, open a memory note only when its description says it holds
instructions for the agent.

### 4. Say what this repository is

Two or three sentences, before any judgment. See "Proportion comes first" in
`lenses.md`.

Then draw the harness map: every piece of the harness, one line each, with
its location, sorted by when it reaches the agent. See "The harness map" in
`lenses.md`. It goes in the report before the lens table and the findings,
and in `findings.json` as `harness_map`.

### 5. Work through the nine lenses, split into groups

One context covering every lens loses depth (the 2026-10-01 acceptance test).
So once the reads in step 3 are done, launch three `lens-reviewer` subagents in
parallel, one per group: `checks-and-code`, `agent-and-machine` and
`context-and-removal`. Give each the group name, the repository path, the
inventory output, the scopes in use, and the paths of `lenses.md`,
`evidence-rules.md` and `surface-map.md`. The cross-cutting passes in step 6
are split between them as `lens-reviewer.md` says.

Your job in this step is to merge: fill the main table from their rows, merge
duplicate findings, and resolve disagreements by opening the cited file
yourself. Every lens gets a row and a status. Lens L6 must end each thing it
notices with a call: recommend, or leave alone and why. If subagents are
unavailable, work through the lenses yourself and say the split did not happen.

### 6. Three cross-cutting passes

These produce the most useful findings. The lens reviewers run them; check
that each pass came back and fill any gap yourself.

**a. Rules and what holds them.** Take every always, never and must statement
the inventory extracted. For each, name what holds it and its class:
automation, agent control, code shape, nothing, or judgment. Then check the
repository's never-touch rules against the attached connectors and tools.

**b. Credentials and blast radius.** Inline credentials in any agent
configuration. Secret files readable with nothing stopping it. Broad
pre-approved commands. Irreversible actions with no gate.

**c. What can come out.** Rules that restate what the daily models do
anyway. Instructions written for an older or weaker model than the ones now in
use. Closed history kept in always-on files. Stale permissions. Connector
servers that nothing in the repository's work calls for. Memory that is no
longer true. Removal has the same standing as addition. Whether a model still
needs a rule is a hypothesis until measured on that model; say so.

### 7. Write the findings

One block per finding, in the template's shape. Each needs: evidence with
`path:line`, why it matters here, the exact fix, the expected difference, how
to verify it, the tradeoff, whether it is model-specific, and whether it needs
the owner's ruling.

For anything outside the repository, judge it by the two questions in
`lenses.md`: is its location deliberate, and does every session get it
reliably? Being outside the repository is not a finding.

Recommend only what the evidence supports. Keep "seen in passing" code
observations out of the findings. They go in their own section.

### 8. Draft benchmark tasks

Read `benchmark-tasks.md`. Draft two or three tasks, at least one aimed at a
confirmed finding. Name the daily models they should run on. Do not run
anything.

### 9. Verification pass

Write the report as a draft, `audit-draft.md` in the run folder. Before
writing the final report, send these to the `finding-verifier` subagent, with
the repository path, the scopes in use, the path of the draft, and the paths
of `surface-map.md` and `evidence-rules.md`, which it must read in full and
obey:

- every finding rated critical or high,
- every fix that contains literal configuration, code or a command to run.
  A fix that is only suggested wording is not included,
- every claim about how Claude Code behaves that a finding depends on,
- a sample of claims of absence or adequacy: "no conflicts", "absent",
  "clean", "proportionate", "not needed". Include every one that a finding,
  a "leave alone" call or a "proportionate" status rests on. The verifier
  picks at least three more from the draft. The
  2026-10-01 acceptance test's only false statement was of this kind: "the
  draft prompt spec has no conflicts".

Apply its verdicts. Correct what it corrects. Drop what it rejects, and say in
the verification scope that it was dropped. Mark anything it could not check
as not verified. Medium and low findings without a fix block are not
re-checked; say so. Say which claims of absence or adequacy were sampled.

If subagents are unavailable, re-open each cited file yourself for those items
and record that the check was not independent.

### 10. Write the report

Write `audit.md` and `findings.json` to the run folder, following
`report-template.md`. Then draw the harness map from `findings.json`:

```
"${CLAUDE_SKILL_DIR}/../../bin/harness-state" map --run <run folder>
```

It writes `harness-map.svg` beside `audit.md`, which the report's Harness map
section shows. Never replace the picture with the table: see "What the
picture shows" in `lenses.md`. Then reply with:

- the verdict, in three sentences at most,
- the count of findings by severity,
- anything that needs the owner's ruling,
- the run folder path,
- the next step: `/harness-audit:harness-plan`.

## Reminders

- The goal is a harness that fits the repository, not the largest one.
- Prefer a mechanism the project already has, such as a test or a script, over
  new machinery. Reach for a hook or a deny rule when a rule must hold whatever
  the agent decides.
- Report what was verified. "Not assessed" is a legitimate result. A confident
  statement about a file that was never opened is not.
