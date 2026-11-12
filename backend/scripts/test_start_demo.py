"""Launcher contracts without an embedding model, provider, or dependency installs."""
import importlib
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


class StartDemoTest(unittest.TestCase):
    def launcher(self):
        try:
            return importlib.import_module('start_demo')
        except ModuleNotFoundError:
            self.fail('The one-command launcher is not implemented.')

    def test_evaluation_service_runs_as_a_package_from_the_repository(self):
        app = self.launcher()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            commands = {}

            class Owned:
                def __init__(self, session, cwd):
                    self.cwd = cwd
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def run_checked(self, *args, **kwargs): pass
                def start(self, label, command, *args):
                    commands[label] = command
                    if label == 'evals': raise KeyboardInterrupt()

            with patch.dict(app.os.environ, {}, clear=True), \
                    patch.object(app, 'ROOT', root), patch.object(app, 'check_tools'), \
                    patch.object(app, 'check_ports'), patch.object(app, 'check_no_native_jobs'), \
                    patch.object(app, 'NativeSlot'), patch.object(app, 'prepare_builds'), \
                    patch.object(app, 'credential', return_value=(root / 'provided.key', False)), \
                    patch.object(app, 'validate_index', return_value={'corpus_version': 'synthetic'}), \
                    patch.object(app, 'wait_json', return_value={'status': 'ready', 'corpus_version': 'synthetic'}), \
                    patch.object(app, 'OwnedProcesses', Owned):
                self.assertEqual(app.run(app.parse_args(['--no-open'])), 0)
            self.assertEqual(commands['evals'][:3], [sys.executable, '-m', 'evals.evals_web'])

    def test_backend_build_prepares_the_document_extractor_too(self):
        app = self.launcher()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root / 'backend/src').mkdir(parents=True); (root / 'frontend').mkdir()
            for name in ['backend/Cargo.toml', 'backend/Cargo.lock', 'backend/src/main.rs', 'frontend/package.json', 'frontend/package-lock.json']:
                (root / name).write_text('synthetic-build-input')
            settings = app.local_settings(root, {})
            try: extractor = settings['extractor']
            except KeyError: self.fail('A complete Mike build must include document_text.')
            calls = []
            def run(command, **kwargs):
                calls.append((command, kwargs))
                self.assertNotIn('ORQ_API_KEY', kwargs['env']); self.assertNotIn('ORQ_API_KEY_FILE', kwargs['env'])
                if command[0] == 'cargo':
                    for file in (settings['binary'], extractor): file.parent.mkdir(parents=True, exist_ok=True); file.write_text('built')
                elif 'ci' in command:
                    file = root / 'frontend/node_modules/.package-lock.json'; file.parent.mkdir(parents=True); file.write_text('installed')
                else:
                    file = root / 'frontend/dist/index.html'; file.parent.mkdir(parents=True); file.write_text('built')
            app.prepare_builds(settings, {'ORQ_API_KEY': 'never-to-build'}, run)
            self.assertIn('--bins', calls[0][0]); self.assertTrue(extractor.is_file())

    def test_sigterm_executes_main_cleanup_and_removes_only_its_temporary_key(self):
        app = self.launcher()
        with tempfile.TemporaryDirectory() as temporary:
            script = r"""
import os, signal, sys
from pathlib import Path
import start_demo as app
root=Path(sys.argv[1]); app.ROOT=root
app.check_tools=lambda:None; app.check_ports=lambda _:None
app.validate_index=lambda _:{'corpus_version':'synthetic'}
app.prepare_builds=lambda *args:None
app.check_no_native_jobs=lambda:None
app.native_slot_path=lambda:root/'native.lock'
class Owned:
 def __init__(self,*args):pass
 def __enter__(self):return self
 def __exit__(self,*args):(root/'cleanup-ran').write_text('yes')
 def run_checked(self,*args,**kwargs):pass
 def start(self,*args):os.kill(os.getpid(),signal.SIGTERM)
app.OwnedProcesses=Owned
os.environ['ORQ_API_KEY']='synthetic-private-key'
raise SystemExit(app.main(['--no-open']))
"""
            result = subprocess.run([sys.executable, '-c', script, temporary], env={**os.environ, 'PYTHONPATH': str(ROOT / 'backend/scripts')}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue((Path(temporary) / 'cleanup-ran').exists())
            self.assertFalse(list(Path(temporary).rglob('*.key')))
            self.assertNotIn('synthetic-private-key', result.stdout + result.stderr)

    def test_root_entry_is_directly_executable_and_explains_its_options(self):
        entry = ROOT / 'start'
        self.assertTrue(entry.exists() and os.access(entry, os.X_OK), './start must be executable.')
        result = subprocess.run([str(entry), '--help'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--orq-key-file', result.stdout)
        self.assertIn('--no-open', result.stdout)

    def test_secret_modes_do_not_leak_and_user_file_is_never_owned(self):
        app = self.launcher()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            user_file = root / 'provided.key'; user_file.write_text('synthetic-provided\n')
            path, owned = app.credential({}, user_file, root, interactive=False)
            self.assertEqual(path, user_file.resolve()); self.assertFalse(owned)
            path, owned = app.credential({'ORQ_API_KEY': 'synthetic-env'}, None, root, interactive=False)
            self.assertTrue(owned); self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.read_text(), 'synthetic-env'); path.unlink()
            path, owned = app.credential({}, None, root, interactive=True, prompt=lambda _: 'synthetic-hidden')
            self.assertTrue(owned); self.assertEqual(path.read_text(), 'synthetic-hidden'); path.unlink()
            with self.assertRaisesRegex(app.StartError, 'ORQ_API_KEY_FILE'):
                app.credential({}, None, root, interactive=False)
            clean = app.clean_environment({'PATH': '/bin', 'ORQ_API_KEY': 'never-to-child', 'ORQ_API_KEY_FILE': '/private'})
            self.assertNotIn('ORQ_API_KEY', clean); self.assertNotIn('ORQ_API_KEY_FILE', clean)
            self.assertEqual(user_file.read_text(), 'synthetic-provided\n')

    def test_occupied_or_duplicate_ports_fail_without_signalling_any_process(self):
        app = self.launcher()
        with socket.socket() as listener:
            listener.bind(('127.0.0.1', 0)); listener.listen()
            with self.assertRaisesRegex(app.StartError, 'bezet'):
                app.check_ports([listener.getsockname()[1]])
            with self.assertRaises(app.StartError): app.check_ports([12345, 12345])
            self.assertEqual(listener.getsockname()[0], '127.0.0.1')

    def test_cleanup_stops_only_children_created_by_the_launcher(self):
        app = self.launcher()
        with tempfile.TemporaryDirectory() as temporary:
            other = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'], start_new_session=True)
            owned = app.OwnedProcesses(Path(temporary), ROOT)
            try:
                child = owned.start('test', [sys.executable, '-c', 'import time; time.sleep(60)'], {})
                owned.stop()
                self.assertIsNotNone(child.poll()); self.assertIsNone(other.poll())
            finally:
                try: owned.stop()
                finally:
                    other.terminate(); other.wait(timeout=5)

    def test_partial_start_failure_still_cleans_up_owned_children(self):
        app = self.launcher()
        with tempfile.TemporaryDirectory() as temporary:
            owned = app.OwnedProcesses(Path(temporary), ROOT)
            child = None
            with self.assertRaises(OSError):
                with owned:
                    child = owned.start('first', [sys.executable, '-c', 'import time; time.sleep(60)'], {})
                    owned.start('missing', ['/not/an/executable'], {})
            self.assertIsNotNone(child.poll())

    def test_local_path_configuration_is_portable_and_environment_wins(self):
        app = self.launcher()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'start.local.json').write_text('{"ADAMI_DB_PATH":"private/index.sqlite"}')
            settings = app.local_settings(root, {'ADAMI_CACHE_DIR': 'cached-model'})
            self.assertEqual(settings['database'], root / 'private/index.sqlite')
            self.assertEqual(settings['cache'], root / 'cached-model')
            settings = app.local_settings(root, {'ADAMI_DB_PATH': '/explicit/index.sqlite'})
            self.assertEqual(settings['database'], Path('/explicit/index.sqlite'))

    def test_existing_corrupt_index_is_a_clear_setup_error(self):
        app = self.launcher()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); (root / 'cache').mkdir(); (root / 'corpus').mkdir()
            database = root / 'bad.sqlite'; database.write_text('not a sqlite database')
            settings = {'root': ROOT, 'database': database, 'cache': root / 'cache', 'corpus': root / 'corpus'}
            try: app.validate_index(settings)
            except app.StartError as failure: self.assertIn('LOCAL_SETUP', str(failure))
            except Exception: self.fail('An existing corrupt index must produce a safe setup error, not a traceback.')
            else: self.fail('A corrupt index must not start services.')

    def test_two_launchers_cannot_claim_the_same_native_slot(self):
        app = self.launcher()
        with tempfile.TemporaryDirectory() as temporary:
            lock = Path(temporary) / 'native.lock'
            with app.NativeSlot(lock):
                with self.assertRaises(app.StartError):
                    with app.NativeSlot(lock): pass
            with app.NativeSlot(lock): pass

    def test_existing_native_job_on_another_port_is_rejected_without_signals(self):
        app = self.launcher()
        process = '123 /some/target/texas-case-finder serve\n'
        with patch.object(app.subprocess, 'check_output', return_value=process), patch.object(app.os, 'killpg') as signal_group:
            with self.assertRaises(app.StartError): app.check_no_native_jobs()
            signal_group.assert_not_called()

    def test_missing_index_fails_with_setup_instructions_without_building_or_importing(self):
        app = self.launcher()
        with tempfile.TemporaryDirectory() as temporary:
            settings = app.local_settings(Path(temporary), {})
            with self.assertRaisesRegex(app.StartError, 'LOCAL_SETUP'):
                app.validate_index(settings)
