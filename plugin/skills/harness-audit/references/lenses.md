# The nine lenses

A lens is a place to look, not a score. Every lens gets a row in the report's
main table, so nothing is skipped by accident. Each row ends with a status and
a plain answer to "worth improving now?".

## Status

| Status | Meaning |
|---|---|
| under-built | Something this repository needs is missing, stale or held by the wrong mechanism |
| proportionate | What is here fits the repository. Leave it alone |
| over-built | Something here costs more than it returns. Removal is the finding |
| not assessed | Not inspected. Say why |

There are no numbers. Numbers appear in the report only for things that were
counted or measured: file sizes, test counts, benchmark results.

## Proportion comes first

Before judging any lens, write two or three sentences on what this repository
is: who works on it, whether it touches production or live data, who reviews
the agent's work, how fast it changes. Judge every lens against that. A solo
prototype with a sandbox, hooks and a five-agent review flow is over-built. A
repository that writes to a live system with nothing but prose rules is
under-built. "Leave it alone" is a valid and common conclusion.

## The harness is more than the repository

A harness is everything that shapes a session: the commit, the folder the
session starts in (the launch folder), every settings layer, memory notes,
connectors, and the model. Machine scope exists so the audit can see the parts
outside the repository.

**Outside the repository is not a defect.** Secrets, personal working rules,
account-level connectors and shared workspace documents can all belong
outside. Judge every piece, inside or outside, by two questions:

1. **Is its location deliberate?** Someone chose to put it there, for a
   reason that still holds.
2. **Does every session get it reliably?** Every session that needs it,
   started the way sessions are actually started, receives it.

A finding is about something being accidental, unreliable or contradictory.
Never about it merely being outside the repository. A memory note that holds a
rule only one machine sees is a finding if other sessions need the rule and do
not get it. A personal preference kept in user settings on purpose is not.

### The launch folder has two valid designs

- **Launch from the repository.** The repository's `CLAUDE.md` and
  `.claude/settings.json` load at launch and are versioned with the code.
- **Launch from a workspace folder above it,** made deliberate: the workspace
  `CLAUDE.md` imports the repository's (`@<repo>/CLAUDE.md`), and the
  workspace's own settings hold what must apply, on purpose. The repository's
  `.claude/settings.json` deny rules do not apply in this design (measured;
  see `surface-map.md`, section 2), so rules that must hold go in the
  workspace settings, with paths that start `./<repo>/`.

Recommend whichever fits the owner's work, and say why. A workspace folder
that holds several repositories, or shared documents beside them, is a reason
for the second. A single repository with nothing beside it is a reason for the
first. The defect is an accidental mix: sessions start above the repository
and the repository's settings and instructions silently do not apply.

## Which model the harness serves

There are two kinds of model, answered by different people. The kit's author
recommends which model runs each step of this kit. The owner states which
models they use in this repository day to day: the **daily models**. The
harness exists to serve the daily models. Judge it against them, not against
the model running the audit.

There is no single best harness. The best one fits the repository, the work,
and the daily models. What generalizes is the process: audit, freeze the
criteria, change, measure.

## The harness map

Before any lens, list every piece of the harness, one line each, with its
location: instruction files, imports, rules, skills, subagents, settings
files, permission rules, hooks, memory notes, connectors, tests and CI that
guard a rule, and the documents the instructions route to. Sort each by when
it reaches the agent, for sessions started the way the owner starts them:

| Value | Meaning |
|---|---|
| loaded at launch | In context from the first turn: instruction files at or above the launch folder and their imports, rules without `paths:`, the memory index, skill and subagent descriptions, connector tool definitions |
| found when needed | Reaches the agent only when it reads or looks for it: a `CLAUDE.md` below the launch folder, path-scoped rules, skill bodies, memory topic files, documents an instruction points to |
| enforced | Holds whatever the agent decides: permission rules, hooks, sandbox settings, and tests or CI that fail |
| does not reach | Exists, but sessions started where they are started never get it, such as the repository's deny rules for a session started above the repository |

The report shows this as a "Before" column. When a plan exists, the plan adds
an "After" column with where each piece will be once the plan is done. Design
becomes one question per rule: should it be loaded at launch, found when
needed, or enforced? A rule that must hold every time belongs in "enforced".
Context needed on every task belongs in "loaded at launch". Everything else
can wait in "found when needed".

### What the picture shows

The harness map is a drawing, never only a table, and `harness-state map` draws
it from `harness_map` so every audit's map looks the same:

- every piece is its own box: a name and a note of at most 22 characters;
- the box sits in a zone by its value: the agent session at the centre, inside
  "loaded at launch", inside "found when needed", inside the enforced boundary,
  where the guards sit; "does not reach" sits outside the boundary;
- before and after are two panels with the same layout, so a piece that moved
  is seen in a new place; a "What moved" key lists each move, computed from the
  values, never typed;
- `note_before` and `note_after` give a piece a different note on each side.

The owner reads the shape first: a launch zone that is nearly empty, a found
zone that holds everything, a boundary with no guards. A table hides that
shape; it stays under the picture only as its text.

## The main table

Every repository already has a harness in three layers: what Claude Code ships,
what the project added without anyone naming it (tests, CI, a readable
layout), and what was written on purpose for the agent. The table keeps them
apart. One row per lens, plus status:

| Lens | Provided by Claude Code itself | Already provided by this repository or machine | Missing or weak | Worth improving now? | Status |

