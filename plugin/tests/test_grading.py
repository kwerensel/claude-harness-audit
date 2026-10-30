"""Blind packets, reading measures and batched runs, on small synthetic results folders."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from harness_bench import grading
from harness_bench.cli import main, pending_runs, run_benchmark
from harness_bench.grading import build_packets, norm, reading, workspace_patterns
from test_benchmark import RepoFixture

TMP = '/private/var/folders/xy/abc/T/harness-value-k3j9'


def call(ident, name, given, seconds=1.0):
    return {'elapsed_seconds': seconds, 'event': {'type': 'assistant', 'message': {'content': [
        {'type': 'tool_use', 'id': ident, 'name': name, 'input': given}]}}}


def returned(ident, text):
    return {'elapsed_seconds': 0, 'event': {'type': 'user', 'message': {'content': [
        {'type': 'tool_result', 'tool_use_id': ident, 'content': text}]}}}


def trace(root):
    """A run started in a workspace folder above a repository named my-app."""
    return [call('t1', 'Read', {'file_path': f'{root}/parent/my-app/CLAUDE.md'}, 1.0),
            returned('t1', 'x' * 100),
            call('t2', 'Grep', {'pattern': 'rules'}, 2.0),
            call('t3', 'Bash', {'command': 'cat .claude/rules/api.md docs/old.md'}, 3.0),
            returned('t3', 'y' * 60),
            call('t4', 'Read', {'file_path': f'{root}/parent/my-app/src/api.ts', 'offset': 10, 'limit': 5}, 4.0),
            returned('t4', 'z' * 40),
            call('t5', 'Read', {'file_path': f'{root}/memory/notes.md'}, 5.0),
            returned('t5', 'm' * 10)]


class Results(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def results(self, name, side, tasks, key_sources=None):
        """A results folder like the runner's, with one completed run per task."""
        folder = self.root / name
        manifest_tasks = [{'id': t, 'kind': 'orientation', 'rubric': ['Names the rule.', 'Cites the file.']}
                          for t in tasks]
        for t in manifest_tasks:
            if key_sources and t['id'] in key_sources:
                t['key_sources'] = key_sources[t['id']]
        runs = []
        for t in tasks:
            run_id = f'{t}-{side}-1'
            art = folder / 'runs' / run_id
            (art / 'agent').mkdir(parents=True)
            (art / 'agent' / 'events.json').write_text(json.dumps(trace(TMP)))
            (art / 'final.txt').write_text(f'See {TMP}/parent/my-app/src/api.ts and {TMP}/memory/notes.md')
            (art / 'tracked.patch').write_text('')
            runs.append({'id': run_id, 'task_id': t, 'side': side, 'repeat': 1, 'status': 'completed',
                         'revision': 'abc123', 'rubric': ['Names the rule.', 'Cites the file.'], 'checks': [],
                         'changed_files': [], 'scope_ok': True, 'artifacts': f'runs/{run_id}'})
        (folder / 'results.json').write_text(json.dumps({'schema_version': 1, 'runs': runs}))
        (folder / 'manifest.json').write_text(json.dumps({
            'tasks': manifest_tasks,
            'launch': {side: {'start': 'parent', 'parent_name': 'my-app', 'parent_files': {},
                              'memory': str(self.root / 'fixtures' / 'memory-variant')}}}))
        return folder


class NormTests(unittest.TestCase):
    def test_leading_dot_of_dot_folders_is_kept(self):
        self.assertEqual(norm('.claude/rules/notion.md'), '.claude/rules/notion.md')
        self.assertEqual(norm('./.claude/settings.json'), '.claude/settings.json')
        self.assertEqual(norm('./docs/a.md'), 'docs/a.md')
        self.assertEqual(norm('.github/workflows/ci.yml'), '.github/workflows/ci.yml')

    def test_temporary_folders_map_to_repository_paths(self):
        patterns = workspace_patterns(['my-app'])
        self.assertEqual(norm(f'{TMP}/parent/my-app/.claude/rules/x.md', patterns), '.claude/rules/x.md')
        self.assertEqual(norm(f'{TMP}/repo/.claude/rules/x.md', patterns), '.claude/rules/x.md')
        self.assertEqual(norm(f'{TMP}/parent/CLAUDE.md', patterns), '../CLAUDE.md')
        self.assertEqual(norm(f'{TMP}/memory/notes.md', patterns), 'memory/notes.md')
        self.assertEqual(norm('/tmp/harness-value-q/repo/src/a.ts'), 'src/a.ts')


