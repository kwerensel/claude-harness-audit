"""Runner tests. Ported from the kit's tests/test_benchmark.py at 4cc820e, with the
fake agent speaking Claude Code's stream-json instead of Codex's event format."""
import contextlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from harness_bench.cli import (agent_environment, delta, execute, footprint, git, load_manifest, outcome,
                               render_report, run_benchmark, snapshot, summarize_events, validate_results)


def event(value):
    return {'event': value, 'elapsed_seconds': 1}


def result_event(fresh=70, written=0, read=30, output=20, **extra):
    return {'type': 'result', 'subtype': 'success', 'is_error': False, 'result': 'app.txt', 'num_turns': 2,
            'usage': {'input_tokens': fresh, 'cache_creation_input_tokens': written,
                      'cache_read_input_tokens': read, 'output_tokens': output}, **extra}


def tool_event(ident, name='Read'):
    return {'type': 'assistant', 'message': {'content': [{'type': 'tool_use', 'id': ident, 'name': name}]}}


class RepoFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.repo = self.root / 'source'
        self.repo.mkdir()
        git(self.repo, 'init', '-q')
        git(self.repo, 'config', 'user.name', 'Test')
        git(self.repo, 'config', 'user.email', 'test@localhost')
        (self.repo / 'app.txt').write_text('original')
        (self.repo / '.gitignore').write_text('ignored\n')
        git(self.repo, 'add', '.')
        git(self.repo, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'before')
        before = git(self.repo, 'rev-parse', 'HEAD')
        (self.repo / 'CLAUDE.md').write_text('Find app.txt.\n')
        git(self.repo, 'add', '.')
        git(self.repo, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'after')
        self.manifest = {'schema_version': 1, 'repo': str(self.repo), 'before': before,
                         'after': git(self.repo, 'rev-parse', 'HEAD'), 'harness_paths': ['CLAUDE.md'],
                         'change_origin': 'Exploratory candidate: navigation guide, not an earlier implementation.',
                         'model': 'test-model', 'reasoning_effort': 'low', 'repetitions': 1,
                         'tasks': [{'id': 'locate', 'kind': 'orientation', 'prompt': 'Find the app.',
                                    'rubric': ['Identifies app.txt with evidence.']}]}
        self.path = self.root / 'manifest.json'

    def tearDown(self):
        self.temp.cleanup()

    def load(self):
        self.path.write_text(json.dumps(self.manifest))
        return load_manifest(self.path)


    def fake_claude(self):
        fake = self.root / 'fake-claude'
        fake.write_text(f'''#!{sys.executable}
import sys,json,os
from pathlib import Path
if '--version' in sys.argv:
 print('fake-claude 1'); sys.exit()
argv=sys.argv[1:]
for flag in ('-p','--verbose','--no-session-persistence','--strict-mcp-config'):
 assert flag in argv, flag
assert argv[argv.index('--output-format')+1]=='stream-json'
assert argv[argv.index('--setting-sources')+1]=='project'
assert 'ANTHROPIC_API_KEY' not in os.environ
prompt=sys.stdin.read()
assert 'Identifies app.txt with evidence.' not in prompt
assert 'hidden acceptance' not in prompt
tools=argv[argv.index('--allowedTools')+1:]
if 'change app' in prompt:
 assert 'Edit' in tools and argv[argv.index('--permission-mode')+1]=='acceptEdits'
 Path('app.txt').write_text('changed')
else:
 assert 'Edit' not in tools and 'Write' not in tools
print(json.dumps({{"type":"system","subtype":"init"}}))
print(json.dumps({{"type":"assistant","message":{{"content":[{{"type":"tool_use","id":"t1","name":"Read"}}]}}}}))
print(json.dumps({{"type":"result","subtype":"success","is_error":False,"result":"app.txt","num_turns":2,
 "usage":{{"input_tokens":70,"cache_creation_input_tokens":0,"cache_read_input_tokens":30,"output_tokens":20}}}}))
''')
        fake.chmod(0o755)
        return str(fake)

