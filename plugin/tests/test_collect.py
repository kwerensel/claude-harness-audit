"""The inventory script must be safe to point at a real machine.

These tests build a fake home folder and a fake repository, then check both what
the script reports and what it must never print: secret values, the body of a
memory note, or conversation text from session history.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "skills" / "harness-audit" / "scripts" / "collect.sh"
TOKEN = "patFAKEFAKEFAKE1234567890abcdef"
ENV_SECRET = "sbp_do_not_print_this_value_0000"
NOTE_BODY = "PRIVATE-NOTE-BODY-should-never-appear"
CHAT_TEXT = "PRIVATE-CONVERSATION-should-never-appear"


def encode(path):
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


class CollectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / "home"
        self.parent = self.home / "Work Folder"
        self.repo = self.parent / "app"
        self.repo.mkdir(parents=True)
        git(self.repo, "init", "-q")
        git(self.repo, "config", "user.name", "T")
        git(self.repo, "config", "user.email", "t@localhost")

    def tearDown(self):
        self.temp.cleanup()

    def run_script(self, *args, timeout=60):
        env = dict(os.environ, HOME=str(self.home))
        env.pop("CLAUDE_PROJECT_DIR", None)
        p = subprocess.run(["bash", str(SCRIPT), *args], capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL, env=env, cwd=str(self.root))
        return p.returncode, p.stdout + p.stderr

    def populate(self):
        (self.repo / "CLAUDE.md").write_text("# App\n\n## Rules\n- Never touch the live workspace.\n"
                                             "- Always run `npm test` before committing.\n")
        (self.repo / ".gitignore").write_text(".env\n")
        (self.repo / ".env").write_text(f"SUPABASE_TOKEN={ENV_SECRET}\n")
        (self.repo / ".env.example").write_text("SUPABASE_TOKEN=\n")
        (self.repo / "package.json").write_text('{"scripts": {"test": "vitest", "typecheck": "tsc"}}\n')
        (self.repo / "docs").mkdir()
        (self.repo / "docs" / "contract.md").write_text("one two three four five\n")
        git(self.repo, "add", ".")
        git(self.repo, "-c", "core.hooksPath=/dev/null", "commit", "-qm", "init")
        (self.repo / "docs" / "handoff.md").write_text("newest decisions live here\n")  # untracked on purpose
        # settings one level above the repository, as when sessions are launched from the parent
        (self.parent / ".claude").mkdir()
        (self.parent / ".claude" / "settings.local.json").write_text(json.dumps(
            {"permissions": {"allow": ["Bash(node -e ' *)", f"Bash(curl -H 'Authorization: Bearer {TOKEN}' *)"]}}))
        # user-level settings with an inline credential
        (self.home / ".claude").mkdir()
        (self.home / ".claude" / "settings.json").write_text(json.dumps(
            {"model": "x", "mcpServers": {"airtable": {"type": "http", "url": "https://example.invalid/mcp",
                                                      "headers": {"Authorization": f"Bearer {TOKEN}"}}}}, indent=2))
        # session history and memory recorded against the PARENT folder
        project = self.home / ".claude" / "projects" / encode(self.parent)
        (project / "memory").mkdir(parents=True)
        lines = [json.dumps({"cwd": str(self.parent), "message": {"content": CHAT_TEXT}})] * 3
        lines += [json.dumps({"cwd": str(self.repo), "message": {"content": CHAT_TEXT}})]
        (project / "session-1.jsonl").write_text("\n".join(lines) + "\n")
        (project / "memory" / "MEMORY.md").write_text("- [Rules](working-rules.md) - apply every session\n")
        (project / "memory" / "working-rules.md").write_text(
            f"---\nname: working-rules\ndescription: Rules to apply in every session\n---\n\n{NOTE_BODY}\n")

    def test_blank_repository_with_no_commits_completes(self):
        code, out = self.run_script(str(self.repo), timeout=30)
        self.assertEqual(code, 0, out)
        self.assertIn("===== end =====", out)
        self.assertIn("no project CLAUDE.md", out)
        self.assertNotIn("usage:", out.lower())

    def test_checkout_scope_reports_rules_documents_and_checks(self):
        self.populate()
        code, out = self.run_script("--no-machine", str(self.repo))
        self.assertEqual(code, 0, out)
        self.assertIn("scopes: checkout\n", out)
        self.assertRegex(out, r"4:- Never touch the live workspace")
        self.assertRegex(out, r"5:- Always run `npm test`")
        self.assertRegex(out, r"UNTRACKED\s+-\s+docs/handoff.md")
        self.assertRegex(out, r"tracked\s+\S+\s+docs/contract.md")
        self.assertRegex(out, r"\./\.env\s+gitignored")
        self.assertRegex(out, r"\./\.env\.example\s+NOT gitignored")
        self.assertIn('"typecheck": "tsc"', out)
        self.assertIn("no settings files in the repository", out)
        self.assertNotIn("MACHINE SCOPE", out)
        self.assertNotIn(str(self.home / ".claude"), out)

    def test_machine_scope_finds_the_launch_folder_above_the_repository(self):
        self.populate()
        code, out = self.run_script(str(self.repo))
        self.assertEqual(code, 0, out)
        self.assertIn("scopes: checkout + machine", out)
        self.assertRegex(out, rf"launch folder: {re.escape(str(self.parent))}\s+\(ABOVE the repository\)\s+sessions recorded: 1")
        self.assertRegex(out, rf"3 \"cwd\":\"{re.escape(str(self.parent))}\"")
        self.assertRegex(out, r"working-rules\.md\s+\d+ lines\s+description: Rules to apply in every session")
        self.assertIn("MEMORY.md index: 1 lines", out)
        self.assertIn("outside the repository, not version controlled with it", out)
        self.assertIn("1. Bash(node -e ' *)", out)
        self.assertIn("connector server 'airtable': type=http inline credential=YES", out)
        self.assertIn("lines holding a literal credential:", out)
        self.assertIn("top-level keys: mcpServers, model", out)

    def test_nothing_private_is_printed_in_either_scope(self):
        self.populate()
        for args in ([str(self.repo)], ["--no-machine", str(self.repo)]):
            _, out = self.run_script(*args)
            for forbidden in (TOKEN, ENV_SECRET, NOTE_BODY, CHAT_TEXT, "example.invalid"):
                self.assertNotIn(forbidden, out, f"{forbidden} leaked with {args[:-1]}")
        _, out = self.run_script(str(self.repo))
        self.assertIn("<REDACTED-SECRET>", out)

    def test_script_changes_nothing(self):
        self.populate()
        def state():
            # every file and folder, including the repository's own .git folder
            return sorted((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in self.root.rglob("*"))
        before = state()
        self.run_script(str(self.repo))
        self.run_script("--no-machine", str(self.repo))
        self.assertEqual(before, state())

    def test_sessions_recorded_against_the_repository_itself(self):
        self.populate()
        project = self.home / ".claude" / "projects" / encode(self.repo)
        project.mkdir(parents=True)
        (project / "s.jsonl").write_text(json.dumps({"cwd": str(self.repo)}) + "\n")
        _, out = self.run_script(str(self.repo))
        self.assertRegex(out, rf"launch folder: {re.escape(str(self.repo))}\s+\(the repository itself\)")


if __name__ == "__main__":
    unittest.main()
