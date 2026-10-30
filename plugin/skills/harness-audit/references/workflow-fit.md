# Orchestration fit (optional module)

Load this for lens L8 only when the inventory shows orchestration in use
(subagents, saved workflows, scheduled runs) or the repository has work that is
clearly fan-out shaped. Otherwise one sentence in the report is enough.

Orchestration means more than one context working on a task. It costs
significantly more tokens. The honest answer for most repositories is that
none is needed, and "correctly uses none" is a proportionate result.

## Four tests, all required

1. **Independence.** Subtasks do not need each other's intermediate state.
2. **Volume.** Enough units, roughly five or more, that serial work is slow.
3. **Context pressure.** The material does not fit comfortably in one window,
   or reading it all would crowd out the work.
4. **Verifiable output.** Each subtask returns something structured that can
   be merged and checked, not prose that must be re-read to be trusted.

Fail any one and the answer is a single context. Say so.

## Three failure modes orchestration exists to fix

- **Stopping early:** declaring done on partial work.
- **Self-preference:** trusting your own output when verifying it.
- **Goal drift:** losing the original objective across rounds of summarising.

If the repository's tasks do not show these, the machinery is overhead.

## The seven shapes

| Shape | What it is |
|---|---|
| Classify and act | Categorise, then route to the right handler |
| Fan out and synthesise | Split independent work, merge structured results |
| Adversarial verification | A separate context checks output against a rubric |
| Generate and filter | Produce many candidates, test and dedupe |
| Tournament | Several attempts at one task, a judge picks |
| Loop until done | Keep going until a stop condition holds |
| Quarantine | The context that reads untrusted input holds no privileged tools |

## Work that genuinely fits

Codebase-wide migration. Per-package audit in a monorepo. Enforcing one rule
across many units. Root-cause investigation with several expensive hypotheses.
Triage of a backlog. Deep research across many long sources.

## Findings to look for

- Orchestration used for ordinary feature work.
- Fan-out where the subtasks share state. They rediscover it and disagree.
- Subagents returning long prose instead of a structured result.
- No budget on an open-ended run.
- A multi-agent task retyped every time instead of saved.
- Quarantine broken: a context that reads issues, comments or web pages while
  holding write, shell or network-write tools.
- A pattern already built by hand. Two of the seven, adversarial verification
  and quarantine, are often present in a well-designed pipeline without any
  orchestration tooling. Adding tooling would re-implement what exists.

## What to write

One clear statement: does this repository warrant more than one context, yes
or no, and which test decided it. If something is over-orchestrated, that is
an over-built finding with the same standing as a gap.
