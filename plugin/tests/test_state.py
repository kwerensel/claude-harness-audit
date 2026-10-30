import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from harness_bench.state import check, freeze, latest_run, load_plan, machine_before, main, run_dir


def plan(**overrides):
    base = {"summary": "Dashboard harness fixes",
            "recommendations": [{"id": "name-check-command", "kind": "harness", "title": "Name the check command",
                                 "source_evidence": "F10: CLAUDE.md names no check command",
                                 "acceptance": ["CLAUDE.md names the typecheck and test commands"]}],
            "decisions": [{"id": "no-stop-hook", "title": "No Stop hook for tests", "reason": "CI already runs them"}],
            "coverage": [{"finding": "F10", "covered_by": "name-check-command"}]}
    base.update(overrides)
    return base


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / "My Repo"
        self.repo.mkdir()
        for args in (["init", "-q"], ["config", "user.name", "T"], ["config", "user.email", "t@localhost"]):
            subprocess.run(["git", "-C", str(self.repo), *args], check=True)
        (self.repo / "a.txt").write_text("a")
        subprocess.run(["git", "-C", str(self.repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(self.repo), "-c", "core.hooksPath=/dev/null", "commit", "-qm", "one"], check=True)
        self.runs = self.root / "runs"

    def tearDown(self):
        self.temp.cleanup()

    def write(self, run, value):
        (run / "plan.json").write_text(json.dumps(value))

    def test_run_dir_is_outside_the_repo_and_named_by_repo_date_and_commit(self):
        run = run_dir(self.repo, self.runs, "2026-10-01")
        self.assertEqual(run.parent.name, "My-Repo")
        self.assertRegex(run.name, r"^2026-10-01-[0-9a-f]{7}$")
        self.assertNotIn(str(self.repo), str(run))
        meta = json.loads((run / "run.json").read_text())
        self.assertFalse(meta["dirty_at_start"])
        self.assertEqual(run_dir(self.repo, self.runs, "2026-10-01"), run)
        self.assertEqual(latest_run(self.repo, self.runs), run)
        self.assertEqual(subprocess.run(["git", "-C", str(self.repo), "status", "--porcelain"],
                                        capture_output=True, text=True).stdout, "")

    def test_run_dir_works_for_a_folder_that_is_not_a_repository(self):
        plain = self.root / "plain"
        plain.mkdir()
        self.assertTrue(run_dir(plain, self.runs, "2026-10-01").name.endswith("-nogit"))

    def test_latest_run_requires_an_audit(self):
        with self.assertRaisesRegex(ValueError, "Run the audit first"):
            latest_run(self.repo, self.runs)

    def test_freeze_then_check_then_detect_a_changed_criterion(self):
        run = run_dir(self.repo, self.runs, "2026-10-01")
        self.write(run, plan())
        lock = freeze(run)
        self.assertEqual(lock["recommendations"], ["name-check-command"])
        self.assertEqual(lock["decisions"], ["no-stop-hook"])
        self.assertEqual(check(run)["sha256"], lock["sha256"])
        with self.assertRaisesRegex(ValueError, "already frozen"):
            freeze(run)
        changed = plan()
        changed["recommendations"][0]["acceptance"] = ["CLAUDE.md mentions tests somewhere"]
        self.write(run, changed)
        with self.assertRaisesRegex(ValueError, "changed since it was frozen"):
            check(run)

    def test_reformatting_the_file_does_not_break_the_lock(self):
        run = run_dir(self.repo, self.runs, "2026-10-01")
        self.write(run, plan())
        freeze(run)
        (run / "plan.json").write_text(json.dumps(plan(), indent=4, sort_keys=True))
        check(run)

    def test_an_unruled_item_blocks_freezing(self):
        run = run_dir(self.repo, self.runs, "2026-10-01")
        value = plan()
        value["recommendations"][0]["needs_ruling"] = True
        self.write(run, value)
        with self.assertRaisesRegex(ValueError, "needs a ruling"):
            freeze(run)
        value["recommendations"][0]["ruling"] = "Owner chose option 1 on 2026-10-01"
        self.write(run, value)
        freeze(run)

    def test_plan_validation(self):
        path = self.root / "plan.json"
        cases = [(plan(summary=""), "summary"),
                 (plan(recommendations=[dict(plan()["recommendations"][0], kind="docs")]), "kind"),
                 (plan(recommendations=[dict(plan()["recommendations"][0], acceptance=[])]), "acceptance"),
                 (plan(recommendations=plan()["recommendations"] * 2), "unique"),
                 (plan(coverage=[{"finding": "F2", "covered_by": "missing"}]), "unknown ID"),
                 (plan(decisions=[{"id": "x", "title": "t"}]), "reason")]
        for value, message in cases:
            path.write_text(json.dumps(value))
            with self.assertRaisesRegex(ValueError, message):
                load_plan(path)

    def test_kit_shaped_plan_without_extras_is_accepted(self):
        path = self.root / "plan.json"
        path.write_text(json.dumps({"summary": "s", "recommendations": plan()["recommendations"]}))
        self.assertEqual(len(load_plan(path)["recommendations"]), 1)

    def test_measured_by_is_optional_and_validated_when_present(self):
        run = run_dir(self.repo, self.runs, "2026-10-01")
        rec = plan()["recommendations"][0]
        path = self.root / "plan.json"
        for measured, message in (("benchmark", "method"), ({"method": "survey", "detail": "x"}, "method"),
                                  ({"method": "benchmark", "detail": " "}, "detail"), ({"method": "direct check"}, "detail")):
            path.write_text(json.dumps(plan(recommendations=[dict(rec, measured_by=measured)])))
            with self.assertRaisesRegex(ValueError, message):
                load_plan(path)
        good = [dict(rec, measured_by={"method": "benchmark", "detail": "arm B against arm A"}),
                dict(rec, id="deny-env", measured_by={"method": "direct check", "detail": "Read .env once; refused"}),
                dict(rec, id="why-notes", measured_by={"method": "not measurable", "detail": "Upkeep only"})]
        self.write(run, plan(recommendations=good))
        self.assertEqual(freeze(run)["recommendations"], ["name-check-command", "deny-env", "why-notes"])

    def test_machine_before_copies_once_with_checksums_and_skips_credentials(self):
        run = run_dir(self.repo, self.runs, "2026-10-01")
        launch = self.root / "workspace"
        (launch / ".claude").mkdir(parents=True)
        (launch / "CLAUDE.md").write_text("@My Repo/CLAUDE.md\n")
        (launch / ".claude/settings.local.json").write_text('{"permissions": {"allow": ["Bash(ls:*)"]}}')
        (launch / ".claude/settings.json").write_text('{"env": {"TOKEN": "Bearer abcdefghijklmnop1234"}}')
        memory = self.root / "memory"
        memory.mkdir()
        (memory / "MEMORY.md").write_text("- [Rule](rule.md)\n")
        (memory / "nested").mkdir()
        record = machine_before(run, launch, memory)
        copied = run / "machine-before"
        self.assertEqual(sorted(record["files"]), ["launch-folder/.claude/settings.local.json",
                                                   "launch-folder/CLAUDE.md", "memory/MEMORY.md"])
        self.assertIn("credential", record["skipped"]["launch-folder/.claude/settings.json"])
        self.assertIn("not a regular file", record["skipped"]["memory/nested"])
        self.assertFalse((copied / "launch-folder/.claude/settings.json").exists())
        self.assertNotIn("abcdefghijklmnop", (copied / "checksums.json").read_text())
        self.assertEqual((copied / "memory/MEMORY.md").read_text(), "- [Rule](rule.md)\n")
        self.assertEqual(json.loads((copied / "checksums.json").read_text())["files"], record["files"])
        with self.assertRaisesRegex(ValueError, "already exists"):
            machine_before(run, launch, memory)
        with self.assertRaisesRegex(ValueError, "--launch-folder"):
            machine_before(self.root, None, None)

    def test_command_line(self):
        self.assertEqual(main(["dir", "--repo", str(self.repo), "--root", str(self.runs), "--date", "2026-10-01"]), 0)
        run = latest_run(self.repo, self.runs)
        self.assertEqual(main(["check", "--run", str(run)]), 2)
        self.write(run, plan())
        self.assertEqual(main(["freeze", "--run", str(run)]), 0)
        self.assertEqual(main(["check", "--run", str(run)]), 0)


if __name__ == "__main__":
    unittest.main()


class HarnessMapTests(unittest.TestCase):
    def test_map_is_a_drawing_with_every_piece_and_what_moved(self):
        import xml.etree.ElementTree as ET
        from harness_bench.harness_map import render
        entries = [{"piece": "CLAUDE.md", "location": "CLAUDE.md", "note": "routing and rules", "before": "found when needed", "after": "loaded at launch"},
                   {"piece": "Deny rules", "location": ".claude/settings.json", "before": "absent", "after": "enforced"},
                   {"piece": "Parent allow list", "location": "../.claude/settings.local.json", "before": "loaded at launch", "after": "does not reach"},
                   {"piece": "CI & tests", "location": ".github/workflows/ci.yml", "before": "enforced", "after": "enforced"}]
        svg = render(entries, "Map <test>")
        root = ET.fromstring(svg)
        texts = [t.text for t in root.iter("{http://www.w3.org/2000/svg}text")]
        self.assertNotIn("<table", svg)
        self.assertEqual(texts.count("CLAUDE.md"), 2)
        self.assertEqual(texts.count("Deny rules"), 1)
        self.assertIn("CI & tests", texts)
        self.assertIn("CLAUDE.md: found when needed → launch", texts)
        self.assertIn("Deny rules: added, enforced", texts)
        self.assertIn("Parent allow list: launch → outside", texts)
        self.assertGreater(len(list(root.iter("{http://www.w3.org/2000/svg}rect"))), 10)

    def test_map_without_after_is_one_panel_and_values_are_checked(self):
        from harness_bench.harness_map import render
        svg = render([{"piece": "CLAUDE.md", "location": "CLAUDE.md", "before": "loaded at launch"}], "One")
        self.assertNotIn("What moved", svg)
        self.assertIn("No guards", svg)
        with self.assertRaisesRegex(ValueError, "before must be"):
            render([{"piece": "x", "location": "y", "before": "sometimes"}], "Bad")

    def test_map_command_writes_svg_from_findings(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp)
            (run / "findings.json").write_text(json.dumps({"harness_map": [
                {"piece": "CLAUDE.md", "location": "CLAUDE.md", "before": "found when needed"}]}))
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["map", "--run", str(run)]), 0)
            self.assertTrue((run / "harness-map.svg").read_text().startswith("<svg"))


class DocIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        g = lambda *a: subprocess.run(["git", "-C", str(self.repo), *a], check=True, capture_output=True)
        g("init", "-q")
        (self.repo / "docs" / "_history").mkdir(parents=True)
        (self.repo / "CLAUDE.md").write_text("# Rules\n\n## Checks\n")
        (self.repo / "docs" / "spec.md").write_text("# Spec\n\n> DRAFT - pending\n\n## Scope\n## Data\n")
        (self.repo / "docs" / "_history" / "old.md").write_text("# Old plan\n")
        (self.repo / "package.json").write_text(json.dumps({"scripts": {"test": "vitest run"}}))
        g("add", ".")
        g("-c", "user.name=t", "-c", "user.email=t@l", "commit", "-qm", "init")
        self.g = g

    def tearDown(self):
        self.temp.cleanup()

    def test_index_is_deterministic_labelled_and_never_lists_itself(self):
        from harness_bench.doc_index import write_or_check
        write_or_check(self.repo, "AGENT-INDEX.md")
        first = (self.repo / "AGENT-INDEX.md").read_text()
        self.g("add", ".")
        self.g("-c", "user.name=t", "-c", "user.email=t@l", "commit", "-qm", "index")
        write_or_check(self.repo, "AGENT-INDEX.md")
        self.assertEqual((self.repo / "AGENT-INDEX.md").read_text(), first)
        self.assertNotIn("`AGENT-INDEX.md`", first)
        self.assertIn("| `docs/spec.md` | Spec | draft |", first)
        self.assertIn("| `docs/_history/old.md` | Old plan | historical |", first)
        self.assertIn("`npm run test`", first)
        self.assertLess(first.index("docs/spec.md"), first.index("docs/_history/old.md"))

    def test_check_fails_when_a_document_changes(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["index", "--repo", str(self.repo)]), 0)
            self.assertEqual(main(["index", "--repo", str(self.repo), "--check"]), 0)
        (self.repo / "docs" / "notes.txt").write_text("a file of a new kind is fine to ignore? no: new kind\n")
        self.g("add", ".")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["index", "--repo", str(self.repo), "--check"]), 1)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["index", "--repo", str(self.repo)]), 0)
        (self.repo / "docs" / "more.txt").write_text("same kind as notes.txt\n")
        self.g("add", ".")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["index", "--repo", str(self.repo), "--check"]), 0)
        (self.repo / "docs" / "new.md").write_text("# New\n")
        self.g("add", ".")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["index", "--repo", str(self.repo), "--check"]), 1)

    def test_index_stays_current_after_the_commit_that_refreshes_it(self):
        (self.repo / "docs" / "spec.md").write_text("# Spec\n\n## Scope changed\n")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["index", "--repo", str(self.repo)]), 0)
        self.g("add", ".")
        self.g("-c", "user.name=t", "-c", "user.email=t@l", "commit", "-qm", "docs and index together")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["index", "--repo", str(self.repo), "--check"]), 0)