class PacketTests(Results):
    def build(self, reading=False, **extra):
        before = self.results('run-old-orientation', 'before', ['find-rule', 'unlisted-task'])
        after = self.results('run-new-orientation', 'after', ['find-rule', 'unlisted-task'])
        out = self.root / 'grading-1'
        count, leaked = build_packets(out, 7, [(before, {'before': 'A'}), (after, {'after': 'B'})],
                                      reading=reading, **extra)
        return out, count, leaked

    def test_files_opened_listed_for_every_task_without_any_sources(self):
        out, count, _ = self.build()
        self.assertEqual(count, 4)
        for meta in sorted(out.glob('runs/*/meta.json')):
            meta = json.loads(meta.read_text())
            self.assertEqual(meta['files_opened'], ['CLAUDE.md', '.claude/rules/api.md', 'docs/old.md',
                                                    'src/api.ts', 'memory/notes.md'])
        self.assertEqual(sorted(json.loads((out / 'by-task.json').read_text())), ['find-rule', 'unlisted-task'])

    def test_setup_is_hidden_and_the_key_is_outside(self):
        out, _, leaked = self.build()
        self.assertEqual(leaked, [])
        key = json.loads((self.root / 'grading-1-KEY.json').read_text())
        self.assertEqual(sorted(k['arm'] for k in key.values()), ['A', 'A', 'B', 'B'])
        self.assertFalse(list(out.rglob('*KEY*')))
        final = (out / 'runs/R01/final.txt').read_text()
        self.assertEqual(final, 'See <repo>/src/api.ts and <memory-dir>/notes.md')
        self.assertNotIn('harness-value', (out / 'runs/R01/tool-calls.txt').read_text())
        _, _, again = self.build_same_seed()
        self.assertEqual(again, key)

    def build_same_seed(self):
        out = self.root / 'grading-2'
        sets = [(self.root / 'run-old-orientation', {'before': 'A'}), (self.root / 'run-new-orientation', {'after': 'B'})]
        build_packets(out, 7, sets)
        return out, None, json.loads((self.root / 'grading-2-KEY.json').read_text())

    def test_leaks_are_reported(self):
        before = self.results('run-old-orientation', 'before', ['find-rule'])
        (before / 'runs/find-rule-before-1/final.txt').write_text('I used memory-variant and run-old-orientation.')
        _, leaked = build_packets(self.root / 'g', 1, [(before, {'before': 'A'})], leaks=['secret-arm'])
        self.assertEqual(leaked, ['runs/R01/final.txt'])

    def test_instructions_say_traces_show_calls_not_contents(self):
        out, _, _ = self.build()
        text = (out / 'GRADER-INSTRUCTIONS.md').read_text()
        self.assertIn('does not show\n  what any file or command returned', text)
        self.assertIn('records calls, not file contents', text)
        self.assertNotIn('needed', text)
        self.assertNotRegex(text, r'\{[a-z_]+\}')

    def test_file_labelling_only_when_reading_is_measured(self):
        out, _, _ = self.build(reading=True, answer_key='/k/answer-key.md', checkout='/k/checkout')
        text = (out / 'GRADER-INSTRUCTIONS.md').read_text()
        self.assertIn('**Files.** Label every path in `files_opened`', text)
        self.assertIn('"not_needed"', text)
        self.assertIn('`/k/answer-key.md`', text)
        self.assertIn('`/k/checkout`', text)


