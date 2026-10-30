"""Blind grading packets and reading measures, built from a benchmark's results folders.

Two steps after `harness-bench run`:

    harness-bench packets --out DIR --seed N RESULTS_DIR:before=A,after=B [RESULTS_DIR:after=C ...]
                          [--reading] [--answer-key FILE] [--checkout DIR] [--leak TEXT ...]
    harness-bench reading (--results DIR [DIR ...] | --packets DIR) [--sources FILE] [--stale PREFIX ...]
                          [--output FILE]

`packets` turns every run into runs/R01..Rnn with meta.json, final.txt, tool-calls.txt,
tracked.patch and new-files/, in shuffled order, with paths that reveal the setup rewritten.
The key that maps packet IDs back to setups is written beside the folder, never inside it.
With --reading, the grader also labels every file a run opened as needed or not needed.

`reading` counts, from each run's own trace, the files it opened and how much text each read
returned. With --packets it adds the graders' needed / not needed labels and totals per document.
Key sources per task come from each task's `key_sources` in the manifest, or from --sources.
"""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import random
import re
import shutil

# A "read" is a Read call, or a file named in a Bash command that prints file contents.
# grep and wc are searches, not reads.
PRINTERS = re.compile(r"\b(cat|head|tail|sed|awk|less|more|nl|bat)\b")
RANGED = re.compile(r"\b(head|tail|sed -n)\b")
PATHLIKE = re.compile(r"(?:[\w.\-]+/)*[\w.\-]+\.(?:md|mdx|txt|rst|ts|tsx|js|jsx|mjs|cjs|py|rb|go|rs|java|kt|swift"
                      r"|c|h|cpp|cs|php|sh|sql|json|jsonc|ya?ml|toml|ini|cfg|env|lock|html|css|scss|vue|svelte)\b")
# The runner works in <tmp>/harness-value-<random>/ with repo/, parent/<name>/ or memory/ inside.
TEMP = r"[^\s\"']*?/harness-value-[^/\s\"']+"
INDEX = "AGENT-INDEX.md"
LEAK = r"harness-value-|/parent\b|-parent\b|machine-before|machine-after"

GRADER_INSTRUCTIONS = """\
# Blind grading instructions

Each packet in `runs/` is one benchmark run. The runs come from different setups of the same
repository. You are not told which, and must not try to find out. Do not open any file named
*KEY*, or any folder other than the ones named here.

`by-task.json` lists the packets for each task. Grade one task at a time, across all its packets,
and apply each criterion the same way to every packet.

Read:
{answer_key}- In each packet, `meta.json`: the task, the rubric, the files the run opened, the files it
  changed, and the hidden acceptance checks' results (`acceptance_stage_status`).
- `final.txt`: the agent's last message.
- `tool-calls.txt`: every tool call the run made, in order, with its time and its input
  (shortened). It shows which files were opened and what was searched or run. It does not show
  what any file or command returned: the trace records calls, not file contents. To know what a
  file says, read it in the checkout, not in the trace.
- `tracked.patch` and `new-files/`: the run's edits (coding tasks only).
{checkout}
For each packet:
1. **Criteria.** For each rubric criterion (0-based, in `meta.json` order), decide passed true or
   false, with one sentence of evidence that quotes or points at the run. Grade only what the
   criterion says, against the checkout the run had.
{files_step}
Write one JSON file per task, `reviews-<task_id>.json` in this folder, exactly:
{{"R01": {{"task_id": "...", "reviews": [{{"criterion": 0, "passed": true, "evidence": "..."}}, ...]{labels_shape}}}, ...}}

Then reply with three lines: packets passing every criterion, the criteria most often failed,
and anything odd.
"""

FILES_STEP = """\
2. **Files.** Label every path in `files_opened` as needed or not needed. Needed means the
   answer (or, for a coding task, making or checking the change correctly) actually depended
   on it. Give a short reason for each needed file. Paths under `memory/` may be skipped.
"""


def workspace_patterns(parent_names=()):
    """Regexes that map a run's temporary paths to repository-relative ones."""
    names = "|".join(re.escape(n) for n in sorted(set(parent_names), key=len, reverse=True))
    repo = rf"{TEMP}/(?:repo|parent/(?:{names}))(?=/|\b)" if names else rf"{TEMP}/repo(?=/|\b)"
    return re.compile(repo), re.compile(rf"{TEMP}/parent(?=/|\b)"), re.compile(rf"{TEMP}/memory(?=/|\b)")


