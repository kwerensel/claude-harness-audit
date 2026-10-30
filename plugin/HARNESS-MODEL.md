# Three harnesses, not one

*The conceptual basis for the audit in this package. Written to be shared or adapted.*

---

## The advice that doesn't land

Most writing about agents arrives at the same instruction: **you need a harness.**

It's confusing advice, because you already have one. Several, actually. Nobody starts from
zero and adds a harness. The question was never whether you have one — it's whether the one
you have was chosen or just happened.

A harness, in Anthropic's framing, is "the software scaffolding around a model: the loop,
tools, context management, and guardrails that turn raw intelligence into a working agent."
Read that list carefully and notice that a plain Claude Code session already has every item.
So does a repo with a README and a test command. The scaffolding is not something you
introduce. It's something you inherit, and then either curate or ignore.

## Three layers, always present

**1. The built-in harness.** What the vendor ships. In Claude Code: the agentic loop,
Read/Write/Edit/Bash/Grep, permission modes, auto-compaction, plan mode, worktrees, the
bundled skills and subagents, auto memory. You did not design this and mostly cannot
change it. You *can* fail to know what's in it — which is how people end up hand-building
things that already exist.

**2. The emergent harness.** What your project accreted without anyone naming it. The fact
that `npm test` works. Directory layout that makes intent guessable. A CI config that
defines what "passing" means. A README that answers the first question a newcomer asks.
Type signatures that make a wrong edit fail loudly. Naming conventions consistent enough
to grep.

None of this was written for an agent. All of it functions as one. A repo with a fast,
comprehensive test suite has a better harness than a repo with an elaborate CLAUDE.md and
no way to check anything — and it got there by being a well-run repo, not by doing agent
work. **Good engineering practice is harness.** This is the layer the "you need a harness"
framing renders invisible, and it's usually the largest one.

**3. The intentional harness.** The part you actually author: CLAUDE.md, path-scoped rules,
skills, subagents, hooks, permission rules, sandbox config, MCP servers, saved workflows.

This is the thinnest layer, and it's the only one most discussions talk about.

## Why the distinction is practical, not semantic

Once you see three layers, the useful questions change shape.

**"What do I need to add?" becomes "which layer is this already in, and is that the right
layer?"** A rule that lives in your test suite is enforced. The same rule written in
CLAUDE.md is a suggestion. Moving it between layers is often the entire fix — and it's a
move you can't see if you only have one bucket.

**"Is my harness good?" becomes "is my harness proportionate?"** A scratch prototype with
hooks, sandboxing, and a five-agent review workflow isn't well-harnessed, it's overbuilt.
Cost is real: every always-on instruction, MCP schema, and skill description is paid for on
every turn, forever.

**"What should I add next?" gets a counterweight: what can I stop doing?** Anthropic's
harness-design post makes this the engine of the whole practice — harness design is largely
*removing* assumptions as the model gets more capable. Rules written for a weaker model
survive as cargo. Elaborate scaffolding gets outlived by the thing it was scaffolding.
Nobody deletes it, because deletion doesn't feel like progress.

## The sharpest single distinction: context vs. enforcement

If you take one operational idea from this, take this one.

CLAUDE.md is **context**. Claude reads it and tries to follow it. There is no guarantee,
especially when instructions are vague or contradict each other. It is a strong prior, not
a constraint.

Hooks, permission rules, and sandbox settings are **enforcement**. They execute at fixed
lifecycle points regardless of what Claude decides.

Almost every "Claude didn't follow my instructions" complaint is a rule sitting in the
context layer that needed to be in the enforcement layer. "Always run the linter" is a
`PostToolUse` hook. "Never commit to main" is a `PreToolUse` hook or a `permissions.deny`
rule. "Don't read `.env`" is a deny rule, not a sentence.

The audit's most useful output is the table that lists every "always / never / must" your
repo states, and names what actually holds it. Usually the answer is "nothing," and usually
that's a surprise.

## Where dynamic workflows fit

The newest layer — Claude writing its own harness per task, spawning subagents with
isolated contexts — is easy to misread as "the harness you should now be building."

It isn't. It's the layer that exists because *some* tasks don't fit one context window, and
those tasks fail in three specific, named ways when you force them to: **agentic laziness**
(declaring done at partial completion), **self-preferential bias** (trusting your own output
when you're supposed to be verifying it), and **goal drift** (losing the original objective
across rounds of summarization).

The failure modes are the reason for the machinery. If your task doesn't exhibit them, the
machinery is overhead — and Anthropic says so directly: workflows aren't needed for every
task and use significantly more tokens.

Four tests, all required, before reaching for orchestration:
1. **Independence** — subtasks don't need each other's intermediate state
2. **Volume** — enough units that serial work is genuinely slow
3. **Context pressure** — it doesn't comfortably fit in one window
4. **Verifiable output** — each subtask returns something structured you can merge and check

Migrations, per-package sweeps, multi-hypothesis debugging, triage backlogs, deep research
pass. Ordinary feature work does not. "This repo does not need workflows" is a legitimate
audit conclusion and the most common correct one.

## What this makes the audit

Not a checklist of things to install. An instrument for three questions:

1. **What's already here?** Across all three layers, including the emergent one nobody
   wrote down.
2. **Is each rule in the right layer** — context where a prior is enough, enforcement where
   it isn't, and neither where the model handles it unaided?
3. **What can come out?**

That last one is why the audit has a mandatory "Stop doing" section. A harness audit that
only ever adds is not an audit. It's a shopping list.

---

*Grounded in Anthropic's [Harnessing Claude's intelligence](https://claude.com/blog/harnessing-claudes-intelligence)
and [A harness for every task: dynamic workflows in Claude Code](https://claude.com/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code).
The three-layer model, the proportionality argument, and the context-vs-enforcement framing
are this package's own synthesis.*
