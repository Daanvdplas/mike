"""Start the complete local Mike demo; own and clean up only our processes."""
import argparse
import getpass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import shlex
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib import error, request
import webbrowser

import deterministic_b1 as b1
import evals_web
from orq_credentials import load_api_key
from orq_proxy import provider_endpoint

ROOT = Path(__file__).resolve().parents[2]
LOCAL_KEYS = {'ADAMI_DB_PATH', 'ADAMI_CACHE_DIR', 'ADAMI_CORPUS_DIR', 'ADAMI_BINARY', 'CARGO_TARGET_DIR', 'ADAMI_DOCUMENT_EXTRACTOR'}


class StartError(Exception):
    pass


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description='Start Mike en de evaluaties. Ctrl+C stopt alleen deze services.')
    parser.add_argument('--orq-key-file', type=Path, help='Privé sleutelbestand; geef geen sleutel als commandoregelargument.')
    parser.add_argument('--no-open', action='store_true', help='Open de browser niet automatisch.')
    for name, default in [('backend', 8000), ('orq', 18000), ('mike', 5176), ('eval', 8798)]:
        parser.add_argument(f'--{name}-port', type=int, default=default)
    return parser.parse_args(argv)


def local_settings(root, environment):
    local_file = root / 'start.local.json'
    try:
        local = json.loads(local_file.read_text()) if local_file.exists() else {}
    except (OSError, ValueError):
        raise StartError('start.local.json kan niet worden gelezen; zie docs/LOCAL_SETUP.md.') from None
    if not isinstance(local, dict) or set(local) - LOCAL_KEYS or any(not isinstance(value, str) or not value.strip() for value in local.values()):
        raise StartError('start.local.json mag uitsluitend de gedocumenteerde lokale padinstellingen bevatten.')
    def path(key, default):
        value = Path(environment.get(key) or local.get(key) or default).expanduser()
        return value if value.is_absolute() else root / value
    target = path('CARGO_TARGET_DIR', 'backend/target')
    return {'root': root, 'database': path('ADAMI_DB_PATH', 'data/cases.sqlite3'),
            'cache': path('ADAMI_CACHE_DIR', '.fastembed_cache'),
            'corpus': path('ADAMI_CORPUS_DIR', 'data/texas-criminal-reports'),
            'target': target, 'binary': path('ADAMI_BINARY', str(target / 'debug/texas-case-finder')),
            'extractor': path('ADAMI_DOCUMENT_EXTRACTOR', str(target / 'debug/document_text'))}


def validate_index(settings):
    if not settings['database'].is_file() or not settings['cache'].is_dir() or not settings['corpus'].is_dir():
        raise StartError('De ingestelde index, modelcache of corpus ontbreekt. Zie docs/LOCAL_SETUP.md; ./start importeert of downloadt geen model.')
    try:
        fixture, _ = b1.load_fixture(settings['root'])
        manifest, _ = b1.verified_index(fixture, settings['database'], settings['corpus'])
        model = manifest['embedding']['model'].replace('/', '--')
        cache_root = settings['cache'] / f'models--{model}'
        revision = (cache_root / 'refs/main').read_bytes()
        if not re.fullmatch(rb'[0-9a-f]{40}\s*', revision):
            raise ValueError('Invalid cached revision')
        snapshot = cache_root / 'snapshots' / revision.decode().strip()
        digest = hashlib.sha256(revision)
        for name in ('model_optimized.onnx', 'tokenizer.json', 'tokenizer_config.json', 'special_tokens_map.json', 'config.json'):
            file = snapshot / name
            digest.update(name.encode()); digest.update(file.stat().st_size.to_bytes(8, 'little'))
            with file.open('rb') as source:
                for chunk in iter(lambda: source.read(65536), b''): digest.update(chunk)
        if digest.hexdigest() != manifest['embedding']['artifacts_sha256']:
            raise ValueError('Cache fingerprint mismatch')
        # Validate the E06 source as well, without loading an embedding model.
        rows, _ = evals_web.scenario_catalog(settings['root'])
        row = next(row for row in rows if row['id'] == 'E06')
        evals_web.indexed_source({'corpus': settings['corpus'], 'database': settings['database']}, row)
    except (OSError, ValueError, KeyError, TypeError, StopIteration, sqlite3.Error, evals_web.RunError) as failure:
        raise StartError('De index/modelcache/corpus past niet bij deze versie. Zie docs/LOCAL_SETUP.md; er is niets geïmporteerd of gedownload.') from failure
    return manifest


