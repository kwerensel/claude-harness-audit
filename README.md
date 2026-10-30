# Claude harness audit

A Claude Code plugin that audits the **harness** around a coding agent in your
repository, meaning everything that shapes what the agent knows and is allowed
to do. That covers:
- instruction files, documents and routing
- checks and guards
- settings, memory notes and connectors
- the folder sessions start in

It reports what is working, what is missing, and what can come out. If you want,
it can also measure whether your fixes helped.

It is read-only. It never changes your repository, and it never reads secret
values or conversation text.

## Quick start

In an interactive `claude` session:

```
/plugin marketplace add kwerensel/claude-harness-audit
/plugin install harness-audit@claude-harness-audit
```

Then, in the repository you want audited:

```
/harness-audit:harness-audit
```

To try it without installing, clone this repository and start Claude with
`claude --plugin-dir /path/to/clone/plugin`.

The audit is the only step you need. The plan and the benchmark are optional.

## What it looks at

Nine lenses. Each one gets a status: **under-built**, **proportionate**,
**over-built** or **not assessed**. There are no scores.

| Lens | What it checks |
|---|---|
| **L1 Instructions** | Which instruction files a fresh session actually loads, whether they are specific and checkable, and whether they contradict rules or memory notes |
| **L2 Documents and routing** | Whether a session can get from a task to the one current source of truth; which documents are current and which are history; whether stated versions, commands and counts match the code. Always runs |
| **L3 Capabilities** | Skills, subagents and commands: whether descriptions say when to use them, tool lists fit the job, and repeated procedures are packaged |
| **L4 Checks and completion** | Whether one command shows a change works, what the checks cover, whether "done" is defined, and whether the agent can see UI work running |
| **L5 Repo-level enforcement** | CI, tests that guard stated rules, git hooks, and rules that hold only by accident of how the code is written |
| **L6 Agent-level enforcement** | Permission rules, hooks, sandboxing, readable secrets, inline credentials, connectors that can reach systems your rules forbid, and ungated irreversible actions |
| **L7 Context economy** | What loads every session, connectors that are loaded but never used, stale memory, and read orders that make narrow work read everything |
| **L8 Orchestration fit** | Whether multi-agent or fan-out setups fit the work. Usually the answer is that none is needed |
| **L9 Continuity and maintenance** | Handoffs, memory that exists on one machine only, whether the harness keeps up with the code, and whether rules record why they exist |

**Optional retrieval lens.** It loads only when the evidence calls for it: a
large or scattered document set, questions worded differently from their
sources, or agents that struggle to find the right file. It tries simpler fixes
first: links, then names, then exact search, then a generated index, and only
then semantic search or embeddings. It recommends a method only when the
simpler ones demonstrably miss.

**Machine scope**, on by default. Much of the effective harness lives outside
the repository: the folder sessions start in, user and parent-folder settings,
memory notes and attached connectors. It reads key names, rule lists and
counts, never values. Turn it off with `--no-machine`. Use `--public` for a
report you intend to share.

## What it measures

Every report ends with eight design questions:

1. **What is always loaded?** Is it small, current and needed by most tasks?
2. **Can the agent navigate?** Does it get from a task to the right source without reading what it does not need?
3. **Is there one current answer per question?** Or do sources conflict?
4. **Is anything mechanical left to prose?** Rules a script could check belong in code, hooks or CI.
5. **Can the agent check its own work?**
6. **Do the guards hold?** Each forbidden action is tried once, to see whether it is refused.
7. **Does memory help rather than mislead?**
8. **Does it fit your daily models and budget?**

If you run the benchmark, it reports:
- **correctness first**, graded blind against a rubric and hidden checks;
- then **tool calls per correct answer**, the headline efficiency number;
- then tokens, and how much of what was read was actually needed.

## What you get

| Command | Output | Changes your repo? |
|---|---|---|
| `/harness-audit:harness-audit` | A report with a harness map (every piece sorted by when it reaches the agent), a status per lens, verified findings with `file:line` evidence, concrete fixes, and draft benchmark tasks | No |
| `/harness-audit:harness-plan` | A checklist built from the findings, with your rulings recorded and acceptance criteria frozen before work starts | No |
| `/harness-audit:harness-benchmark` | Before-and-after runs of the same tasks in disposable snapshots | No. It uses real model usage |

Results are written to `~/.harness-audit/runs/<repo>/<date>-<commit>/`.

Every critical and high finding is re-checked by a separate read-only verifier
before it reaches the report.

## Requirements

- Claude Code with plugin support.
- For the benchmark only: Python 3.11 or newer and a signed-in command-line
  `claude`. The benchmark has no other dependencies.

## Limits

- **It has been tested on one real repository,** with the measurements run on
  one model. The method is meant to carry over, but that has not yet been shown.
- **The benchmark is expensive.** One before-and-after answer took about two
  hours of runs plus grading. Most people should run the audit alone.
- **A benchmark cannot show the value of a guard.** Guards are checked directly.
- **Claude Code changes quickly.** Product facts in
  `plugin/skills/harness-audit/references/surface-map.md` carry the date they
  were last checked.

## Learn more

- [docs/method.md](docs/method.md): a checklist you can use without the
  plugin, how to measure a harness change, and what did not help.
- [docs/worked-example.md](docs/worked-example.md): one full audit, with fixes
  and measurement, on a real project.
- [plugin/HARNESS-MODEL.md](plugin/HARNESS-MODEL.md): the idea behind it.
- [plugin/README.md](plugin/README.md): the plugin in detail.

## License

MIT. See [LICENSE](LICENSE).