class BenchmarkTests(RepoFixture):
    def test_reject_application_changes(self):
        (self.repo / 'app.txt').write_text('different')
        git(self.repo, 'add', '.')
        git(self.repo, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'app change')
        self.manifest['after'] = git(self.repo, 'rev-parse', 'HEAD')
        with self.assertRaisesRegex(ValueError, 'Application changes'):
            self.load()

    def test_manifest_requires_quality_and_explicit_configuration(self):
        self.manifest.pop('change_origin')
        with self.assertRaisesRegex(ValueError, 'change_origin'):
            self.load()
        self.manifest['change_origin'] = 'Exploratory candidate: navigation guide.'
        self.manifest['tasks'][0]['rubric'] = []
        with self.assertRaisesRegex(ValueError, 'acceptance criteria'):
            self.load()
        self.manifest['tasks'][0]['kind'] = 'coding'
        self.manifest['tasks'][0]['rubric'] = ['Review']
        with self.assertRaisesRegex(ValueError, 'Coding tasks'):
            self.load()

    def test_manifest_warns_when_no_task_targets_a_gap(self):
        warnings = self.load()['warnings']
        self.assertTrue(any('gap' in w for w in warnings))
        self.assertTrue(any('repetition' in w for w in warnings))
        self.manifest['tasks'][0]['gap'] = 'F10: no check command is named'
        self.manifest['repetitions'] = 3
        self.assertEqual(self.load()['warnings'], [])
        self.manifest['tasks'][0]['gap'] = '  '
        with self.assertRaisesRegex(ValueError, 'gap'):
            self.load()

    def test_manifest_tool_lists_have_defaults_and_can_be_overridden(self):
        m = self.load()
        self.assertIn('Read', m['claude']['orientation_tools'])
        self.assertNotIn('Edit', m['claude']['orientation_tools'])
        self.assertIn('Edit', m['claude']['coding_tools'])
        self.manifest['claude'] = {'coding_tools': []}
        with self.assertRaisesRegex(ValueError, 'coding_tools'):
            self.load()

    def test_snapshot_omits_history_ignored_and_uncommitted_files(self):
        (self.repo / 'ignored').write_text('not exported')
        (self.repo / 'untracked').write_text('not exported')
        (self.repo / 'app.txt').write_text('local change')
        target = self.root / 'snapshot'
        snapshot(self.repo, self.manifest['before'], target)
        self.assertEqual((target / 'app.txt').read_text(), 'original')
        self.assertFalse((target / 'CLAUDE.md').exists())
        self.assertFalse((target / 'ignored').exists())
        self.assertFalse((target / 'untracked').exists())
        self.assertEqual(git(target, 'rev-list', '--count', 'HEAD'), '1')
        self.assertEqual(git(target, 'remote'), '')
        self.assertEqual((self.repo / 'app.txt').read_text(), 'local change')

    def test_footprint_counts_missing_as_zero_without_token_estimates(self):
        m = self.load()
        self.assertEqual(footprint(m, m['before'])['bytes'], 0)
        self.assertEqual(footprint(m, m['after'])['words'], 2)

    def test_parse_usage_maps_claude_fields_onto_the_kit_contract(self):
        values = [event({'type': 'system', 'subtype': 'init'}),
                  event(tool_event('x')), event(tool_event('x')), event(tool_event('y', 'Bash')),
                  event(result_event(fresh=10, written=30, read=60, output=10))]
        result = summarize_events(values)
        # total input includes both cache figures; cached is the read part only
        self.assertEqual(result['usage']['input_tokens'], 100)
        self.assertEqual(result['usage']['cached_input_tokens'], 60)
        self.assertEqual(result['usage']['uncached_input_tokens'], 40)
        self.assertEqual(result['usage']['cache_creation_input_tokens'], 30)
        self.assertEqual(result['usage']['output_tokens'], 10)
        self.assertIsNone(result['usage']['reasoning_output_tokens'])
        self.assertEqual(result['tool_calls'], 2)
        self.assertEqual(result['tool_breakdown'], {'Bash': 1, 'Read': 1})
        self.assertEqual(result['final'], 'app.txt')
        self.assertTrue(result['turn_completed'])
        self.assertFalse(result['turn_failed'])

    def test_parse_usage_missing_stays_unknown(self):
        self.assertIsNone(summarize_events([])['usage']['input_tokens'])
        self.assertIsNone(summarize_events([])['tool_calls'])
        partial = summarize_events([event({'type': 'result', 'subtype': 'success', 'usage': {'output_tokens': 5}})])
        self.assertIsNone(partial['usage']['input_tokens'])
        self.assertIsNone(partial['usage']['uncached_input_tokens'])
        self.assertEqual(partial['usage']['output_tokens'], 5)
        no_result = summarize_events([event(tool_event('x'))])
        self.assertFalse(no_result['turn_completed'])
        self.assertEqual(no_result['tool_calls'], 1)

    def test_error_result_is_a_failed_turn_with_usage_preserved(self):
        failed = result_event(fresh=5, written=0, read=5, output=2, is_error=True)
        failed['subtype'] = 'error_max_turns'
        result = summarize_events([event(failed)])
        self.assertTrue(result['turn_failed'])
        self.assertEqual(result['usage']['input_tokens'], 10)

    def test_timeout_and_malformed_output(self):
        result = execute([sys.executable, '-c', 'import time; print("bad",flush=True); time.sleep(10)'],
                         self.root, self.root / 'timeout', 0.1, events=True)
        self.assertEqual(result['status'], 'timeout')
        self.assertEqual(result['malformed_events'], 1)
        self.assertTrue((self.root / 'timeout/stdout.txt').exists())

    def test_agent_environment_drops_the_api_key_by_default(self):
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'not-a-real-key'}):
            self.assertNotIn('ANTHROPIC_API_KEY', agent_environment({}))
            self.assertIn('ANTHROPIC_API_KEY', agent_environment({'allow_api_key': True}))

    def test_full_runner_and_quality_gate(self):
        self.manifest['tasks'] += [{'id': 'change', 'kind': 'coding', 'prompt': 'change app',
                                    'acceptance': [[sys.executable, '-c',
                                                    "from pathlib import Path; assert Path('app.txt').read_text()=='changed', 'hidden acceptance'"]],
                                    'allowed_edit_paths': ['app.txt']}]
        with contextlib.redirect_stdout(io.StringIO()), patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'not-a-real-key'}):
            results = run_benchmark(self.load(), self.root / 'output', self.fake_claude())
        self.assertEqual(results['adapter'], 'claude')
        self.assertEqual(len(results['runs']), 4)
        self.assertEqual([r['status'] for r in results['runs']], ['completed'] * 4)
        self.assertEqual([r['side'] for r in results['runs']], ['before', 'after', 'after', 'before'])
        self.assertEqual(results['runs'][0]['usage']['input_tokens'], 100)
        self.assertEqual(results['runs'][0]['tool_breakdown'], {'Read': 1})
        self.assertEqual((self.root / 'output/runs/locate-before-1/final.txt').read_text(), 'app.txt')
        self.assertEqual(outcome(results['runs'][0]), 'unverified')
        self.assertEqual(outcome(results['runs'][2]), 'passed')
        self.assertEqual((self.repo / 'app.txt').read_text(), 'original')
        report = render_report(results)
        self.assertIn('Inconclusive', report)
        self.assertIn('Adapter: claude', report)
        run = results['runs'][0]
        run['reviews'] = [{'criterion': 0, 'passed': True, 'evidence': 'final.txt names app.txt'}]
        self.assertEqual(outcome(run), 'passed')
        run['reviews'][0]['passed'] = False
        run['usage']['input_tokens'] = 1
        run['usage']['cached_input_tokens'] = 0
        run['usage']['uncached_input_tokens'] = 1
        self.assertEqual(outcome(run), 'failed')
        self.assertIn('| failed |', render_report(results))
        results['runs'].append(dict(run))
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            validate_results(results)

    def test_zero_baseline(self):
        self.assertIn('zero baseline', delta(0, 10))
        self.assertEqual(delta(None, 10), 'unavailable')
        self.assertIn('-50.0%', delta(100, 50))

    def results(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return run_benchmark(self.load(), self.root / 'results', self.fake_claude())

    def test_faster_wrong_answer_is_not_an_efficiency_win(self):
        data = self.results()
        for r in data['runs']:
            r['reviews'] = [{'criterion': 0, 'passed': r['side'] == 'before',
                             'evidence': 'fixed-rubric review'}]
            r['usage']['input_tokens'] = 100 if r['side'] == 'before' else 50
            r['usage']['uncached_input_tokens'] = r['usage']['input_tokens'] - 30
        report = render_report(data)
        self.assertIn('Regressed correctness', report)
        self.assertNotIn('Matched successful pairs only', report)

    def test_usage_and_review_validation(self):
        data = self.results()
        r = data['runs'][0]
        r['usage']['cached_input_tokens'] = 101
        with self.assertRaisesRegex(ValueError, 'Inconsistent'):
            validate_results(data)
        r['usage']['cached_input_tokens'] = 30
        r['reviews'] = [{'criterion': 1, 'passed': True, 'evidence': 'wrong criterion'}]
        with self.assertRaisesRegex(ValueError, 'review criterion'):
            validate_results(data)
        r['reviews'] = []
        r['elapsed_seconds'] = float('nan')
        with self.assertRaisesRegex(ValueError, 'elapsed_seconds'):
            validate_results(data)

    def test_identical_criteria_required(self):
        data = self.results()
        data['runs'][1]['rubric'] = ['An easier question']
        with self.assertRaisesRegex(ValueError, 'criteria differ'):
            validate_results(data)

    def test_continuity_requires_handoff(self):
        self.manifest['tasks'][0]['scenario'] = 'continuity'
        with self.assertRaisesRegex(ValueError, 'handoff'):
            self.load()

    def test_symlink_snapshot_rejected(self):
        (self.repo / 'external').symlink_to('/tmp')
        git(self.repo, 'add', '.')
        git(self.repo, '-c', 'core.hooksPath=/dev/null', 'commit', '-qm', 'symlink')
        with self.assertRaisesRegex(ValueError, 'symlinks'):
            snapshot(self.repo, 'HEAD', self.root / 'unsafe-snapshot')

    def test_interruption_preserves_process_logs(self):
        import subprocess
        original = subprocess.Popen.wait
        calls = [0]

        def interrupt_once(process, *args, **kwargs):
            calls[0] += 1
            if calls[0] == 1:
                raise KeyboardInterrupt
            return original(process, *args, **kwargs)
        with patch.object(subprocess.Popen, 'wait', interrupt_once):
            result = execute([sys.executable, '-c', 'import time; time.sleep(10)'],
                             self.root, self.root / 'interrupted', 15, events=True)
        self.assertEqual(result['status'], 'interrupted')
        self.assertTrue((self.root / 'interrupted/events.json').exists())

    def test_provider_startup_error_stops_remaining_sessions(self):
        fake = self.root / 'unavailable-claude'
        fake.write_text(f'''#!{sys.executable}
import sys,json
if '--version' in sys.argv:
 print('fake-claude 1'); sys.exit()
print(json.dumps({{"type":"result","subtype":"success","is_error":True,"result":"Failed to authenticate.","usage":{{}}}}))
sys.exit(1)
''')
        fake.chmod(0o755)
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            data = run_benchmark(self.load(), self.root / 'stopped', str(fake))
        self.assertEqual(len(data['runs']), 1)
        self.assertEqual(data['runs'][0]['status'], 'error')
        self.assertIn('Inconclusive', render_report(data))


if __name__ == '__main__':
    unittest.main()


class LaunchTests(RepoFixture):
    """Launch setups: a side may start in a recreated workspace folder above the repository,
    with given settings and a copy of given memory notes."""

    def fixtures(self):
        parent_settings = self.root / 'parent-settings.json'
        parent_settings.write_text('{"permissions": {"allow": ["Bash(git add *)"]}}')
        memory = self.root / 'memory'
        memory.mkdir()
        (memory / 'MEMORY.md').write_text('- [Rule](rule.md) - proceed without asking\n')
        return parent_settings, memory

    def fake_launch_claude(self):
        fake = self.root / 'fake-launch-claude'
        fake.write_text(f'''#!{sys.executable}
import sys,json,os,re
from pathlib import Path
if '--version' in sys.argv:
 print('fake-claude 1'); sys.exit()
argv=sys.argv[1:]
cwd=Path.cwd()
sources=argv[argv.index('--setting-sources')+1]
memory=Path(json.loads(argv[argv.index('--settings')+1])['autoMemoryDirectory'])
assert sources=='project,local', sources
assert '--strict-mcp-config' in argv
assert 'proceed without asking' in (memory/'MEMORY.md').read_text()
if (cwd/'source').is_dir():
 assert (cwd/'.claude/settings.local.json').is_file()
 assert (cwd/'source/app.txt').read_text()=='original'
else:
 assert (cwd/'app.txt').is_file() and not (cwd/'.claude/settings.local.json').exists()
(memory/'new-note.md').write_text('written by the agent')
state=Path(os.environ['HOME'])/'.claude/projects'/re.sub(r'[^A-Za-z0-9]','-',str(cwd))
state.mkdir(parents=True)
(state/'leftover.txt').write_text('session state')
print(json.dumps({{"type":"assistant","message":{{"content":[{{"type":"tool_use","id":"t1","name":"Read"}}]}}}}))
print(json.dumps({{"type":"result","subtype":"success","is_error":False,"result":"app.txt","num_turns":1,
 "usage":{{"input_tokens":5,"cache_creation_input_tokens":0,"cache_read_input_tokens":5,"output_tokens":2}}}}))
''')
        fake.chmod(0o755)
        return str(fake)

    def test_launch_is_validated(self):
        parent_settings, memory = self.fixtures()
        self.manifest['launch'] = {'before': {'start': 'elsewhere'}}
        with self.assertRaisesRegex(ValueError, 'start must be repo or parent'):
            self.load()
        self.manifest['launch'] = {'before': {'start': 'repo', 'parent_files': {'x.json': str(parent_settings)}}}
        with self.assertRaisesRegex(ValueError, 'need start parent'):
            self.load()
        self.manifest['launch'] = {'before': {'start': 'parent', 'parent_files': {'source/x.json': str(parent_settings)}}}
        with self.assertRaisesRegex(ValueError, 'inside the repository snapshot'):
            self.load()
        self.manifest['launch'] = {'before': {'start': 'parent', 'memory': str(self.root / 'missing')}}
        with self.assertRaisesRegex(ValueError, 'not a folder'):
            self.load()
        (memory / 'leak.md').write_text('token: Bearer abcdefghijklmnop1234')
        self.manifest['launch'] = {'before': {'start': 'repo', 'memory': str(memory)}}
        with self.assertRaisesRegex(ValueError, 'credential-shaped'):
            self.load()
        self.manifest['tasks'][0]['sides'] = ['during']
        self.manifest.pop('launch')
        with self.assertRaisesRegex(ValueError, 'sides'):
            self.load()

    def test_parent_and_repo_launch_use_copies_and_leave_nothing_behind(self):
        parent_settings, memory = self.fixtures()
        home = self.root / 'home'
        (home / '.claude/projects/unrelated').mkdir(parents=True)
        self.manifest['launch'] = {
            'before': {'start': 'parent', 'parent_files': {'.claude/settings.local.json': str(parent_settings)},
                       'memory': str(memory)},
            'after': {'start': 'repo', 'memory': str(memory)}}
        with contextlib.redirect_stdout(io.StringIO()), patch.dict(os.environ, {'HOME': str(home)}):
            results = run_benchmark(self.load(), self.root / 'output', self.fake_launch_claude())
        self.assertEqual([r['status'] for r in results['runs']], ['completed', 'completed'])
        before = next(r for r in results['runs'] if r['side'] == 'before')
        self.assertEqual(before['launch']['start'], 'parent')
        self.assertIn('.claude/settings.local.json', before['launch']['fixtures_sha256'])
        self.assertTrue(before['memory_changed'])
        self.assertTrue((self.root / 'output/runs/locate-before-1/memory-after/new-note.md').exists())
        # The fixture itself is untouched, and every session folder the runs created is gone.
        self.assertEqual(sorted(p.name for p in memory.iterdir()), ['MEMORY.md'])
        self.assertEqual([p.name for p in (home / '.claude/projects').iterdir()], ['unrelated'])
        report = render_report(results)
        self.assertIn('Launch, before: a workspace folder above the repository', report)
        self.assertIn('Launch, after: repository root', report)

    def test_cleanup_also_runs_when_the_agent_fails(self):
        _, memory = self.fixtures()
        home = self.root / 'home'
        fake = self.root / 'failing-claude'
        fake.write_text(f'''#!{sys.executable}
import sys,os,re
from pathlib import Path
if '--version' in sys.argv:
 print('fake-claude 1'); sys.exit()
state=Path(os.environ['HOME'])/'.claude/projects'/re.sub(r'[^A-Za-z0-9]','-',str(Path.cwd()))
state.mkdir(parents=True)
sys.exit(3)
''')
        fake.chmod(0o755)
        self.manifest['launch'] = {'before': {'start': 'repo', 'memory': str(memory)}}
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), \
                patch.dict(os.environ, {'HOME': str(home)}):
            results = run_benchmark(self.load(), self.root / 'output', str(fake))
        self.assertEqual(results['runs'][0]['status'], 'error')
        self.assertEqual(list((home / '.claude/projects').iterdir()), [])

    def test_sides_limits_a_task_to_runs_not_already_measured(self):
        self.manifest['tasks'][0]['sides'] = ['after']
        with contextlib.redirect_stdout(io.StringIO()):
            results = run_benchmark(self.load(), self.root / 'output', self.fake_claude())
        self.assertEqual([r['side'] for r in results['runs']], ['after'])

    def test_closing_replaces_the_default_last_sentence(self):
        self.manifest['tasks'][0]['closing'] = 'Report what you did.'
        with contextlib.redirect_stdout(io.StringIO()):
            run_benchmark(self.load(), self.root / 'output', self.fake_claude())
        prompt = json.loads((self.root / 'output/runs/locate-before-1/invocation.json').read_text())['prompt']
        self.assertTrue(prompt.endswith('Report what you did.'))
        self.assertNotIn('Do not modify any files.', prompt)
        self.manifest['tasks'][0]['closing'] = ' '
        with self.assertRaisesRegex(ValueError, 'closing'):
            self.load()
