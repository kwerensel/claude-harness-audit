# The scorecard: eight design questions

Every audit report ends with this scorecard, and every plan and benchmark is
judged against it. It turns the lenses into the questions an owner can act on:
what harness design changes, and how to tell whether a change helped.

## What design affects

Six outcomes. A design choice is worth making only through one of them.

| Outcome | Meaning |
|---|---|
| Correctness | The right answer, the right change |
| Safety | Nothing harmful happens, even when the agent errs |
| Efficiency | Steps, tokens and time per correct result |
| Reliability | The same result run after run |
| Owner effort | Re-briefing, corrections, interruptions |
| Upkeep | How fast the harness goes stale, and how cheaply it is kept current |

## The eight questions

| # | Question | Good looks like | Metric | Method |
|---|---|---|---|---|
| 1 | What is always loaded? | Small, current, needed by most tasks | Launch context: tokens on the first turn, and how much of it is current and relevant | Static count plus first-turn usage from a benchmark run |
| 2 | Can the agent navigate? | From a task to the right source without reading what it does not need | Read precision (useful reads / all reads); calls and tokens before the first correct source; stale sources used | Benchmark retrieval questions, traces graded blind |
| 3 | Is there one current answer per question? | No conflicting sources | Conflicting sources per key question | Static, from the document review |
| 4 | Is anything deterministic left to prose? | Mechanical rules live in code, hooks, CI or generated files; prose holds judgment | Rules by class (see "Rules and what holds them"); for each rule moved, a direct check that passes | Static inventory, then direct checks |
| 5 | Can the agent check its own work? | Named, fast, targeted, quiet checks; a stated definition of done | Right checks run; hidden-check pass rate; check output size and time per check | Benchmark coding tasks |
| 6 | Do the guards hold? | Risky actions blocked mechanically, wherever sessions start | Each forbidden action attempted once: refused or not | Direct check, never a benchmark |
| 7 | Does memory and state help, not mislead? | Notes accurate and indexed; no conflict with instructions; rules survive compaction and new sessions | Stale notes; unindexed notes; behaviour when a note conflicts; rules kept after compaction | Static review plus a conflict task |
| 8 | Does it fit the daily models and budget? | Works on each daily model, nothing written for a weaker one, steady across runs | **Tool calls per correct answer** (headline); tokens per correct answer; spread across runs | The same benchmark on each daily model, never mixed |

Why tool calls are the headline efficiency number: every step re-sends the
whole conversation, so steps drive tokens. On the 2026-10-01 dashboard runs,
tool calls and input tokens correlated at 0.92 across 75 runs, at about 41,000
input tokens per call. Steps are also what design controls: a route that sends
the agent straight to the right file, or one command for all checks, removes
steps. Wall-clock time costs tokens only through steps, or when a check runs
longer than the provider's cache window and the next step pays full price.

## Navigation aids such as a generated index

A generated repository index is one possible fix under question 2, not a
default. Whether to recommend it is decided in `retrieval.md` ("A generated
index"), from evidence of a finding problem. If an index is adopted, generate
it rather than hand-writing it: a hand-written map goes stale, and a stale map
is worse than none. Listing what exists is deterministic, so code does it
(question 4).

## Reporting rules

- Before is measured or counted from the checkout. After is "proposed" until a
  plan is implemented and measured; say which.
- A correctness change is reported first. An efficiency number counts only
  alongside correct results.
- A difference is clear only when every run of one side falls outside the
  other's whole range. Otherwise call it direction, not proof.
- Each row says what the owner would notice in daily work.