def norm(path, patterns=None):
    """A repository-relative path, `../<file>` for a workspace-folder file, `memory/<note>` for memory.

    Only a leading `./` is removed: `.claude/rules/x.md` keeps its dot.
    """
    repo, parent, memory = patterns or workspace_patterns()
    if memory.match(path):
        return "memory/" + memory.sub("", path, count=1).lstrip("/")
    if repo.match(path):
        path = repo.sub("", path, count=1).lstrip("/")
    elif parent.match(path):
        return "../" + parent.sub("", path, count=1).lstrip("/")
    while path.startswith("./"):
        path = path[2:]
    return path


def text_len(content):
    if isinstance(content, str):
        return len(content)
    return sum(len(b.get("text", "")) for b in content or [] if isinstance(b, dict))


def tool_calls(events):
    """[(call number, seconds, tool_use block)] in trace order."""
    out = []
    for entry in events:
        event = entry["event"]
        if event.get("type") != "assistant":
            continue
        for block in (event.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                out.append((len(out) + 1, entry["elapsed_seconds"], block))
    return out


def reads(events, patterns=None):
    """[(call number, seconds, file, characters returned, ranged)] for every file opened, in order.

    A Bash command that prints several files splits its output evenly between them. Re-reads of the
    agent's own spilled tool output (/tool-results/) are not repository reads.
    """
    returned = {}
    for entry in events:
        event = entry["event"]
        if event.get("type") != "user":
            continue
        for block in (event.get("message") or {}).get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_result":
                returned[block.get("tool_use_id")] = text_len(block.get("content"))
    out = []
    for n, seconds, block in tool_calls(events):
        given = block.get("input") or {}
        if block.get("name") == "Read" and given.get("file_path"):
            if "/tool-results/" in given["file_path"]:
                continue
            files = [norm(given["file_path"], patterns)]
            ranged = bool(given.get("offset") or given.get("limit"))
        elif block.get("name") == "Bash" and PRINTERS.search(given.get("command", "")):
            files = sorted({norm(p, patterns) for p in PATHLIKE.findall(given["command"])})
            ranged = bool(RANGED.search(given["command"]))
        else:
            continue
        size = returned.get(block.get("id"), 0) / len(files) if files else 0
        out += [(n, seconds, f, size, ranged) for f in files]
    return out


def score(events, key_sources=(), stale_prefixes=(), patterns=None):
    """Mechanical reading counts for one run. Needed or not is the grader's label, not this."""
    key_sources = set(key_sources)
    rs = reads(events, patterns)
    files = list(dict.fromkeys(f for _, _, f, _, _ in rs))
    repo_files = [f for f in files if not f.startswith("memory/")]
    stale = [f for f in repo_files if f.startswith(tuple(stale_prefixes)) and f not in key_sources] \
        if stale_prefixes else []
    first = next(((n, s) for n, s, f, _, _ in rs if f in key_sources and f != INDEX), None)
    return {"files_opened": len(repo_files), "stale": len(stale),
            "memory_notes_opened": len(files) - len(repo_files),
            "calls_to_first_key_source": first[0] if first else None,
            "seconds_to_first_key_source": round(first[1]) if first else None,
            "opened_index": INDEX in files, "opened": files}


def load_results(folder):
    """The runner's results.json and its copy of the manifest."""
    folder = Path(folder).expanduser().resolve()
    data = json.loads((folder / "results.json").read_text())
    manifest = json.loads((folder / "manifest.json").read_text())
    return folder, data, manifest


def parent_names(manifest):
    return [spec["parent_name"] for spec in (manifest.get("launch") or {}).values() if spec.get("parent_name")]


def key_sources(manifest, extra=None):
    """Key sources per task: the manifest's `key_sources`, then a sources file's, which win.

    A sources file maps task IDs to lists of paths. Keys starting with `_` are notes and are skipped.
    """
    sources = {t["id"]: t["key_sources"] for t in manifest.get("tasks", []) if "key_sources" in t}
    sources.update({k: v for k, v in (extra or {}).items() if not k.startswith("_")})
    return sources


def events_of(folder, run):
    path = Path(folder) / run["artifacts"] / "agent" / "events.json"
    return json.loads(path.read_text()) if path.is_file() else []


def build_packets(out, seed, sets, reading=False, answer_key=None, checkout=None, leaks=()):
    """Write blind packets. `sets` is [(results folder, {side: arm label})]. Returns (count, leaked files)."""
    out = Path(out).expanduser()
    if out.exists():
        raise ValueError(f"{out} exists; choose a new folder")
    runs, names, leak_terms = [], set(), set(leaks)
    for folder, arms in sets:
        folder, data, manifest = load_results(folder)
        names.update(parent_names(manifest))
        leak_terms.add(folder.name)
        for spec in (manifest.get("launch") or {}).values():
            if spec.get("memory"):
                memory_folder = Path(spec["memory"])
                # A folder named plain "memory" says nothing; the folder holding it may (machine-before).
                leak_terms.add(memory_folder.name if memory_folder.name != "memory" else memory_folder.parent.name)
        tasks = {t["id"]: t for t in manifest["tasks"]}
        runs += [(folder, arms[r["side"]], r, tasks[r["task_id"]]) for r in data["runs"] if r["side"] in arms]
    patterns = workspace_patterns(names)
    repo, parent, memory = patterns
    session = re.compile(r"-?[A-Za-z0-9_-]*?harness-value-[A-Za-z0-9_-]*?-(?:parent|repo)\b")
    bare = re.compile(TEMP + r"[^\s\"';&|]*")

    def clean(text):
        text = memory.sub("<memory-dir>", text)
        text = repo.sub("<repo>", text)
        text = parent.sub("<workspace>", text)
        text = session.sub("<session-dir>", text)
        return bare.sub("<run-dir>", text)

    random.Random(seed).shuffle(runs)
    key, by_task = {}, defaultdict(list)
    for i, (folder, arm, run, task) in enumerate(runs, 1):
        rid = f"R{i:02d}"
        key[rid] = {"results": str(folder), "run": run["id"], "arm": arm}
        by_task[run["task_id"]].append(rid)
        src, dst = folder / run["artifacts"], out / "runs" / rid
        dst.mkdir(parents=True)
        for name in ("final.txt", "tracked.patch"):
            text = (src / name).read_text() if (src / name).is_file() else ""
            (dst / name).write_text(clean(text))
        if (src / "new-files").exists():
            shutil.copytree(src / "new-files", dst / "new-files")
        events = events_of(folder, run)
        lines = [f"t={s}s call #{n} {b.get('name')}: {json.dumps(b.get('input'))[:400]}"
                 for n, s, b in tool_calls(events)]
        (dst / "tool-calls.txt").write_text(clean("\n".join(lines)) + "\n")
        # Every opened file is listed, whatever the task: no key-source list is needed for this.
        opened = list(dict.fromkeys(f for _, _, f, _, _ in reads(events, patterns)))
        meta = {"run": rid, "task_id": run["task_id"], "commit": run["revision"], "rubric": run["rubric"],
                "discovery_milestone": task.get("discovery_milestone"), "changed_files": run.get("changed_files", []),
                "edits_within_allowed_files": run.get("scope_ok"), "files_opened": [clean(f) for f in opened],
                "acceptance_stage_status": [f"{c['status']} exit {c.get('exit_code')}" for c in run.get("checks", [])]}
        (dst / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    (out / "by-task.json").write_text(json.dumps(dict(sorted(by_task.items())), indent=2) + "\n")
    (out / "GRADER-INSTRUCTIONS.md").write_text(GRADER_INSTRUCTIONS.format(
        answer_key=f"- `{answer_key}`: your task's section of the answer key.\n" if answer_key else "",
        checkout=(f"\nIf you must confirm a fact about the repository, read it, read-only, in `{checkout}`. Instruction\n"
                  "files may differ between setups, so for what a run's own instructions said, use the paths\n"
                  "and lines the run cites.\n") if checkout else "",
        files_step=FILES_STEP if reading else "",
        labels_shape=', "needed": ["path", ...], "needed_reasons": {"path": "..."}, "not_needed": ["path", ...]'
        if reading else ""))
    (out.parent / (out.name + "-KEY.json")).write_text(json.dumps(key, indent=2) + "\n")
    # Folder names and extra terms count as whole tokens; very short ones would match everywhere.
    terms = [rf"(?<![\w.-]){re.escape(t)}(?![\w-])" for t in sorted(leak_terms) if len(t) >= 3]
    pattern = re.compile("|".join([LEAK, *terms]))
    leaked = sorted(str(p.relative_to(out)) for p in out.rglob("*")
                    if p.is_file() and pattern.search(p.read_text(errors="replace")))
    return len(runs), leaked


def labels(items):
    """Graders list files as strings or as {"file": ..., "reason": ...}."""
    return {i["file"] if isinstance(i, dict) else i for i in items or []}


def correct(review, rubric):
    """True when every criterion has a passing review, False when any failed, else None."""
    given = {r.get("criterion"): r.get("passed") for r in review.get("reviews", [])}
    if any(v is False for v in given.values()):
        return False
    return True if all(given.get(i) is True for i in range(len(rubric))) else None


def reading(results=(), packets=None, sources=None, stale_prefixes=()):
    """Per-run reading counts and per-document totals. With packets, the graders' labels are applied."""
    items, loaded = [], {}

    def load(folder):
        if folder not in loaded:
            loaded[folder] = load_results(folder)
        return loaded[folder]

    if packets:
        packets = Path(packets).expanduser()
        key = json.loads((packets.parent / (packets.name + "-KEY.json")).read_text())
        reviews = {}
        for f in sorted(packets.glob("reviews-*.json")):
            reviews.update(json.loads(f.read_text()))
        for rid, k in key.items():
            # Keys name results folders by absolute path, or (older keys) relative to the key's folder.
            folder, data, manifest = load(packets.parent / Path(k["results"]).expanduser())
            run = next(r for r in data["runs"] if r["id"] == k["run"])
            items.append((rid, k["arm"], folder, run, manifest, reviews.get(rid)))
    else:
        for folder in results:
            folder, data, manifest = load(folder)
            items += [(run["id"], run["side"], folder, run, manifest, None)
                      for run in data["runs"] if run["status"] == "completed"]
    docs = defaultdict(lambda: defaultdict(float))
    doc_tasks = defaultdict(set)
    runs = []
    for rid, arm, folder, run, manifest, review in items:
        patterns = workspace_patterns(parent_names(manifest))
        events = events_of(folder, run)
        task = run["task_id"]
        row = {"id": rid, "results": folder.name, "run": run["id"], "task": task, "arm": arm,
               **score(events, key_sources(manifest, sources).get(task, ()), stale_prefixes, patterns)}
        needed = labels((review or {}).get("needed"))
        not_needed = labels((review or {}).get("not_needed"))
        if review is not None:
            row["correct"] = correct(review, run["rubric"])
        rs = [r for r in reads(events, patterns) if not r[2].startswith("memory/")]
        first_needed = next((n for n, _, f, _, _ in rs if f in needed), None)
        tot = {"chars_needed": 0.0, "chars_not_needed": 0.0, "chars_unlabelled": 0.0,
               "chars_not_needed_after_first_needed": 0.0}
        seen = set()
        for n, _, f, size, ranged in rs:
            label = "needed" if f in needed else "not_needed" if f in not_needed else "unlabelled"
            tot["chars_" + label] += size
            if label == "not_needed" and first_needed and n > first_needed:
                tot["chars_not_needed_after_first_needed"] += size
            d = docs[f]
            d["chars_" + label] += size
            d["reads"] += 1
            d["full_reads"] += not ranged
            if f not in seen:
                seen.add(f)
                d["runs_opened"] += 1
                d["runs_" + label] += 1
                doc_tasks[f].add(task)
        runs.append({**row, **{k: round(v) for k, v in tot.items()}})
    documents = {f: {**{k: round(v) for k, v in sorted(d.items())}, "tasks": sorted(doc_tasks[f])}
                 for f, d in sorted(docs.items(), key=lambda kv: -sum(v for k, v in kv[1].items()
                                                                      if k.startswith("chars_")))}
    totals = {"runs": len(runs),
              "chars_read": sum(r["chars_needed"] + r["chars_not_needed"] + r["chars_unlabelled"] for r in runs),
              "chars_not_needed": sum(r["chars_not_needed"] for r in runs),
              "chars_not_needed_after_first_needed": sum(r["chars_not_needed_after_first_needed"] for r in runs),
              "labelled": bool(packets)}
    return {"runs": runs, "documents": documents, "totals": totals}
