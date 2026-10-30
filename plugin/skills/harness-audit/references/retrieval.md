# Retrieval assessment (optional module)

Load this only when the inventory or the document review shows a trigger:

- the agent-facing documents total more than roughly 100,000 words, or
- knowledge a task needs is scattered across many files with no index, or
- the document review found a question whose answer exists but uses different
  words from the question, or
- benchmark traces show agents searching or opening wrong files before they
  reach the right source, or
- the owner asks about search, embeddings or retrieval.

If none applies, write one line in the report, "No retrieval candidate: the
corpus is small and exact search works", and move on. In the first trial this
section found nothing inside the repository.

## Method

Assess retrieval separately from document size. For each observed search
problem, record:

- the question an agent needs to answer,
- the authoritative source and how often it changes,
- how the agent finds it today,
- whether a wrong or stale answer would matter.

Compare methods in this order, and stop at the first that works:

1. direct links and task-specific pointers,
2. clear file names and headings,
3. exact keyword or code search,
4. structured metadata, indexes or summaries,
5. semantic or hybrid search.

Flag a corpus as an **embedding candidate to test** only when it is large or
scattered, the vocabulary of questions differs from the source, and simpler
methods demonstrably miss or bury the right material. Exact symbols, current
configuration, small well-linked documentation and fast-changing state usually
need exact lookup instead.

## A generated index (step 4)

The plugin can write one:

```
"${CLAUDE_SKILL_DIR}/../../bin/harness-state" index --repo <repo>
```

It writes `AGENT-INDEX.md`: every command from the package files, the folder
layout, and every document with its status, size and sections. If adopted, the
instruction file points to it, and `harness-state index --check` runs in CI so
it cannot go stale.

Recommend it only when the evidence shows a **finding** problem: agents open
the wrong files or search for a long time before they reach the right source,
and steps 1 to 3 cannot fix that. A large number of documents or an unfamiliar
layout is a reason to look, not a reason to recommend.

Do not recommend it for a **reading** problem: agents reach the right source
quickly and then keep opening more files. An index speeds up finding, so it
cannot shorten reading that happens after the source is found. On the
2026-10 dashboard measurement, the right source was found at once, and then a
median of about eight more files were opened. An index there changed nothing,
and removing it lost nothing. Report reading after finding as its own finding
under context economy.

Only assess a corpus that was actually inspected. Do not propose a candidate
for material outside the audit's scope.

## If there is a candidate

Record: the corpus and a representative question, the observed gap, the simpler
alternative tried or proposed, the next method to test, freshness and citation
needs, access and privacy limits, setup and upkeep costs, and a small
evaluation of ten or so questions with known-correct sources.

Score correct-and-current source found first, then stale or irrelevant hits,
and only then calls, time or tokens.

Never index secrets or private material by default. A candidate is a
hypothesis to test, not a recommendation to build.
