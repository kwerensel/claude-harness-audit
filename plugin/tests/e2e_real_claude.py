"""End-to-end check against the real command-line Claude. Uses real usage.

Not part of the unit suite (the file name does not start with test_). Run it by
hand when the runner or Claude Code's output format changes:

    HARNESS_E2E_MODEL=sonnet python3 tests/e2e_real_claude.py

It builds a tiny fixture repository with a before and an after commit, runs one
orientation task on each side, and checks that the adapter read real events:
a completed status, integer token counts that add up, a tool-call count, and a
final answer. Output is kept in a temporary folder whose path is printed.
"""
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from harness_bench.cli import git, load_manifest, outcome, render_report, run_benchmark  # noqa: E402


def main():
    model = os.environ.get("HARNESS_E2E_MODEL", "sonnet")
    root = Path(tempfile.mkdtemp(prefix="harness-e2e-"))
    repo = root / "fixture"
    (repo / "src").mkdir(parents=True)
    git(repo, "init", "-q")
    git(repo, "config", "user.name", "Fixture")
    git(repo, "config", "user.email", "fixture@localhost")
    (repo / "src" / "greeting.txt").write_text("Hello from the fixture.\n")
    (repo / "src" / "notes.txt").write_text("Unrelated notes.\n")
    (repo / "README.md").write_text("# Fixture\n\nA tiny repository for an end-to-end check.\n")
    git(repo, "add", ".")
    git(repo, "-c", "core.hooksPath=/dev/null", "commit", "-qm", "before")
    before = git(repo, "rev-parse", "HEAD")
    (repo / "CLAUDE.md").write_text("The greeting text lives in src/greeting.txt.\n")
    git(repo, "add", ".")
    git(repo, "-c", "core.hooksPath=/dev/null", "commit", "-qm", "after")
    manifest = {"schema_version": 1, "repo": str(repo), "before": before, "after": git(repo, "rev-parse", "HEAD"),
                "harness_paths": ["CLAUDE.md"], "model": model, "reasoning_effort": "low", "repetitions": 1,
                "timeout_seconds": 300,
                "change_origin": "Exploratory candidate: end-to-end check of the runner, not a real audit item.",
                "environment_notes": "End-to-end check of the adapter. Not a measurement.",
                "tasks": [{"id": "find-greeting", "kind": "orientation", "gap": "fixture",
                           "prompt": "Which file in this repository holds the greeting text? Reply with the path only.",
                           "rubric": ["Names src/greeting.txt."]}]}
    path = root / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2))
    data = run_benchmark(load_manifest(path), root / "output", os.environ.get("HARNESS_E2E_CLAUDE", "claude"))
    problems = []
    for run in data["runs"]:
        final = (root / "output" / run["artifacts"] / "final.txt").read_text().strip()
        usage = run["usage"]
        print(f"\n{run['id']}: status={run['status']} turns={run.get('num_turns')} "
              f"seconds={run['elapsed_seconds']} tools={run['tool_calls']} {run.get('tool_breakdown')}")
        print(f"  usage: {usage}")
        print(f"  final: {final[:200]!r}")
        if run["status"] != "completed":
            problems.append(f"{run['id']}: status {run['status']}")
            continue
        for key in ("input_tokens", "cached_input_tokens", "uncached_input_tokens", "output_tokens"):
            if type(usage[key]) is not int:
                problems.append(f"{run['id']}: {key} was not read")
        if type(usage["input_tokens"]) is int and usage["input_tokens"] != usage["cached_input_tokens"] + usage["uncached_input_tokens"]:
            problems.append(f"{run['id']}: token counts do not add up")
        if run["tool_calls"] is None:
            problems.append(f"{run['id']}: tool calls were not counted")
        if "greeting.txt" not in final:
            problems.append(f"{run['id']}: final answer not captured or wrong: {final[:80]!r}")
        if not run["scope_ok"]:
            problems.append(f"{run['id']}: an orientation run changed files: {run['changed_files']}")
        run["reviews"] = [{"criterion": 0, "passed": "src/greeting.txt" in final, "evidence": f"final.txt: {final[:80]}"}]
        print(f"  outcome after review: {outcome(run)}")
    print("\n" + "\n".join(render_report(data).splitlines()[:14]))
    print(f"\nartifacts kept in: {root}")
    print(f"adapter: {data['adapter']} {data['cli_version']}  model: {model}")
    if problems:
        print("\nPROBLEMS:\n  " + "\n  ".join(problems))
        return 1
    print("\nEnd-to-end check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