def clean_environment(environment):
    return {key: value for key, value in environment.items() if key not in {'ORQ_API_KEY', 'ORQ_API_KEY_FILE', 'ADAMI_DOCUMENT_EXTRACTOR'}}


def credential(environment, key_file, session, interactive=None, prompt=None):
    supplied = dict(environment)
    if key_file is not None:
        supplied = {'ORQ_API_KEY_FILE': str(key_file.expanduser().resolve())}
    try:
        key = load_api_key(supplied)
    except ValueError as failure:
        raise StartError(str(failure)) from None
    if not key:
        interactive = sys.stdin.isatty() if interactive is None else interactive
        if not interactive:
            raise StartError('Geen Orq-sleutel beschikbaar. Stel ORQ_API_KEY_FILE of ORQ_API_KEY in, of start ./start in een interactieve terminal.')
        try:
            key = (prompt or getpass.getpass)('Orq API key (verborgen): ').strip()
        except EOFError:
            raise StartError('Geen Orq-sleutel ontvangen; er zijn geen services gestart.') from None
        if not key:
            raise StartError('Geen Orq-sleutel ingevoerd; er zijn geen services gestart.')
        try:
            key = load_api_key({'ORQ_API_KEY': key})
        except ValueError as failure:
            raise StartError(str(failure)) from None
    if not supplied.get('ORQ_API_KEY', '').strip() and supplied.get('ORQ_API_KEY_FILE'):
        return Path(supplied['ORQ_API_KEY_FILE']).expanduser().resolve(), False
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', prefix='orq-', suffix='.key', dir=session, delete=False) as output:
        output.write(key)
        return Path(output.name), True


def check_ports(ports):
    if len(set(ports)) != len(ports) or any(not 1 <= port <= 65535 for port in ports):
        raise StartError('Kies vier verschillende geldige poorten.')
    for port in ports:
        try:
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', port))
        except OSError:
            raise StartError(f'Poort {port} is bezet. Stop zelf de betreffende service of kies andere --*-port opties; ./start stopt geen bestaande processen.') from None


def check_tools():
    if sys.platform not in {'darwin', 'linux'}:
        raise StartError('De bewaakte launcher ondersteunt macOS en Linux; zie docs/LOCAL_SETUP.md.')
    for executable in ('cargo', 'rustup', 'node', 'npm', 'ps'):
        if shutil.which(executable) is None:
            raise StartError(f'{executable} ontbreekt. Installeer de vereisten uit docs/LOCAL_SETUP.md.')
    node = subprocess.run(['node', '--version'], capture_output=True, text=True, check=True, env=clean_environment(os.environ)).stdout.strip()
    version = tuple(int(part) for part in node.lstrip('v').split('.')[:2])
    if not (version >= (22, 12) or (version[0] == 20 and version[1] >= 19)):
        raise StartError('Node.js22.12+ (of20.19+) is vereist.')
    rust = subprocess.run(['rustup', 'run', '1.94.1', 'cargo', '--version'], capture_output=True, env=clean_environment(os.environ))
    if rust.returncode:
        raise StartError('Rust1.94.1 ontbreekt. Installeer de vereisten uit docs/LOCAL_SETUP.md.')


def newer_than(output, sources):
    return not output.is_file() or any(path.is_file() and path.stat().st_mtime > output.stat().st_mtime for path in sources)


def prepare_builds(settings, environment, run=subprocess.run):
    root = settings['root']; env = clean_environment(environment)
    env.update({'CARGO_TARGET_DIR': str(settings['target']), 'CARGO_BUILD_JOBS': '2'})
    rust_sources = [root / 'backend/Cargo.toml', root / 'backend/Cargo.lock', *(root / 'backend/src').rglob('*.rs')]
    if newer_than(settings['binary'], rust_sources) or newer_than(settings['extractor'], rust_sources):
        print('Backend bouwen…', flush=True)
        run(['cargo', '+1.94.1', 'build', '--bins', '--locked', '--manifest-path', str(root / 'backend/Cargo.toml')], cwd=root, env=env, check=True)
    if not all(file.is_file() for file in (settings['binary'], settings['extractor'])):
        raise StartError('De zoekbackend of documentextractor ontbreekt na de build.')
    frontend = root / 'frontend'
    lock = frontend / 'package-lock.json'; installed = frontend / 'node_modules/.package-lock.json'
    if newer_than(installed, [lock, frontend / 'package.json']):
        print('Frontenddependencies installeren…', flush=True)
        run(['npm', 'ci', '--no-audit', '--no-fund'], cwd=frontend, env=env, check=True)
    if newer_than(frontend / 'dist/index.html', [frontend / 'package.json', lock, *(frontend / 'src').rglob('*')]):
        print('Frontend bouwen…', flush=True)
        run(['npm', 'run', 'build'], cwd=frontend, env=env, check=True)


