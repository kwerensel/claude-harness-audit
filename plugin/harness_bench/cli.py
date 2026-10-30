"""Dependency-free, local before/after benchmark runner for Claude Code.

Ported from the agent-harness-audit kit (harness_value/cli.py at commit 4cc820e,
MIT licence). The manifest and results contracts are version 1 of that kit's, so
either tool can render the other's results. Only the agent adapter differs: this
one drives headless `claude -p` and reads its stream-json events.

Commands: validate, run (in batches with --max-minutes and --resume), report, and, for grading,
packets and reading (see harness_bench/grading.py).
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import statistics
import subprocess
import sys
import tarfile
import tempfile
import threading
import time

from . import grading

VERSION = 1
USAGE = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_output_tokens")
METRICS = ("input_tokens", "cached_input_tokens", "uncached_input_tokens", "output_tokens",
           "elapsed_seconds", "tool_calls")
EXTRA_USAGE = ("cache_creation_input_tokens",)
SECRET = re.compile(r"(Bearer\s+[A-Za-z0-9._~+/-]{12,}|pat[A-Za-z0-9]{14}\.[A-Za-z0-9]{20,}|sk-[A-Za-z0-9_-]{16,}"
                    r"|sbp_[A-Za-z0-9]{16,}|ntn_[A-Za-z0-9]{16,}|secret_[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}"
                    r"|github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}"
                    r"|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,})")
ORIENTATION_TOOLS = ["Read", "Grep", "Glob", "Bash(git log:*)", "Bash(git status:*)", "Bash(git diff:*)",
                     "Bash(git show:*)", "Bash(ls:*)", "Bash(wc:*)"]
CODING_TOOLS = ["Read", "Grep", "Glob", "Edit", "Write", "Bash"]


def read_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, value):
    path = Path(path)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def git(repo, *args, binary=False):
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True)
    if p.returncode:
        raise ValueError(p.stderr.decode(errors="replace").strip())
    return p.stdout if binary else p.stdout.decode().strip()


def safe_path(value):
    require(isinstance(value, str) and value, "Paths must be nonempty strings")
    p = PurePosixPath(value)
    require(not p.is_absolute() and ".." not in p.parts and ".git" not in p.parts,
            f"Expected repository-relative file path: {value}")
    return value


def command_list(value, label):
    require(isinstance(value, list), f"{label} must be a list of argv arrays")
    for command in value:
        require(isinstance(command, list) and command and
                all(isinstance(x, str) and x for x in command), f"Invalid command in {label}")


def fixture_file(value, base, label):
    """A launch fixture is copied into every run, so it must exist and hold no credential."""
    require(isinstance(value, str) and value, f"{label} must be a file path")
    source = Path(value).expanduser()
    if not source.is_absolute():
        source = base / source
    require(source.is_file() and not source.is_symlink(), f"{label} is not a regular file: {value}")
    require(not SECRET.search(source.read_text(errors="replace")), f"{label} holds a credential-shaped string: {value}")
    return str(source.resolve())


def load_launch(m, base):
    """Optional launch setup per side. Without it a side starts in the repository root with
    project settings only and an empty memory folder, exactly as in version 1 runs."""
    launch = m.get("launch")
    if launch is None:
        return
    require(isinstance(launch, dict) and launch and set(launch) <= {"before", "after"},
            "launch must map before and/or after to a launch setup")
    for side, spec in launch.items():
        label = f"launch.{side}"
        require(isinstance(spec, dict) and set(spec) <= {"start", "parent_name", "parent_files", "memory"},
                f"{label} accepts start, parent_name, parent_files and memory only")
        require(spec.get("start") in ("repo", "parent"), f"{label}.start must be repo or parent")
        files = spec.setdefault("parent_files", {})
        require(isinstance(files, dict), f"{label}.parent_files must map parent-relative paths to source files")
        if spec["start"] == "repo":
            require(not files and "parent_name" not in spec, f"{label}: parent_files and parent_name need start parent")
        else:
            spec.setdefault("parent_name", Path(m["repo"]).name)
            require(isinstance(spec["parent_name"], str) and re.fullmatch(r"[A-Za-z0-9._ -]+", spec["parent_name"])
                    and spec["parent_name"] not in (".", ".."), f"{label}.parent_name must be a plain folder name")
            for target in list(files):
                safe_path(target)
                require(PurePosixPath(target).parts[0] != spec["parent_name"],
                        f"{label}.parent_files may not write inside the repository snapshot")
                files[target] = fixture_file(files[target], base, f"{label}.parent_files[{target}]")
        memory = spec.setdefault("memory", None)
        if memory is not None:
            folder = Path(memory).expanduser()
            if not folder.is_absolute():
                folder = base / folder
            require(folder.is_dir(), f"{label}.memory is not a folder: {memory}")
            for item in sorted(folder.iterdir()):
                fixture_file(str(item), base, f"{label}.memory/{item.name}")
            spec["memory"] = str(folder.resolve())


def fixture_digest(spec):
    """Checksums of every launch fixture, so results show exactly what each side saw."""
    digest = {target: hashlib.sha256(Path(source).read_bytes()).hexdigest()
              for target, source in spec.get("parent_files", {}).items()}
    if spec.get("memory"):
        for item in sorted(Path(spec["memory"]).iterdir()):
            digest[f"memory/{item.name}"] = hashlib.sha256(item.read_bytes()).hexdigest()
    return digest


def load_manifest(path):
    m = read_json(path)
    require(m.get("schema_version") == VERSION, "Unsupported manifest schema_version")
    repo = Path(m["repo"]).expanduser()
    if not repo.is_absolute():
        repo = Path(path).resolve().parent / repo
    m["repo"] = str(repo.resolve())
    require(repo.is_dir(), "Repository does not exist")
    for side in ("before", "after"):
        m[side] = git(repo, "rev-parse", "--verify", f"{m[side]}^{{commit}}")
    paths = m.get("harness_paths", [])
    require(isinstance(paths, list) and paths, "Declare exact harness_paths being compared")
    for p in paths:
        safe_path(p)
    changed = git(repo, "diff", "--name-only", "--no-renames", m["before"], m["after"]).splitlines()
    require(not (set(changed) - set(paths)),
            "Application changes outside harness_paths: " + ", ".join(set(changed) - set(paths)))
    m["changed_paths"] = changed
    require(isinstance(m.get("change_origin"), str) and m["change_origin"].strip(),
            "change_origin must identify the actual implemented recommendation or label an exploratory candidate")
    for key in ("model", "reasoning_effort"):
        require(isinstance(m.get(key), str) and m[key], f"Explicit {key} is required")
    m.setdefault("repetitions", 1)
    m.setdefault("timeout_seconds", 900)
    require(type(m["repetitions"]) is int and m["repetitions"] > 0, "Invalid repetitions")
    require(type(m["timeout_seconds"]) is int and m["timeout_seconds"] > 0, "Invalid timeout")
    m.setdefault("setup", [])
    command_list(m["setup"], "setup")
    require(isinstance(m.get("tasks"), list) and m["tasks"], "At least one task is required")
    ids = set()
    for task in m["tasks"]:
        ident = task.get("id", "")
        require(re.fullmatch(r"[a-z0-9][a-z0-9_-]*", ident) and ident not in ids,
                "Task IDs must be unique lowercase slugs")
        ids.add(ident)
        require(task.get("kind") in ("orientation", "coding"), "Invalid task kind")
        require(task.get("scenario", "fresh") in ("fresh", "continuity"), "Invalid scenario")
        require(isinstance(task.get("prompt"), str) and task["prompt"], "Task prompt is required")
        task.setdefault("scenario", "fresh")
        task.setdefault("acceptance", [])
        task.setdefault("rubric", [])
        command_list(task["acceptance"], "acceptance")
        require(isinstance(task["rubric"], list) and all(isinstance(x, str) and x for x in task["rubric"]),
                "rubric must contain nonempty criterion strings")
        require(task["acceptance"] or task["rubric"], "Every task needs acceptance criteria")
        if task["kind"] == "coding":
            require(task["acceptance"], "Coding tasks require acceptance commands")
        if task["scenario"] == "continuity":
            require(isinstance(task.get("handoff"), str) and task["handoff"],
                    "Continuity tasks require identical handoff text for both designs")
        for p in task.get("allowed_edit_paths", []):
            safe_path(p)
        if "gap" in task:
            require(isinstance(task["gap"], str) and task["gap"].strip(),
                    "gap must name the audited finding this task is aimed at")
        if "key_sources" in task:
            # Analysis input for `harness-bench reading`: never shown to the agent.
            require(isinstance(task["key_sources"], list) and task["key_sources"],
                    "key_sources must list the repository files that answer the task")
            for p in task["key_sources"]:
                safe_path(p)
        if "discovery_milestone" in task:
            require(isinstance(task["discovery_milestone"], str) and task["discovery_milestone"].strip(),
                    "discovery_milestone must define the required evidence")
        if "closing" in task:
            # Replaces the default last sentence, for tasks where "make the change" would itself answer the question.
            require(isinstance(task["closing"], str) and task["closing"].strip(), "closing must be a nonempty sentence")
        if "sides" in task:
            require(isinstance(task["sides"], list) and task["sides"] and set(task["sides"]) <= {"before", "after"}
                    and len(set(task["sides"])) == len(task["sides"]),
                    "sides must list before and/or after; use it only to reuse runs already measured")
    m.setdefault("context_paths", paths)
    for p in m["context_paths"]:
        safe_path(p)
    load_launch(m, Path(path).resolve().parent)
    m.setdefault("environment_notes", "Uncontrolled machine load and provider caching.")
    tools = m.setdefault("claude", {})
    require(isinstance(tools, dict), "claude must be an object")
    tools.setdefault("orientation_tools", ORIENTATION_TOOLS)
    tools.setdefault("coding_tools", CODING_TOOLS)
    for key in ("orientation_tools", "coding_tools"):
        require(isinstance(tools[key], list) and tools[key] and all(isinstance(x, str) and x for x in tools[key]),
                f"claude.{key} must be a nonempty list of tool rules")
    m["warnings"] = []
    if not any("gap" in task for task in m["tasks"]):
        m["warnings"].append("No task names a gap from the audit. If every task passes on both sides, "
                             "only resource use is left to compare. Aim at least one task at a confirmed finding.")
    if m["repetitions"] == 1:
        m["warnings"].append("One repetition is preliminary. Use 3 or more to see variation.")
    return m


def footprint(m, revision):
    files = []
    for path in m["context_paths"]:
        listing = git(m["repo"], "ls-tree", revision, "--", path)
        if not listing:
            files.append({"path": path, "present": False, "bytes": 0, "words": 0})
            continue
        require(listing.split()[0] in ("100644", "100755"), "Context paths must be regular files")
        data = git(m["repo"], "show", f"{revision}:{path}", binary=True)
        files.append({"path": path, "present": True, "bytes": len(data),
                      "words": len(data.decode(errors="replace").split())})
    return {"files": files, "bytes": sum(x["bytes"] for x in files),
            "words": sum(x["words"] for x in files)}


def snapshot(repo, revision, destination):
    """Export one revision without history, remotes, ignored files or credentials."""
    tree = git(repo, "ls-tree", "-r", revision)
    require(not any(line.startswith("160000") for line in tree.splitlines()),
            "Submodules are not supported; supply a self-contained benchmark repository")
    data = git(repo, "archive", "--format=tar", revision, binary=True)
    destination.mkdir()
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for member in archive.getmembers():
            safe_path(member.name)
            require(member.isfile() or member.isdir(), "Snapshot symlinks and special files are unsupported")
            target = destination / member.name
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())
                target.chmod(member.mode & 0o777)
    git(destination, "init", "-q")
    git(destination, "add", "--force", ".")
    git(destination, "-c", "user.name=Harness benchmark", "-c", "user.email=benchmark@localhost",
        "-c", "core.hooksPath=/dev/null", "commit", "-qm", "Benchmark snapshot")


def terminate(process):
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=2)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()
    except ProcessLookupError:
        pass


def execute(argv, cwd, folder, timeout, stdin=None, events=False, env=None):
    """Keep raw logs and a timestamped event index. All timings are wall clock."""
    folder.mkdir(parents=True, exist_ok=True)
    start = time.monotonic()
    records = []
    malformed = 0
    with (folder / "stdout.txt").open("w") as stdout, (folder / "stderr.txt").open("w") as stderr, \
            tempfile.TemporaryFile(mode="w+") as input_file:
        input_file.write(stdin or "")
        input_file.seek(0)
        try:
            p = subprocess.Popen(argv, cwd=cwd, stdin=input_file, stdout=subprocess.PIPE,
                                 stderr=stderr, text=True, errors="replace", start_new_session=True, env=env)
        except OSError as exc:
            return {"status": "error", "exit_code": None, "elapsed_seconds": 0,
                    "error": str(exc), "events": [], "malformed_events": 0}
        def read_output():
            nonlocal malformed
            for line in p.stdout:
                stdout.write(line)
                stdout.flush()
                if events:
                    try:
                        event = json.loads(line)
                        if not isinstance(event, dict):
                            raise ValueError("not an object")
                        records.append({"elapsed_seconds": round(time.monotonic() - start, 3), "event": event})
                    except ValueError:
                        malformed += 1
        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        status = "completed"
        try:
            p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            status = "timeout"
            terminate(p)
        except KeyboardInterrupt:
            terminate(p)
            status = "interrupted"
        reader.join(timeout=5)
        if reader.is_alive():
            terminate(p)
            status = "error"
            reader.join(timeout=5)
        p.stdout.close()
        if p.returncode != 0 and status == "completed":
            status = "error"
    if events:
        write_json(folder / "events.json", records)
    return {"status": status, "exit_code": p.returncode,
            "elapsed_seconds": round(time.monotonic() - start, 3),
            "events": records, "malformed_events": malformed}


def summarize_events(records):
    """Read Claude Code stream-json events.

    Claude reports fresh, cache-write and cache-read input separately. The kit's
    contract wants total input with cached as a subset, so:
      input_tokens          = fresh + cache write + cache read
      cached_input_tokens   = cache read
      uncached_input_tokens = fresh + cache write
    Tool calls are unique tool_use blocks of any tool, file reads included. The
    Codex adapter counts commands, MCP calls and web searches only, so call
    counts are comparable within one adapter, not across adapters.
    """
    result = None
    tools = {}
    failed = False
    for entry in records:
        event = entry["event"]
        kind = event.get("type")
        if kind == "assistant":
            content = (event.get("message") or {}).get("content")
            for block in content if isinstance(content, list) else []:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    tools[block.get("id", f"missing-{len(tools)}")] = block.get("name", "unknown")
        elif kind == "result":
            result = event
            if event.get("is_error") or event.get("subtype", "success") != "success":
                failed = True
    usage = {k: None for k in (*USAGE, "uncached_input_tokens", *EXTRA_USAGE)}

    def count(value):
        return value if type(value) is int and value >= 0 else None

    if result:
        u = result.get("usage") or {}
        fresh, written, read = (count(u.get(k)) for k in
                                ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
        if None not in (fresh, written, read):
            usage.update({"input_tokens": fresh + written + read, "cached_input_tokens": read,
                          "uncached_input_tokens": fresh + written, "cache_creation_input_tokens": written})
        usage["output_tokens"] = count(u.get("output_tokens"))
    final = result.get("result") if result else ""
    return {"usage": usage, "tool_calls": len(tools) if records else None,
            "tool_breakdown": dict(sorted(collections.Counter(tools.values()).items())),
            "turn_completed": result is not None, "turn_failed": failed,
            "final": final if isinstance(final, str) else "",
            "num_turns": count(result.get("num_turns")) if result else None}


def expand_command(argv, workspace, artifacts):
    return [arg.replace("{workspace}", str(workspace)).replace("{artifacts}", str(artifacts))
            .replace("{final}", str(artifacts / "final.txt")) for arg in argv]


def changed_files(workspace, base="HEAD"):
    tracked = git(workspace, "diff", base, "--name-only").splitlines()
    untracked = git(workspace, "ls-files", "--others", "--exclude-standard").splitlines()
    return sorted(set(tracked + untracked))


def agent_environment(m):
    """The agent runs on the signed-in subscription unless the manifest says otherwise."""
    env = dict(os.environ)
    if not m.get("allow_api_key"):
        env.pop("ANTHROPIC_API_KEY", None)
    return env


def session_folders(start):
    """Where Claude Code keeps per-project state for a launch folder: the path with every
    non-alphanumeric character replaced by a dash, under ~/.claude/projects."""
    projects = Path.home() / ".claude" / "projects"
    return sorted({projects / re.sub(r"[^A-Za-z0-9]", "-", str(p)) for p in (start, start.resolve())})


def files_digest(folder):
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()}


def run_one(m, task, side, repeat, output, claude):
    run_id = f"{task['id']}-{side}-{repeat}"
    artifacts = output / "runs" / run_id
    artifacts.mkdir(parents=True)
    run = {"id": run_id, "task_id": task["id"], "side": side, "repeat": repeat,
           "scenario": task["scenario"], "kind": task["kind"], "revision": m[side],
           "status": "error", "usage": {k: None for k in (*USAGE, "uncached_input_tokens", *EXTRA_USAGE)},
           "tool_calls": None, "elapsed_seconds": None, "checks": [], "setup": [],
           "rubric": task["rubric"], "reviews": [], "discovery": None, "artifacts": f"runs/{run_id}"}
    run["expected_checks"] = len(task["acceptance"])
    run["discovery_milestone"] = task.get("discovery_milestone")
    launch = (m.get("launch") or {}).get(side)
    with tempfile.TemporaryDirectory(prefix="harness-value-") as temp:
        if launch and launch["start"] == "parent":
            # A recreated workspace folder holding the snapshot as a subfolder, as on the owner's machine.
            start = Path(temp) / "parent"
            start.mkdir()
            workspace = start / launch["parent_name"]
            for target, source in launch["parent_files"].items():
                (start / target).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, start / target)
        else:
            workspace = Path(temp) / "repo"
            start = workspace
        snapshot(m["repo"], m[side], workspace)
        if launch:
            # Memory is a per-run copy, so nothing the agent writes reaches the fixture or ~/.claude.
            memory = Path(temp) / "memory"
            if launch["memory"]:
                shutil.copytree(launch["memory"], memory)
            else:
                memory.mkdir()
            run["launch"] = {"start": launch["start"], "parent_files": sorted(launch["parent_files"]),
                             "memory": launch["memory"], "fixtures_sha256": fixture_digest(launch)}
            memory_before = files_digest(memory)
        for i, argv in enumerate(m["setup"]):
            check = execute(expand_command(argv, workspace, artifacts), workspace,
                            artifacts / f"setup-{i}", m["timeout_seconds"])
            check.pop("events")
            run["setup"].append(check)
            if check["status"] != "completed":
                run["status"] = "interrupted" if check["status"] == "interrupted" else "setup_failed"
                return run
        # Setup outputs form the environment, not agent edits.
        baseline_edits = changed_files(workspace)
        require(not baseline_edits, "Setup modified tracked/unignored files; use ignored build artifacts only")
        snapshot_base = git(workspace, "rev-parse", "HEAD")
        orientation = task["kind"] == "orientation"
        # Headless runs never prompt: a tool outside --allowedTools is refused, not bypassed.
        # --setting-sources project keeps the snapshot's own harness and drops user settings;
        # --strict-mcp-config with no config file means no connectors are loaded.
        # A launch setup adds local settings (the launch folder's settings.local.json) and points
        # auto memory at the per-run copy. User settings stay out on every side.
        argv = [claude, "-p", "--output-format", "stream-json", "--verbose",
                "--model", m["model"], "--effort", m["reasoning_effort"],
                "--no-session-persistence", "--strict-mcp-config",
                "--setting-sources", "project,local" if launch else "project",
                *(["--settings", json.dumps({"autoMemoryDirectory": str(memory)})] if launch else []),
                "--permission-mode", "default" if orientation else "acceptEdits", "--allowedTools",
                *(m["claude"]["orientation_tools"] if orientation else m["claude"]["coding_tools"])]
        prompt = task["prompt"]
        if task["scenario"] == "continuity":
            prompt = "Continue from this supplied handoff:\n" + task["handoff"] + "\n\n" + prompt
        prompt += "\n\nWork only in this checkout. Do not use external services or read secret files. "
        prompt += "Do not commit, push, or change Git history. "
        prompt += task.get("closing") or ("Do not modify any files." if task["kind"] == "orientation" else
                                          "Make the requested change and report checks actually run.")
        write_json(artifacts / "invocation.json", {"argv": argv, "prompt": prompt})
        leftovers = [p for p in session_folders(start) if not p.exists()] if launch else []
        try:
            result = execute(argv, start, artifacts / "agent", m["timeout_seconds"], stdin=prompt, events=True,
                             env=agent_environment(m))
        finally:
            # Anything Claude Code created for this temporary launch folder goes with the run.
            for folder in leftovers:
                if folder.exists():
                    shutil.rmtree(folder)
        if launch:
            run["memory_changed"] = files_digest(memory) != memory_before
            if run["memory_changed"]:
                shutil.copytree(memory, artifacts / "memory-after")
        summary = summarize_events(result["events"])
        run.update({k: summary[k] for k in ("usage", "tool_calls", "tool_breakdown", "num_turns")})
        run["elapsed_seconds"] = result["elapsed_seconds"]
        run["status"] = result["status"]
        run["malformed_events"] = result["malformed_events"]
        if run["status"] == "completed" and (not summary["turn_completed"] or summary["turn_failed"] or result["malformed_events"]):
            run["status"] = "error"
        (artifacts / "final.txt").write_text(summary["final"])
        run["changed_files"] = changed_files(workspace, snapshot_base)
        (artifacts / "tracked.patch").write_text(git(workspace, "diff", snapshot_base, "--binary"))
        # Preserve newly created, non-ignored files before disposing of the snapshot.
        for name in git(workspace, "ls-files", "--others", "--exclude-standard").splitlines():
            source = workspace / name
            if source.is_file() and not source.is_symlink():
                target = artifacts / "new-files" / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        allowed = task.get("allowed_edit_paths")
        run["scope_ok"] = (not run["changed_files"] if task["kind"] == "orientation" else
                           allowed is None or set(run["changed_files"]) <= set(allowed))
        if run["status"] == "completed":
            for i, argv in enumerate(task["acceptance"]):
                check = execute(expand_command(argv, workspace, artifacts), workspace,
                                artifacts / f"check-{i}", m["timeout_seconds"])
                check.pop("events")
                run["checks"].append(check)
                if check["status"] == "interrupted":
                    run["status"] = "interrupted"
                    break
    return run


def outcome(run):
    if run["status"] != "completed" or not run.get("scope_ok", True):
        return "failed"
    if any(c["status"] != "completed" for c in run["checks"]):
        return "failed"
    if len(run["checks"]) != run.get("expected_checks", len(run["checks"])):
        return "unverified"
    reviews = {r["criterion"]: r for r in run.get("reviews", [])}
    if any(r.get("passed") is False for r in reviews.values()):
        return "failed"
    if any(i not in reviews or reviews[i].get("passed") is not True or not reviews[i].get("evidence")
           for i in range(len(run["rubric"]))):
        return "unverified"
    return "passed"


def validate_results(data):
    require(data.get("schema_version") == VERSION, "Unsupported results schema_version")
    require(isinstance(data.get("runs"), list), "results.runs must be an array")
    require(type(data.get("repetitions")) is int and data["repetitions"] > 0, "Invalid repetitions")
    require(isinstance(data.get("tasks"), list) and data["tasks"], "Missing task metadata")
    tasks = {t["id"]: t for t in data["tasks"]}
    require(len(tasks) == len(data["tasks"]), "Duplicate task metadata")
    seen = set()
    criteria = {}
    for r in data["runs"]:
        key = (r["task_id"], r["side"], r["repeat"])
        require(key not in seen and r["side"] in ("before", "after"), "Duplicate/invalid run identity")
        require(r["task_id"] in tasks and type(r["repeat"]) is int and
                1 <= r["repeat"] <= data["repetitions"], "Unknown task or repetition")
        require(r.get("scenario", "fresh") == tasks[r["task_id"]].get("scenario", "fresh"),
                "Scenario mismatch")
        seen.add(key)
        require(isinstance(r["rubric"], list) and isinstance(r["checks"], list), "Missing checks or rubric")
        require(r.get("revision") == data[r["side"]], "Run revision does not match comparison")
        expected_checks = r.get("expected_checks", len(r["checks"]))
        require(type(expected_checks) is int and expected_checks >= 0, "Invalid expected_checks")
        signature = (r["rubric"], expected_checks)
        require(r["task_id"] not in criteria or criteria[r["task_id"]] == signature,
                "Correctness criteria differ between runs")
        criteria[r["task_id"]] = signature
        for k in (*USAGE, "uncached_input_tokens", *EXTRA_USAGE):
            v = r["usage"].get(k)
            require(v is None or (type(v) is int and v >= 0), f"Invalid {k}")
        for k in ("elapsed_seconds", "tool_calls"):
            v = r.get(k)
            require(v is None or (type(v) in (int, float) and math.isfinite(v) and v >= 0), f"Invalid {k}")
        raw, cached, uncached = (r["usage"].get(k) for k in
                                  ("input_tokens", "cached_input_tokens", "uncached_input_tokens"))
        if raw is not None and cached is not None:
            require(cached <= raw and (uncached is None or uncached == raw - cached),
                    "Inconsistent cached/uncached usage")
        require(r["checks"] or r["rubric"] or r["status"] != "completed", "No correctness evidence")
        require(r["status"] in ("completed", "error", "timeout", "setup_failed", "interrupted"), "Invalid run status")
        require(all(c.get("status") in ("completed", "error", "timeout", "interrupted") for c in r["checks"]), "Invalid check status")
        require(all(c["status"] != "completed" or c.get("exit_code") == 0 for c in r["checks"]),
                "Completed checks must have exit_code 0")
        reviewed = set()
        for review in r.get("reviews", []):
            index = review.get("criterion")
            require(type(index) is int and 0 <= index < len(r["rubric"]) and index not in reviewed,
                    "Invalid or duplicate review criterion")
            reviewed.add(index)
            require(type(review.get("passed")) is bool and isinstance(review.get("evidence"), str)
                    and review["evidence"].strip(), "Reviews require a boolean and evidence")
        discovery = r.get("discovery")
        if discovery is not None:
            require(isinstance(r.get("discovery_milestone"), str) and r["discovery_milestone"].strip(),
                    "Discovery measurement requires a predefined milestone")
            require(type(discovery.get("elapsed_seconds")) in (int, float) and
                    math.isfinite(discovery["elapsed_seconds"]) and discovery["elapsed_seconds"] >= 0 and
                    type(discovery.get("tool_calls")) is int and discovery["tool_calls"] >= 0 and
                    isinstance(discovery.get("evidence"), str) and discovery["evidence"].strip(),
                    "Discovery milestones require time, calls and evidence")
            require(r.get("elapsed_seconds") is not None and discovery["elapsed_seconds"] <= r["elapsed_seconds"],
                    "Discovery milestone is outside the run")
    return data


def metric(run, name):
    return run["usage"].get(name) if name.endswith("tokens") else run.get(name)


def number(value):
    return "unavailable" if value is None else f"{value:,.2f}".rstrip("0").rstrip(".")


def distribution(values):
    if not values or any(v is None for v in values):
        return "unavailable"
    text = number(statistics.median(values))
    return text if len(values) == 1 else f"{text} [{number(min(values))}–{number(max(values))}]"


def delta(before, after):
    if before is None or after is None:
        return "unavailable"
    difference = after - before
    return f"{difference:+,.2f}" + (f" ({difference / before:+.1%})" if before else " (zero baseline)")


def cell(value):
    return str(value).replace("|", "\\|").replace("\n", " ")


def render_report(data):
    validate_results(data)
    lines = ["# Harness value comparison", "", "Correctness is the primary criterion. Differences are after minus before.", "",
             "One repetition is preliminary; repeated runs show variation, not statistical proof.", "",
             "## Conditions", "", f"- Model: {cell(data['model'])}; reasoning: {cell(data['reasoning_effort'])}.",
             f"- Before: `{data['before']}`; after: `{data['after']}`.",
             f"- Change assessed: {cell(data.get('change_origin', 'Unrecorded; verify that the intended implementation was used.'))}",
             f"- Environment: {cell(data.get('environment_notes', 'Not recorded'))}",
             f"- Adapter: {cell(data.get('adapter', 'unrecorded'))} {cell(data.get('cli_version', ''))}. "
             "Tool-call counts are comparable only within one adapter.",
             ("- Cache state is observed, not controlled. Continuity uses a supplied handoff in a fresh session; it does not measure resumed-session caching."
              if any(t.get("scenario") == "continuity" for t in data["tasks"])
              else "- Cache state is observed, not controlled. All tasks use fresh sessions; a task may read the repository's own handoff, but resumed-session caching was not measured."), ""]
    for side, spec in (data.get("launch") or {}).items():
        where = "repository root" if spec["start"] == "repo" else "a workspace folder above the repository"
        extra = ", ".join(f"`{p}`" for p in spec["parent_files"]) or "none"
        memory = f"copy of `{spec['memory']}`" if spec["memory"] else "empty"
        lines.insert(lines.index("", lines.index("## Conditions") + 2), f"- Launch, {side}: {where}; workspace files {extra}; memory {memory}.")
    if data.get("footprint"):
        lines += ["## Selected instruction footprint", "", "| Measure | Before | After | Difference |", "|---|---:|---:|---:|"]
        for k in ("bytes", "words"):
            b, a = (data["footprint"][s][k] for s in ("before", "after"))
            lines.append(f"| {k} | {b} | {a} | {delta(b, a)} |")
        lines += ["", "Scope: " + ", ".join(f"`{x['path']}`" for x in data["footprint"]["after"]["files"]),
                  "File size is not runtime context size or a token-savings estimate.", ""]
    for task in data["tasks"]:
        runs = [r for r in data["runs"] if r["task_id"] == task["id"]]
        sides = {s: sorted([r for r in runs if r["side"] == s], key=lambda r: r["repeat"]) for s in ("before", "after")}
        lines += [f"## {cell(task['id'])} ({cell(task.get('scenario', 'fresh'))})", "",
                  "| Run | Correctness | Execution | Input tokens | Cached input | Uncached input | Output tokens | Seconds | Tool calls |",
                  "|---|---|---|---:|---:|---:|---:|---:|---:|"]
        for r in runs:
            lines.append("| " + " | ".join([cell(r["id"]), outcome(r), r["status"]] +
                         [number(metric(r, k)) for k in METRICS]) + " |")
        matched = [(b, a) for b in sides["before"] for a in sides["after"]
                   if b["repeat"] == a["repeat"] and outcome(b) == outcome(a) == "passed"]
        all_pass = bool(runs) and all(outcome(r) == "passed" for r in runs)
        complete = all(len(sides[s]) == data["repetitions"] for s in sides)
        lines += ["", "; ".join(f"{s}: {sum(outcome(r) == 'passed' for r in sides[s])}/{len(sides[s])} passed" for s in sides) + ".", ""]
        if matched:
            lines += ["Matched successful pairs only (median [min–max]); unsuccessful runs remain above.", "",
                      "| Measure | Before | After | Median paired difference |", "|---|---:|---:|---:|"]
            for k in METRICS:
                b = [metric(pair[0], k) for pair in matched]
                a = [metric(pair[1], k) for pair in matched]
                changes = [y - x for x, y in zip(b, a) if x is not None and y is not None]
                d = number(statistics.median(changes)) if len(changes) == len(matched) else "unavailable"
                if len(matched) == 1:
                    d = delta(b[0], a[0])
                elif len(changes) == len(matched) and all(x != 0 for x in b):
                    d += f" ({statistics.median((y - x) / x for x, y in zip(b, a)):+.1%})"
                lines.append(f"| {k} | {distribution(b)} | {distribution(a)} | {d} |")
        if not complete or any(outcome(r) == "unverified" for r in runs):
            verdict = "Inconclusive: runs or correctness reviews are incomplete."
        elif any(r["status"] != "completed" for r in runs):
            verdict = "Inconclusive: execution failed or timed out. No correctness or efficiency improvement established."
        elif not all_pass:
            bpass = sum(outcome(r) == "passed" for r in sides["before"])
            apass = sum(outcome(r) == "passed" for r in sides["after"])
            direction = "Improved" if apass > bpass else "Regressed" if apass < bpass else "Mixed"
            verdict = direction + " correctness on these tasks. Do not infer an efficiency win from failed runs."
        else:
            verdict = "Correctness preserved on these tasks. Assess the resource tradeoffs above; no general performance claim."
        lines += ["", verdict, ""]
        for r in runs:
            if r.get("discovery"):
                d = r["discovery"]
                lines.append(f"- {cell(r['id'])}: reviewed discovery milestone at {number(d['elapsed_seconds'])} seconds / {d['tool_calls']} calls; {cell(d['evidence'])}")
    lines += ["## What to expect in everyday work", "",
              data.get("interpretation") or "Pending evidence-based interpretation. Explain the observed discovery, continuity, or validation benefit and its tradeoffs; do not extrapolate these tasks to all work.", "",
              "Cached input is a subset of input, not an additional token total. No dollar savings or reasoning capacity is inferred.",
              "Raw traces, prompts, patches, and reviews stay in local artifacts; review this report before sharing.", ""]
    return "\n".join(lines)


def planned_runs(m):
    """Every run the manifest asks for, as (repeat, task, side), in the order the runner takes them."""
    out = []
    for repeat in range(1, m["repetitions"] + 1):
        for index, task in enumerate(m["tasks"]):
            order = ("before", "after") if (repeat + index) % 2 else ("after", "before")
            out += [(repeat, task, side) for side in order if side in task.get("sides", ("before", "after"))]
    return out


def pending_runs(m, data):
    done = {r["id"] for r in data["runs"]}
    return [p for p in planned_runs(m) if f"{p[1]['id']}-{p[2]}-{p[0]}" not in done]


def set_aside(artifacts):
    """Move the folder of a run that did not finish to incomplete/, so a rerun starts clean and nothing is lost."""
    target = artifacts.parent.parent / "incomplete"
    target.mkdir(exist_ok=True)
    n = 1
    while (target / f"{artifacts.name}-{n}").exists():
        n += 1
    artifacts.rename(target / f"{artifacts.name}-{n}")


def run_benchmark(m, output, claude, resume=False, max_minutes=None):
    """Run every planned run, or with resume only those not yet recorded in the output folder.

    With max_minutes, no new run starts once the time used plus the longest run so far would pass
    the limit, so each batch fits under a fixed cap. Runs that never finished (interrupted, or an
    execution error before any tool call) are run again on resume; their folders go to incomplete/.
    """
    output = Path(output).resolve()
    version = subprocess.run([claude, "--version"], capture_output=True, text=True, check=True).stdout.strip()
    manifest_sha = hashlib.sha256(json.dumps(m, sort_keys=True).encode()).hexdigest()
    if resume:
        require((output / "results.json").is_file(), f"Nothing to resume: no results.json in {output}")
        data = read_json(output / "results.json")
        require(data.get("manifest_sha256") == manifest_sha,
                "The manifest has changed since this output folder was started. Resume only with the same "
                "manifest, or start a new output folder.")
        require(data.get("cli_version") == version,
                f"claude is now {version!r}, but this output folder was started with {data.get('cli_version')!r}. "
                "Start a new output folder rather than mixing versions.")
        unfinished = [r for r in data["runs"]
                      if r["status"] == "interrupted" or (r["status"] == "error" and not r.get("tool_calls"))]
        data["runs"] = [r for r in data["runs"] if r not in unfinished]
        for r in unfinished:
            if (output / r["artifacts"]).exists():
                set_aside(output / r["artifacts"])
    else:
        require(not output.exists(), "Output directory already exists; choose a new one, or pass --resume")
        output.mkdir(parents=True, mode=0o700)
        data = {k: m[k] for k in ("model", "reasoning_effort", "before", "after", "repetitions", "environment_notes", "change_origin")}
        data.update({"schema_version": VERSION, "adapter": "claude", "cli_version": version,
                     "manifest_sha256": manifest_sha,
                     "tasks": [{k: t[k] for k in ("id", "kind", "scenario")} for t in m["tasks"]],
                     "footprint": {s: footprint(m, m[s]) for s in ("before", "after")}, "runs": []})
        if m.get("launch"):
            data["launch"] = {s: {"start": spec["start"], "parent_files": sorted(spec["parent_files"]),
                                  "memory": spec["memory"], "fixtures_sha256": fixture_digest(spec)}
                              for s, spec in m["launch"].items()}
        write_json(output / "manifest.json", m)
    write_json(output / "results.json", data)
    started, longest = time.monotonic(), 0.0
    try:
        for repeat, task, side in pending_runs(m, data):
            if max_minutes and longest and time.monotonic() - started + longest > max_minutes * 60:
                break
            artifacts = output / "runs" / f"{task['id']}-{side}-{repeat}"
            if artifacts.exists():
                set_aside(artifacts)  # left by a batch that was stopped mid-run
            print(f"Running {task['id']} / {side} / {repeat}", flush=True)
            began = time.monotonic()
            data["runs"].append(run_one(m, task, side, repeat, output, claude))
            longest = max(longest, time.monotonic() - began)
            write_json(output / "results.json", data)
            (output / "report.md").write_text(render_report(data))
            if data["runs"][-1]["status"] == "interrupted":
                raise KeyboardInterrupt
            if data["runs"][-1]["status"] == "error" and not data["runs"][-1]["tool_calls"]:
                print("Stopped after an execution error before any tool calls; inspect local logs before starting a new comparison.", file=sys.stderr)
                return data
    finally:
        write_json(output / "results.json", data)
        (output / "report.md").write_text(render_report(data))
    return data


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("validate", "run"):
        p = sub.add_parser(action)
        p.add_argument("--manifest", required=True)
        if action == "run":
            p.add_argument("--output", required=True)
            p.add_argument("--claude", default="claude", help="path to the claude executable")
            p.add_argument("--max-minutes", type=float,
                           help="start no new run once this batch would pass this many minutes")
            p.add_argument("--resume", action="store_true",
                           help="continue an existing output folder, running only what is not yet recorded")
    p = sub.add_parser("report")
    p.add_argument("--results", required=True)
    p.add_argument("--output")
    p = sub.add_parser("packets", help="blind grading packets from results folders")
    p.add_argument("--out", required=True, help="new packet folder; the key is written beside it")
    p.add_argument("--seed", type=int, required=True)
    p.add_argument("--reading", action="store_true", help="also ask graders to label opened files needed or not")
    p.add_argument("--answer-key", help="answer key the graders read, named in the instructions")
    p.add_argument("--checkout", help="read-only checkout graders may consult, named in the instructions")
    p.add_argument("--leak", action="append", default=[], help="extra text that would reveal a setup")
    p.add_argument("sets", nargs="+", metavar="RESULTS_DIR:SIDE=ARM[,SIDE=ARM]")
    p = sub.add_parser("reading", help="files opened per run, and per document with grader labels")
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--results", nargs="+", help="results folders")
    source.add_argument("--packets", help="graded packet folder (its -KEY.json beside it)")
    p.add_argument("--sources", help="JSON mapping task IDs to key sources; overrides the manifest's key_sources")
    p.add_argument("--stale", action="append", default=[], metavar="PREFIX",
                   help="path prefix whose files count as stale unless a key source")
    p.add_argument("--output", help="write JSON here instead of printing it")
    args = parser.parse_args(argv)
    try:
        if args.action == "packets":
            sets = []
            for spec in args.sets:
                folder, _, arms = spec.rpartition(":")
                pairs = [x.split("=", 1) for x in arms.split(",")]
                require(folder and all(len(x) == 2 and x[0] in ("before", "after") and x[1] for x in pairs),
                        f"Expected RESULTS_DIR:before=ARM[,after=ARM], got {spec!r}")
                sets.append((folder, dict(pairs)))
            count, leaked = grading.build_packets(args.out, args.seed, sets, args.reading, args.answer_key,
                                                  args.checkout, args.leak)
            print(f"{count} packets in {args.out}; key in {args.out.rstrip('/')}-KEY.json")
            if leaked:
                print("Possible setup leaks in: " + ", ".join(leaked), file=sys.stderr)
                return 1
        elif args.action == "reading":
            sources = read_json(args.sources) if args.sources else None
            out = grading.reading(args.results or (), args.packets, sources, args.stale)
            text = json.dumps(out, indent=1) + "\n"
            if args.output:
                Path(args.output).write_text(text)
                print(json.dumps(out["totals"]))
            else:
                print(text, end="")
        elif args.action == "report":
            report = render_report(read_json(args.results))
            if args.output:
                Path(args.output).write_text(report)
            else:
                print(report)
        else:
            m = load_manifest(args.manifest)
            if args.action == "validate":
                print(json.dumps({"before": m["before"], "after": m["after"], "change_origin": m["change_origin"],
                                  "changed_paths": m["changed_paths"], "setup": m["setup"],
                                  "tasks": m["tasks"], "model": m["model"],
                                  "reasoning_effort": m["reasoning_effort"],
                                  "launch": m.get("launch"),
                                  "runs": sum(len(t.get("sides", ("before", "after"))) for t in m["tasks"])
                                  * m["repetitions"], "warnings": m["warnings"],
                                  "timeout_seconds_per_process": m["timeout_seconds"]}, indent=2))
            else:
                data = run_benchmark(m, args.output, args.claude, args.resume, args.max_minutes)
                left = len(pending_runs(m, data))
                if left:
                    print(f"{left} runs not yet done. Continue with the same command plus --resume.", file=sys.stderr)
                    return 3
        return 0
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted; completed runs have been saved.", file=sys.stderr)
        return 130
