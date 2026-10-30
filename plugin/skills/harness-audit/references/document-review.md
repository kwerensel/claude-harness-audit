# Document review and routing

This step always runs. In the first trial it produced the single most useful
finding: four sources giving four different answers about what phase the
project was in, with the newest decisions in files nothing pointed to.

Shorter is not automatically better. The question is whether a session ends up
with the right, current picture, not how many words it read.

**Run this review in its own context.** The first run of the merged audit did
it alongside eight other lenses and went shallow: it skimmed five documents,
missed half of the drift a document-only audit had found, and called a
document clean that it had not read. The audit therefore hands this file to
the `document-reviewer` subagent, whose only job is the steps below.

## 1. Pick representative tasks

Choose two or three tasks this repository really gets: a small code change in
its riskiest area, a "what should I work on next" question, a change that
touches an external system. Use them for everything below.

## 2. Review each implicated document

Review the entry instructions, handoffs, and every document a session is told
to read or would open for those tasks. Use the inventory's document list,
including untracked files. For each one record:

| Document | Purpose and authority | Tasks that need it | Current or historical | Conflicts and overlap | Full read needed? | Decision |

Decisions: **keep**, **route to a section**, **split current from history**,
**consolidate**, **retire**. Give the tradeoff: what could be lost.

In any repository, review in full the documents the tasks touch, skim the rest
by heading, and state which were read in full, which were skimmed and which
were not opened. Do not inventory every file mechanically.

## 3. Checks that find drift

Run each of these. They are cheap and they found real problems.

- **Which source is newest?** Find the most recently written description of
  current state. Is it tracked? Does the entry file point to it? If two sources
  disagree, does anything say which wins?
- **Is anything untracked that a session needs?** An untracked handoff does not
  exist in a fresh clone or on another machine.
- **Does an "historical" folder hold a live contract?** Look for instruction
  files that name a document as the authority while another line calls its
  folder historical.
- **Do the instructions match the code?** Work through each of these:
  - every version, framework and tool the entry file states, against the
    package files and the configuration files (database and runtime versions
    live in config, not only in package files);
  - every library the instructions name: is it declared, and is it actually
    imported anywhere?
  - stated counts (tests, migrations) against a static count;
  - every file, table, command or folder a document says exists: does it?
  - every environment variable the code reads: is it in the example file?
    Every file a config names (seed files, scripts): does it exist?
  - status or phase strings in code (health endpoints, comments) against the
    current phase.
- **Open every document the entry file names, and every draft.** A read order
  or a "draft, pending" label is a reason to open the file, not to skip it.
  Check each against the entry file's hard rules, especially which environment
  and which systems may be written to.
- **Never call a skimmed document clean.** If a document was read by heading
  only, report it as "skimmed, not checked for conflicts". Saying it has no
  conflicts is a claim, and it needs the file to have been read.
- **Memory notes against reality** (machine scope): counts, paths and states
  in the notes that are no longer true.
- **Do documents contradict each other on a rule?** Especially on what may be
  written to, and which environment is in use.
- **Are links and paths alive?** Count dead link targets in the README and the
  entry file.
- **Is wording stale?** A rule phrased for a phase that has closed reads as if
  it may have lapsed.

Cite both sides of every contradiction with `path:line`.

## 4. Task routing table

Include this table when routing is a finding. Omit it when routing is clear.

| Task | First source of truth | Check or tool that applies | Advisory or enforced? |

A route written in an instruction file is advice. It is enforced only if a
script, CI rule or hook makes it happen. Say which.

Flag a mandatory full read of broad documents for narrow work only when the
evidence shows it leads to conflicting or outdated context. Prefer clear
names, headings and task-specific pointers that keep the necessary contracts.

## 5. What not to do

- Do not recommend shortening a document because it is long.
- Do not infer token use from word counts. A word count is a footprint.
- Do not rule on a conflict that belongs to the owner. Record it as needing
  their ruling and say what the options are.