Column two is what the built-in harness gives for free. Column three is what
the project added, with `path:line` evidence. Combine rows only if two lenses
have nothing separate to say.

---

## L1. Instructions: what loads, when, and is it right

- Which instruction files exist, and which of them a fresh session actually
  loads. Check the launch folder (machine scope): a `CLAUDE.md` below the
  launch folder loads late, not at launch, unless an instruction file at or
  above the launch folder imports it.
- `CLAUDE.md` and `AGENTS.md` both present: which one is read.
- Are the instructions specific and checkable? "Run `npm test` before
  committing" is. "Test your changes" is not.
- Do they restate what the code already shows (directory listings, dependency
  lists)? That is cost with no return.
- Contradictions between instruction files, rules, and memory notes.
- Content that belongs elsewhere: a multi-step procedure that should be a
  skill, a subtree-only rule that should be path-scoped, closed history that
  belongs in git.

## L2. Documents and routing

Follow `document-review.md`. This lens always runs.

- For two or three representative tasks, can a new session get from the task to
  the right source of truth and the right check?
- Which documents are current, which are history, and does anything say which
  wins when they disagree?
- Where is the newest state, and does any tracked file point to it?
- Do the instructions match the code: stated versions, stack, commands, counts?

## L3. Capabilities

- Skills, subagents and commands in the repository. If none, is there a
  repeated multi-step procedure that should be one?
- For each skill: does the description say when to use it? Are side-effecting
  skills restricted to manual invocation?
- For each subagent: does its tool list fit its job? A research agent with
  write tools is a finding.
- Is anything a skill that should be a plain script?

## L4. Checks and completion

- Is there one command that shows a change works, and does an agent-facing
  document name it?
- What do the checks cover? Separate logic tests, simulated UI tests,
  real-browser checks, database integration, production build.
- Setup: are the variables and fixtures a check needs written down?
- Is "done" defined anywhere?
- For UI work: can the agent see the result running?
- Is there a review of the agent's work that does not come from the same
  context that wrote it?

## L5. Repo-level enforcement

What holds without anyone remembering, inside the repository.

- CI: what runs, on which events. Whether it is required on the remote is
  usually unknown from the checkout. Say so.
- Tests that guard a stated rule. A rule with a test is enforced.
- Rules that hold only because of how the code happens to be written. Nothing
  fails if someone adds the forbidden path. Call these "holds by code shape".
- Git hooks and pre-commit configuration.

## L6. Agent-level enforcement and boundaries

What holds without the agent remembering, around the agent.

- Permission rules: allow, ask, deny. Broad allow rules such as arbitrary
  one-line scripts. Stale one-off rules. The absence of any deny rule.
- Hooks: event, matcher, what the script does, how it exits.
- Sandbox settings.
- Secret files the agent can read with nothing stopping it.
- Credentials written inline in any agent configuration file.
- Attached connectors, checked against the repository's own never-touch rules.
  If the instructions say never write to a live system and a connector that can
  write to it is attached, what mechanically stops it?
- Irreversible actions available with no gate: force push, production deploy,
  destructive database commands, publish.
- Untrusted input: does anything read issues, comments or scraped pages while
  holding write or network tools?
- Settings scope: for a rule the project relies on that lives in a local,
  uncommitted or outside-the-repository file, apply the two questions above.
  It is a finding only if its location is accidental or a session that needs
  it does not get it.
- Launch folder: do the settings the owner believes apply actually apply to
  sessions started where they are started? The repository's deny rules do
  not apply to a session started above the repository.

When this lens notices something, it must end in a call: recommend a change, or
say plainly to leave it alone and why. Noticing without a call is not allowed.

## L7. Context economy

- What loads every session: instruction files, always-on rules, the memory
  index, skill and subagent descriptions, connector tool definitions.
- Connectors whose tools are never used but always loaded.
- Stale memory: notes naming files, counts or states that are no longer true.
- A mandated read order that makes narrow work read everything.

## L8. Orchestration fit

Follow `workflow-fit.md`, but only when the inventory shows orchestration in
use or work that is clearly fan-out shaped. Otherwise one sentence is enough.
The honest answer for most repositories is that none is needed.

## L9. Continuity and maintenance

- Handoffs: are they current, tracked, and reachable from the entry file?
- Memory notes that hold rules "for every session" but exist on one machine.
  A finding when other sessions that need the rule do not get it, or when the
  note contradicts a tracked file.
- Does the harness change when the code does? Compare last-changed dates.
- Does anything record why a rule exists? Rules with no reason never get
  removed.
- Machine-specific absolute paths in committed configuration.

---

## Severity for findings

- **Critical.** A credential in a file that is committed, synced or shared.
  An unbounded destructive path. A guardrail that reads as enforced and is
  not. A credential written inline in a private local file is high, not
  critical.
- **High.** A stated must-do or never-do rule with no enforcement where a
  mistake is costly. Instructions that do not load. No way to verify work.
- **Medium.** Conflicting or stale guidance, context waste, settings in the
  wrong scope.
- **Low.** Polish.

Effort is S, M or L.

## Model-specific findings

Each finding says whether it is **model-specific**: likely to matter for some
models and not others. A missing deny rule is not model-specific; a guard
holds whatever the model does. A long list of reminders, a step-by-step recipe
for something the model does unprompted, or a rule written after a mistake an
older model made is model-specific.

Look for instructions written for an older or weaker model than the daily
models. They are candidates for "what can come out". Say that removing them
is a hypothesis until measured on the daily models: the benchmark step tests
it.