class OwnedProcesses:
    def __init__(self, directory, root):
        self.directory, self.root = directory, root
        self.children = []
        self.build_count = 0

    def __enter__(self): return self
    def __exit__(self, *_): self.stop()

    def start(self, label, command, environment, cwd=None):
        log_path = self.directory / f'{label}.log'
        with log_path.open('w') as log:
            os.chmod(log_path, 0o600)
            process = subprocess.Popen(command, cwd=cwd or self.root, env=environment, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        self.children.append((label, process, log_path))
        return process

    def run_checked(self, command, cwd, env, check=True):
        label = f'build-{self.build_count}'
        self.build_count += 1
        process = self.start(label, command, env, cwd)
        code = process.wait()
        if code and check: raise StartError(f'Build mislukt; zie {self.directory / (label + ".log")}.')
        # Dispose completed build groups immediately, so stale PIDs are never retained.
        self.stop_one(label, process)
        self.children.pop()
        return subprocess.CompletedProcess(command, code)

    def check_alive(self):
        for label, process, path in self.children:
            if not label.startswith('build-') and process.poll() is not None:
                raise StartError(f'{label} is gestopt. Zie {path}. De overige eigen services worden opgeruimd.')

    def group_alive(self, pgid):
        rows = subprocess.check_output(['ps', '-axo', 'pgid='], text=True, timeout=3,
                                       env=clean_environment(os.environ))
        return pgid in {int(value) for value in rows.split()}

    def stop_one(self, label, process):
        for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGKILL):
            process.poll()
            if not self.group_alive(process.pid): break
            try: os.killpg(process.pid, sig)
            except ProcessLookupError: break
            except PermissionError:
                if not self.group_alive(process.pid): break
                raise
            deadline = time.monotonic() + (12 if label == 'backend' and sig == signal.SIGINT else 2)
            while time.monotonic() < deadline:
                process.poll()
                if not self.group_alive(process.pid): break
                time.sleep(.05)
            else: continue
            break
        try: process.wait(timeout=2)
        except subprocess.TimeoutExpired: pass

    def stop(self):
        for label, process, _ in reversed(self.children):
            self.stop_one(label, process)
        self.children.clear()


def native_slot_path():
    base = Path.home() / 'Library/Caches' if sys.platform == 'darwin' else Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache'))
    return base / 'adami-case/native-model.lock'


class NativeSlot:
    def __init__(self, path): self.path, self.file = path, None
    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = os.fdopen(os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600), 'r+')
        try: fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.file.close(); self.file = None
            raise StartError('Er draait al een Mike-launcher. Stop die zelf voordat je een tweede model start.') from None
        return self
    def close(self):
        if self.file is not None: self.file.close(); self.file = None
    def __exit__(self, *_): self.close()


def check_no_native_jobs():
    rows = subprocess.check_output(['ps', '-axo', 'pid=,command='], text=True, timeout=3, env=clean_environment(os.environ))
    for row in rows.splitlines():
        fields = row.strip().split(None, 1)
        if len(fields) != 2: continue
        try: command = shlex.split(fields[1])
        except ValueError: continue
        if not command: continue
        executable = Path(command[0]).name
        guard = executable.lower().startswith('python') and any(Path(part).name == 'resource_guard.py' for part in command[1:4])
        model = executable == 'texas-case-finder' or (executable.startswith('texas_case_finder-') and '--ignored' in command)
        if guard or model:
            raise StartError('Er draait al een native modeltaak. Stop de eigenaar zelf; ./start start geen tweede model en stopt geen ander proces.')