class ReadingTests(Results):
    def test_counts_from_the_trace_with_sources_passed_as_data(self):
        folder = self.results('r', 'after', ['find-rule', 'other'], key_sources={'find-rule': ['src/api.ts']})
        out = reading([folder], stale_prefixes=['docs/'])
        rows = {r['task']: r for r in out['runs']}
        self.assertEqual(rows['find-rule']['files_opened'], 4)
        self.assertEqual(rows['find-rule']['memory_notes_opened'], 1)
        self.assertEqual(rows['find-rule']['stale'], 1)
        self.assertEqual(rows['find-rule']['calls_to_first_key_source'], 4)
        self.assertIsNone(rows['other']['calls_to_first_key_source'])
        # A sources file overrides the manifest, and covers tasks the manifest has no list for.
        out = reading([folder], sources={'_about': 'note', 'other': ['CLAUDE.md']})
        rows = {r['task']: r for r in out['runs']}
        self.assertEqual(rows['other']['calls_to_first_key_source'], 1)
        self.assertEqual(out['totals']['chars_read'], 2 * 200)
        self.assertFalse(out['totals']['labelled'])

    def test_per_document_report_applies_grader_labels(self):
        folder = self.results('r', 'after', ['find-rule'])
        out_dir = self.root / 'g'
        build_packets(out_dir, 3, [(folder, {'after': 'B'})], reading=True)
        (out_dir / 'reviews-find-rule.json').write_text(json.dumps({'R01': {
            'task_id': 'find-rule',
            'reviews': [{'criterion': 0, 'passed': True, 'evidence': 'e'}, {'criterion': 1, 'passed': True, 'evidence': 'e'}],
            'needed': [{'file': '.claude/rules/api.md', 'reason': 'holds the rule'}],
            'not_needed': ['CLAUDE.md', 'docs/old.md', 'src/api.ts']}}))
        out = reading(packets=out_dir)
        run = out['runs'][0]
        self.assertEqual((run['arm'], run['correct']), ('B', True))
        self.assertEqual(run['chars_needed'], 30)
        self.assertEqual(run['chars_not_needed'], 100 + 30 + 40)
        self.assertEqual(run['chars_not_needed_after_first_needed'], 40)  # docs/old.md shares the call
        docs = out['documents']
        self.assertEqual(list(docs)[0], 'CLAUDE.md')
        self.assertNotIn('memory/notes.md', docs)
        self.assertEqual(docs['src/api.ts']['full_reads'], 0)
        self.assertEqual(docs['.claude/rules/api.md']['runs_needed'], 1)
        self.assertEqual(docs['.claude/rules/api.md']['tasks'], ['find-rule'])
        self.assertEqual(out['totals']['chars_not_needed'], 170)

    def test_cli(self):
        folder = self.results('r', 'after', ['find-rule'])
        target = self.root / 'reading.json'
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['reading', '--results', str(folder), '--output', str(target)]), 0)
            self.assertEqual(main(['packets', '--out', str(self.root / 'p'), '--seed', '1', f'{folder}:after=B']), 0)
        self.assertEqual(json.loads(target.read_text())['totals']['runs'], 1)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['packets', '--out', str(self.root / 'q'), '--seed', '1', f'{folder}:side=B']), 2)


class BatchTests(RepoFixture):
    def setUp(self):
        super().setUp()
        self.manifest['tasks'].append({'id': 'second', 'kind': 'orientation', 'prompt': 'Find the app again.',
                                       'rubric': ['Identifies app.txt with evidence.']})

    def test_batches_stop_at_the_limit_and_resume_to_completion(self):
        m, output, fake = self.load(), self.root / 'output', self.fake_claude()
        with contextlib.redirect_stdout(io.StringIO()):
            data = run_benchmark(m, output, fake, max_minutes=1e-9)
            self.assertEqual(len(data['runs']), 1)
            self.assertEqual(len(pending_runs(m, data)), 3)
            (output / 'runs' / 'second-before-1').mkdir(parents=True)  # a run cut off by the 2-hour cap
            data = run_benchmark(m, output, fake, resume=True, max_minutes=1e-9)
            self.assertEqual(len(data['runs']), 2)
            data = run_benchmark(m, output, fake, resume=True)
        self.assertEqual(len(data['runs']), 4)
        self.assertEqual(pending_runs(m, data), [])
        self.assertEqual(len({r['id'] for r in data['runs']}), 4)
        self.assertTrue((output / 'incomplete' / 'second-before-1-1').is_dir())
        self.assertEqual(json.loads((output / 'results.json').read_text())['runs'], data['runs'])

    def test_resume_refuses_a_changed_manifest_or_missing_folder(self):
        output, fake = self.root / 'output', self.fake_claude()
        with contextlib.redirect_stdout(io.StringIO()):
            run_benchmark(self.load(), output, fake, max_minutes=1e-9)
        self.manifest['tasks'][0]['rubric'] = ['An easier question']
        with self.assertRaisesRegex(ValueError, 'manifest has changed'):
            run_benchmark(self.load(), output, fake, resume=True)
        with self.assertRaisesRegex(ValueError, 'Nothing to resume'):
            run_benchmark(self.load(), self.root / 'never', fake, resume=True)
        with self.assertRaisesRegex(ValueError, 'pass --resume'):
            run_benchmark(self.load(), output, fake)

    def test_cli_exit_code_says_runs_remain(self):
        self.path.write_text(json.dumps(self.manifest))
        args = ['run', '--manifest', str(self.path), '--output', str(self.root / 'o'), '--claude', self.fake_claude()]
        err = io.StringIO()
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            self.assertEqual(main(args + ['--max-minutes', '1e-9']), 3)
            self.assertIn('--resume', err.getvalue())
            self.assertEqual(main(args + ['--resume']), 0)

    def test_key_sources_are_validated(self):
        self.manifest['tasks'][0]['key_sources'] = ['../outside.md']
        with self.assertRaisesRegex(ValueError, 'repository-relative'):
            self.load()


if __name__ == '__main__':
    unittest.main()
