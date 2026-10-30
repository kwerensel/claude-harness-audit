"""Run folders and the frozen plan.

Each audit of a repository at a commit gets one folder outside that repository:

    ~/.harness-audit/runs/<repo-name>/<date>-<short-sha>/

The audit, the plan and the benchmark all read and write there, so no step
depends on text being pasted from an earlier conversation.

Commands:
    python3 -m harness_bench.state dir    --repo PATH [--root DIR] [--date YYYY-MM-DD]
    python3 -m harness_bench.state latest --repo PATH [--root DIR]
    python3 -m harness_bench.state freeze --run DIR
    python3 -m harness_bench.state check  --run DIR
    python3 -m harness_bench.state machine-before --run DIR [--launch-folder DIR] [--memory DIR]
    python3 -m harness_bench.state map    --run DIR [--input FILE] [--title TEXT]
    python3 -m harness_bench.state index  --repo PATH [--out AGENT-INDEX.md] [--check]
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from .cli import SECRET
from .harness_map import render
from .doc_index import write_or_check

KINDS = ("harness", "code", "mixed")
MEASURED_BY = ("benchmark", "direct check", "not measurable")
DEFAULT_ROOT = "~/.harness-audit/runs"
# The files in a launch folder that change what a session loads. Same relative paths as the
# benchmark manifest's launch.parent_files, so the copies can be used there unchanged.
LAUNCH_FILES = ("CLAUDE.md", "CLAUDE.local.md", ".claude/settings.json", ".claude/settings.local.json")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def git(repo, *args):
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return p.stdout.strip() if p.returncode == 0 else None


def repo_identity(repo):
    """Name, short commit and dirty flag. A folder that is not a repository still gets a run folder."""
    repo = Path(repo).expanduser().resolve()
    require(repo.is_dir(), f"No such directory: {repo}")
    top = git(repo, "rev-parse", "--show-toplevel")
    sha = git(repo, "rev-parse", "--short=7", "HEAD")
    dirty = bool(git(repo, "status", "--porcelain")) if top else False
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(top or repo).name).strip("-") or "repo"
    return {"path": str(repo), "top": top, "name": name, "sha": sha or "nogit", "dirty": dirty}


def run_dir(repo, root=DEFAULT_ROOT, date=None):
    ident = repo_identity(repo)
    date = date or datetime.date.today().isoformat()
    folder = Path(root).expanduser() / ident["name"] / f"{date}-{ident['sha']}"
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    meta = folder / "run.json"
    if not meta.exists():
        meta.write_text(json.dumps({"repo": ident["path"], "commit": git(repo, "rev-parse", "HEAD"),
                                    "dirty_at_start": ident["dirty"], "created": date}, indent=2) + "\n")
    return folder


def latest_run(repo, root=DEFAULT_ROOT):
    ident = repo_identity(repo)
    base = Path(root).expanduser() / ident["name"]
    runs = sorted(p for p in base.glob("*") if p.is_dir()) if base.is_dir() else []
    require(runs, f"No audit run found for {ident['name']} under {base}. Run the audit first.")
    return runs[-1]


def load_plan(path):
    plan = json.loads(Path(path).read_text())
    require(isinstance(plan, dict), "plan.json must be an object")
    require(isinstance(plan.get("summary"), str) and plan["summary"].strip(), "plan.summary is required")
    recs = plan.get("recommendations")
    require(isinstance(recs, list), "plan.recommendations must be a list")
    ids = set()
    for rec in recs:
        ident = rec.get("id", "")
        require(isinstance(ident, str) and re.fullmatch(r"[a-z0-9][a-z0-9_-]*", ident) and ident not in ids,
                f"Recommendation IDs must be unique lowercase slugs: {ident!r}")
        ids.add(ident)
        require(rec.get("kind") in KINDS, f"{ident}: kind must be one of {', '.join(KINDS)}")
        for key in ("title", "source_evidence"):
            require(isinstance(rec.get(key), str) and rec[key].strip(), f"{ident}: {key} is required")
        acceptance = rec.get("acceptance")
        require(isinstance(acceptance, list) and acceptance and
                all(isinstance(x, str) and x.strip() for x in acceptance),
                f"{ident}: acceptance must list at least one observable criterion")
        if rec.get("needs_ruling"):
            require(isinstance(rec.get("ruling"), str) and rec["ruling"].strip(),
                    f"{ident}: needs a ruling from the owner before the plan can be frozen")
        if "measured_by" in rec:
            measured = rec["measured_by"]
            require(isinstance(measured, dict) and measured.get("method") in MEASURED_BY,
                    f"{ident}: measured_by.method must be one of {', '.join(MEASURED_BY)}")
            require(isinstance(measured.get("detail"), str) and measured["detail"].strip(),
                    f"{ident}: measured_by.detail must name the arm, the action attempted, or the reason")
    for decision in plan.get("decisions", []):
        ident = decision.get("id", "")
        require(isinstance(ident, str) and re.fullmatch(r"[a-z0-9][a-z0-9_-]*", ident) and ident not in ids,
                f"Decision IDs must be unique lowercase slugs: {ident!r}")
        ids.add(ident)
        for key in ("title", "reason"):
            require(isinstance(decision.get(key), str) and decision[key].strip(), f"{ident}: {key} is required")
    for row in plan.get("coverage", []):
        require(isinstance(row.get("finding"), str) and row["finding"].strip(), "coverage rows need a finding")
        require(row.get("covered_by") in ids, f"coverage for {row.get('finding')!r} points at an unknown ID")
    return plan


def digest(plan):
    return hashlib.sha256(json.dumps(plan, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def freeze(run):
    run = Path(run).expanduser()
    plan_path, lock_path = run / "plan.json", run / "plan.lock"
    require(plan_path.is_file(), f"No plan.json in {run}")
    require(not lock_path.exists(), "This plan is already frozen. To change it, start a new run folder "
                                    "or delete plan.lock deliberately and freeze again.")
    plan = load_plan(plan_path)
    require(plan["recommendations"] or plan.get("decisions"), "Nothing to freeze: no recommendations or decisions")
    lock = {"sha256": digest(plan), "frozen_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
            "recommendations": [r["id"] for r in plan["recommendations"]],
            "decisions": [d["id"] for d in plan.get("decisions", [])]}
    lock_path.write_text(json.dumps(lock, indent=2) + "\n")
    return lock


def check(run):
    run = Path(run).expanduser()
    lock_path = run / "plan.lock"
    require(lock_path.is_file(), f"No plan.lock in {run}: the plan has not been frozen")
    lock = json.loads(lock_path.read_text())
    current = digest(load_plan(run / "plan.json"))
    require(current == lock["sha256"], "plan.json has changed since it was frozen. Criteria must not move "
                                       "after implementation starts. Restore it or start a new run.")
    return lock


def machine_before(run, launch_folder=None, memory=None):
    """Copy the machine-level state into <run>/machine-before/ with checksums, once.

    Copies the launch folder's instruction and settings files and the memory notes. A file that
    holds a credential-shaped string is never copied; it is listed as skipped, by path only.
    Nothing is printed from any file.
    """
    run = Path(run).expanduser()
    require(run.is_dir(), f"No such run folder: {run}")
    require(launch_folder or memory, "Give --launch-folder, --memory, or both")
    target = run / "machine-before"
    require(not target.exists(), "machine-before already exists. The before state is copied once; "
                                 "start a new run folder to copy it again.")
    sources = []
    if launch_folder:
        folder = Path(launch_folder).expanduser().resolve()
        require(folder.is_dir(), f"No such launch folder: {folder}")
        sources += [(folder / name, f"launch-folder/{name}") for name in LAUNCH_FILES]
    if memory:
        folder = Path(memory).expanduser().resolve()
        require(folder.is_dir(), f"No such memory folder: {folder}")
        sources += [(item, f"memory/{item.name}") for item in sorted(folder.iterdir())]
    record = {"launch_folder": str(Path(launch_folder).expanduser().resolve()) if launch_folder else None,
              "memory": str(Path(memory).expanduser().resolve()) if memory else None,
              "copied_at": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
              "files": {}, "skipped": {}}
    target.mkdir(mode=0o700)
    for source, name in sources:
        if not source.exists():
            continue
        if not source.is_file() or source.is_symlink():
            record["skipped"][name] = "not a regular file"
            continue
        data = source.read_bytes()
        if SECRET.search(data.decode(errors="replace")):
            record["skipped"][name] = "holds a credential-shaped string; not copied"
            continue
        (target / name).parent.mkdir(parents=True, exist_ok=True)
        (target / name).write_bytes(data)
        record["files"][name] = hashlib.sha256(data).hexdigest()
    (target / "checksums.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


def draw_map(run, source=None, title=None):
    """Draw harness-map.svg in the run folder from a harness_map list (findings.json by default)."""
    run = Path(run).expanduser()
    source = Path(source).expanduser() if source else run / "findings.json"
    if not source.is_absolute() and not source.exists():
        source = run / source
    data = json.loads(source.read_text())
    entries = data.get("harness_map") if isinstance(data, dict) else data
    title = title or "Harness map: where each piece reaches the agent"
    target = run / "harness-map.svg"
    target.write_text(render(entries, title))
    return target


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("dir", "latest"):
        p = sub.add_parser(action)
        p.add_argument("--repo", default=os.getcwd())
        p.add_argument("--root", default=DEFAULT_ROOT)
        if action == "dir":
            p.add_argument("--date")
    for action in ("freeze", "check"):
        p = sub.add_parser(action)
        p.add_argument("--run", required=True)
    p = sub.add_parser("machine-before")
    p.add_argument("--run", required=True)
    p.add_argument("--launch-folder")
    p.add_argument("--memory")
    p = sub.add_parser("index")
    p.add_argument("--repo", default=os.getcwd())
    p.add_argument("--out", default="AGENT-INDEX.md")
    p.add_argument("--check", action="store_true", help="fail if the file is missing or out of date")
    p = sub.add_parser("map")
    p.add_argument("--run", required=True)
    p.add_argument("--input", help="JSON with a harness_map list; default findings.json in the run folder")
    p.add_argument("--title")
    args = parser.parse_args(argv)
    try:
        if args.action == "dir":
            print(run_dir(args.repo, args.root, args.date))
        elif args.action == "latest":
            print(latest_run(args.repo, args.root))
        elif args.action == "freeze":
            lock = freeze(args.run)
            print(f"Frozen {len(lock['recommendations'])} recommendations and {len(lock['decisions'])} decisions "
                  f"({lock['sha256'][:12]}).")
        elif args.action == "machine-before":
            record = machine_before(args.run, args.launch_folder, args.memory)
            print(f"Copied {len(record['files'])} files to {Path(args.run).expanduser() / 'machine-before'}.")
            for name, reason in record["skipped"].items():
                print(f"Skipped {name}: {reason}")
        elif args.action == "index":
            if args.check:
                if not write_or_check(args.repo, args.out, check=True):
                    print(f"{args.out} is out of date: run harness-state index", file=sys.stderr)
                    return 1
                print(f"{args.out} is current.")
            else:
                write_or_check(args.repo, args.out)
                print(f"Wrote {args.out}")
        elif args.action == "map":
            print(f"Drew {draw_map(args.run, args.input, args.title)}")
        else:
            lock = check(args.run)
            print(f"Plan unchanged since {lock['frozen_at']} ({lock['sha256'][:12]}).")
        return 0
    except (ValueError, KeyError, OSError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