def wait_json(url, owned, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        owned.check_alive()
        try:
            with request.urlopen(url, timeout=2) as response:
                value = json.load(response)
            if isinstance(value, dict): return value
        except (OSError, ValueError, error.URLError): pass
        time.sleep(.2)
    raise StartError(f'Starten duurde te lang: {url}. Alleen de eigen services worden gestopt.')


def run(args):
    key_path = None; owned_key = False; slot = None
    try:
        settings = local_settings(ROOT, os.environ)
        check_ports([args.backend_port, args.orq_port, args.mike_port, args.eval_port])
        check_tools()
        slot = NativeSlot(native_slot_path()); slot.__enter__()
        check_no_native_jobs()
        manifest = validate_index(settings)
        base = os.environ.get('ORQ_BASE_URL', 'https://my.orq.ai/v3/router').rstrip('/')
        provider_endpoint(base)
        sessions = ROOT / '.cache/starts'; sessions.mkdir(parents=True, exist_ok=True)
        session = Path(tempfile.mkdtemp(prefix='mike-', dir=sessions)); os.chmod(session, 0o700)
        key_path, owned_key = credential(os.environ, args.orq_key_file, session)
        # Also protect OS browser helpers that inherit this process environment.
        os.environ.pop('ORQ_API_KEY', None); os.environ.pop('ORQ_API_KEY_FILE', None)
        common = clean_environment(os.environ)
        common.update({'ADAMI_DB_PATH': str(settings['database']), 'ADAMI_CACHE_DIR': str(settings['cache']),
                       'ADAMI_BIND_ADDR': f'127.0.0.1:{args.backend_port}',
                       'ADAMI_CORS_ORIGINS': f'http://127.0.0.1:{args.mike_port},http://localhost:{args.mike_port}',
                       'ORQ_BASE_URL': base})
        backend = f'http://127.0.0.1:{args.backend_port}'
        gateway = f'http://127.0.0.1:{args.orq_port}'
        mike = f'http://127.0.0.1:{args.mike_port}/'; evals = f'http://127.0.0.1:{args.eval_port}/'
        server_env = {**common, 'ORQ_API_KEY_FILE': str(key_path)}
        with OwnedProcesses(session, ROOT) as owned:
            prepare_builds(settings, os.environ, owned.run_checked)
            owned.start('backend', [sys.executable, str(ROOT / 'backend/scripts/resource_guard.py'), '--label', 'mike-start', '--serve-preview', '--timeout-seconds', '7200', '--report', str(session / 'guard.json'), '--log', str(session / 'model.log'), '--', str(settings['binary']), 'serve'], common)
            health = wait_json(backend + '/api/health', owned)
            if health.get('status') != 'ready' or health.get('corpus_version') != manifest['corpus_version']:
                raise StartError('De backend bevestigt de ingestelde index niet.')
            owned.start('orq', [sys.executable, str(ROOT / 'backend/scripts/orq_proxy.py'), '--backend', backend, '--port', str(args.orq_port)], {**server_env, 'ADAMI_DOCUMENT_EXTRACTOR': str(settings['extractor'])})
            wait_json(gateway + '/api/models', owned)
            wait_json(gateway + '/api/health', owned)
            owned.start('evals', [sys.executable, str(ROOT / 'backend/scripts/evals_web.py'), '--port', str(args.eval_port), '--backend', backend, '--database', str(settings['database']), '--model-cache', str(settings['cache']), '--corpus', str(settings['corpus']), '--outputs', str(ROOT / '.cache/eval-runs')], server_env)
            if not wait_json(evals + 'api/evals', owned).get('judge_available'):
                raise StartError('De evaluatieserver heeft de Orq-configuratie niet geladen.')
            frontend_env = {**common, 'VITE_API_MODE': 'api', 'VITE_API_BASE_URL': gateway}
            owned.start('mike', ['node', str(ROOT / 'frontend/node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', str(args.mike_port), '--strictPort'], frontend_env, ROOT / 'frontend')
            deadline = time.monotonic() + 45
            while True:
                owned.check_alive()
                try:
                    with request.urlopen(mike, timeout=2) as response:
                        if response.status == 200: break
                except (OSError, error.URLError): pass
                if time.monotonic() >= deadline: raise StartError('Mike is niet tijdig gestart.')
                time.sleep(.2)
            print(f'Mike: {mike}\nEvaluaties: {evals}\nCtrl+C stopt alleen deze services. Backendbewaking: maximaal2uur.\nLogs: {session}', flush=True)
            if not args.no_open:
                webbrowser.open(mike); webbrowser.open(evals)
            while True:
                owned.check_alive(); time.sleep(.5)
    except KeyboardInterrupt:
        print('\nMike en de eigen services zijn gestopt.', flush=True)
        return 0
    except (StartError, OSError, ValueError, subprocess.SubprocessError) as failure:
        print(f'Starten mislukt: {failure}', file=sys.stderr)
        return 1
    finally:
        if owned_key and key_path is not None: key_path.unlink(missing_ok=True)
        if slot is not None: slot.close()


def main(argv=None):
    args = parse_args(argv)
    previous = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
    def stop(_signal, _frame):
        for sig in previous: signal.signal(sig, signal.SIG_IGN)
        raise KeyboardInterrupt()
    for sig in previous: signal.signal(sig, stop)
    try: return run(args)
    finally:
        for sig, handler in previous.items(): signal.signal(sig, handler)
