"""Standard-library HTTP bridge to isolated system-browser JavaScript workers.

Part of veusz-js-engine. Licensed under the Apache License 2.0.

Only trusted local JavaScript is supported (this is not a security sandbox).
``run`` uses indirect eval: eval's top-level let/const do not persist. ``run_file``
uses classic importScripts, preserving script global lexical declarations.
"""
import atexit
import json
import math
import os
from pathlib import Path
import queue
import secrets
import shutil
import signal
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit


_ASSETS = Path(__file__).resolve().parent / 'browser_host'
_CSP = ("default-src 'none'; script-src 'self' blob: 'unsafe-eval'; "
        "worker-src 'self' blob:; connect-src 'self'; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'none'")


class BrowserSession:
    """One private browser process/profile, with one Worker per runtime.

    Construction validates configuration but does not launch anything. report()
    returns a JSON-serializable dictionary. A failed/closed session cannot restart.
    """

    def __init__(self, error_type=RuntimeError):
        self.error_type = error_type
        try:
            self.timeout = float(os.environ.get('VEUSZ_JS_ENGINE_BROWSER_TIMEOUT', '30'))
            if not math.isfinite(self.timeout) or self.timeout <= 0:
                raise ValueError('timeout must be finite and positive')
            self.mode = os.environ.get('VEUSZ_JS_ENGINE_BROWSER_MODE', 'headless')
            if self.mode not in ('headless', 'visible'):
                raise ValueError('mode must be headless or visible')
            self.executable = os.environ.get('VEUSZ_JS_ENGINE_BROWSER')
            if self.executable is not None:
                if not self.executable or not Path(self.executable).is_file():
                    raise ValueError('VEUSZ_JS_ENGINE_BROWSER must be an existing browser executable path')
                self.executable = str(Path(self.executable).resolve())
        except (ValueError, OSError) as exc:
            raise error_type('Invalid browser configuration: ' + str(exc)) from exc
        self._lock = threading.RLock()
        self._start_lock = threading.Lock()
        self._rpc_lock = threading.Lock()
        self._cleanup_lock = threading.Lock()
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._tasks = queue.Queue()
        self._pending = {}
        self._runtimes = {}
        self._state = 'new'
        self._failure = None
        self._client = None
        self._last_seen = None
        self._token = secrets.token_urlsafe(32)
        self._server = None
        self._process = None
        self._temp = None
        self._log = None
        self._temp_path = None
        self._cleanup_errors = []
        self._url = None
        self._pid = None
        self._returncode = None
        atexit.register(self.close)

    def _check(self):
        with self._lock:
            if self._failure or self._stop.is_set():
                raise self.error_type(self._failure or 'Browser session is closed')

    def _detect_browser(self):
        if self.executable:
            return self.executable
        roots = [os.environ.get(n, '') for n in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA')]
        if os.name == 'nt':
            # Frozen launchers/sanitized environments can omit ProgramFiles.
            # Keep the normal Windows install locations as a discovery fallback.
            drive = os.environ.get('SYSTEMDRIVE', 'C:') + '\\'
            roots.extend([str(Path(drive) / 'Program Files'),
                          str(Path(drive) / 'Program Files (x86)')])
            try:
                roots.append(str(Path.home() / 'AppData' / 'Local'))
            except RuntimeError:
                pass  # A completely sanitized environment may also omit HOME.
        groups = [(['firefox', 'firefox.exe'], ['Mozilla Firefox/firefox.exe'],
                   ['/Applications/Firefox.app/Contents/MacOS/firefox']),
                  (['msedge', 'microsoft-edge', 'msedge.exe'], ['Microsoft/Edge/Application/msedge.exe'],
                   ['/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge']),
                  (['google-chrome', 'chromium', 'chromium-browser', 'chrome', 'chrome.exe'],
                   ['Google/Chrome/Application/chrome.exe'],
                   ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'])]
        for names, suffixes, absolute in groups:
            for name in names:
                found = shutil.which(name)
                if found:
                    return found
            for candidate in [str(Path(r) / s) for r in roots if r for s in suffixes] + absolute:
                if Path(candidate).is_file():
                    return candidate
        raise self.error_type('No Firefox, Edge or Chrome found; set VEUSZ_JS_ENGINE_BROWSER to its executable')

    def _start(self):
        with self._start_lock:
            self._check()
            if self._state == 'running':
                return
            try:
                self.executable = self._detect_browser()
                # Serialize resource creation against concurrent close().
                with self._cleanup_lock:
                    self._check()
                    self._state = 'starting'
                    # Own cleanup explicitly: TemporaryDirectory's weakref exit
                    # finalizer may run BEFORE our atexit browser shutdown.
                    self._temp = tempfile.mkdtemp(prefix='veusz-js-browser-')
                    self._temp_path = self._temp
                    profile = Path(self._temp) / 'profile'
                    profile.mkdir()
                    self._log = (Path(self._temp) / 'browser.log').open('ab')
                    self._server = self._make_server()
                    self._url = 'http://127.0.0.1:%d' % self._server.server_port
                    threading.Thread(target=self._server.serve_forever,
                                     kwargs={'poll_interval': 0.1}, daemon=True,
                                     name='veusz-js-http').start()
                    url = self._url + '/?token=' + self._token
                    firefox = 'firefox' in Path(self.executable).name.lower()
                    if firefox:
                        args = [self.executable, '-no-remote', '-new-instance', '-profile', str(profile)]
                        if self.mode == 'headless':
                            args.append('-headless')
                        args.append(url)
                    else:
                        args = [self.executable, '--user-data-dir=' + str(profile), '--no-first-run',
                                '--no-default-browser-check', '--disable-background-mode',
                                '--disable-extensions']
                        if self.mode == 'headless':
                            args.append('--headless=new')
                        args.append(url)
                    options = {'stdout': self._log, 'stderr': self._log, 'stdin': subprocess.DEVNULL}
                    if os.name == 'nt':
                        options['creationflags'] = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
                    else:
                        options['start_new_session'] = True
                    self._process = subprocess.Popen(args, **options)
                    self._pid = self._process.pid
                threading.Thread(target=self._monitor, daemon=True, name='veusz-js-monitor').start()
                deadline = time.monotonic() + 60
                while not self._ready.wait(0.1):
                    self._check()
                    if time.monotonic() >= deadline:
                        raise self.error_type('Browser startup timed out after 60 seconds')
                self._check()
                with self._lock:
                    self._check()
                    self._state = 'running'
            except Exception as exc:
                self._fail('Browser startup failed: ' + str(exc))
                raise self.error_type(self._failure) from exc

    def _monitor(self):
        while not self._stop.wait(0.2):
            proc = self._process
            if proc is None:
                return
            code = proc.poll()
            if code is not None:
                self._returncode = code
                self._fail('Browser process exited (status %s)' % code)
                return
            with self._lock:
                stale = self._last_seen is not None and time.monotonic() - self._last_seen > 15
            if stale:
                self._fail('Browser page disconnected (no heartbeat for 15 seconds)')
                return

    def _make_server(self):
        session = self
        assets = {key: (_ASSETS / name).read_bytes() for key, name in
                  [('/', 'index.html'), ('/page.js', 'page.js'), ('/worker.js', 'worker.js')]}
        # The bootstrap page supplies credentials to its sole external script.
        assets['/'] = assets['/'].replace(b'__SESSION_TOKEN__', self._token.encode('ascii'))

        class Server(ThreadingHTTPServer):
            daemon_threads = True
            block_on_close = False

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(5)

            def log_message(self, *args):
                pass

            def reply(self, status, value, mime='application/json'):
                body = value if isinstance(value, bytes) else json.dumps(value).encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type', mime)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Referrer-Policy', 'no-referrer')
                policy = _CSP
                if urlsplit(self.path).path == '/worker.js':
                    policy = policy.replace("connect-src 'self'", "connect-src 'none'").replace(
                        "worker-src 'self' blob:", "worker-src 'none'")
                self.send_header('Content-Security-Policy', policy)
                self.end_headers()
                try:
                    self.wfile.write(body)
                except OSError:
                    pass

            def permitted(self, client=True):
                host = '127.0.0.1:%d' % self.server.server_port
                if self.headers.get('Host') != host or self.headers.get('Origin', 'http://' + host) != 'http://' + host:
                    self.reply(403, {'error': 'host/origin'})
                    return False
                if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                    self.reply(403, {'error': 'cross-site'})
                    return False
                query = parse_qs(urlsplit(self.path).query)
                token = self.headers.get('X-Session-Token') or query.get('token', [''])[0]
                if not secrets.compare_digest(token.encode('utf-8'), session._token.encode('ascii')):
                    self.reply(403, {'error': 'token'})
                    return False
                with session._lock:
                    if session._stop.is_set():
                        self.reply(410, {'error': 'closed'})
                        return False
                    if client and (session._client is None or self.headers.get('X-Client-Id') != session._client):
                        self.reply(409, {'error': 'client'})
                        return False
                    if client:
                        session._last_seen = time.monotonic()
                return True

            def do_GET(self):
                path = urlsplit(self.path).path
                if not self.permitted(client=path not in assets):
                    return
                if path in assets:
                    mime = 'text/html; charset=utf-8' if path == '/' else 'text/javascript; charset=utf-8'
                    self.reply(200, assets[path], mime)
                elif path == '/task':
                    try:
                        task = session._tasks.get(timeout=1)
                    except queue.Empty:
                        task = None
                    self.reply(410 if session._stop.is_set() else 200, task)
                else:
                    self.reply(404, {'error': 'not found'})

            def do_POST(self):
                path = urlsplit(self.path).path
                if not self.permitted(client=path != '/hello'):
                    return
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= 64 * 1024 * 1024:
                        raise ValueError('body size')
                    body = json.loads(self.rfile.read(length))
                    if not isinstance(body, dict):
                        raise ValueError('object expected')
                except (ValueError, OSError):
                    self.reply(400, {'error': 'invalid body'})
                    return
                if path == '/hello':
                    client = self.headers.get('X-Client-Id')
                    with session._lock:
                        if not client or len(client) > 128 or session._client is not None:
                            self.reply(409, {'error': 'client already attached'})
                            return
                        session._client = client
                        session._last_seen = time.monotonic()
                        session._ready.set()
                    self.reply(200, {})
                elif path == '/result':
                    with session._lock:
                        ident = body.get('id')
                        target = session._pending.get(ident) if isinstance(ident, str) else None
                        if target is None or body.get('runtime') != target[0] or target[1].full():
                            self.reply(409, {'error': 'unknown task'})
                            return
                        target[1].put_nowait(body)
                    self.reply(200, {})
                else:
                    self.reply(404, {'error': 'not found'})

        return Server(('127.0.0.1', 0), Handler)

    def _rpc(self, op, runtime, **payload):
        # Preserve script ordering, including concurrent Python callers.
        with self._rpc_lock:
            self._check()
            ident = secrets.token_hex(16)
            answer = queue.Queue(maxsize=1)
            with self._lock:
                self._check()
                self._pending[ident] = (runtime, answer)
                self._tasks.put(dict(id=ident, runtime=runtime, op=op, **payload))
            try:
                try:
                    reply = answer.get(timeout=self.timeout)
                except queue.Empty:
                    self._fail('Browser RPC %s timed out after %gs; session invalidated' % (op, self.timeout))
                    raise self.error_type(self._failure) from None
                self._check()
                if 'error' in reply:
                    raise self.error_type(str(reply['error']).replace(self._token, '<redacted>'))
                if not isinstance(reply.get('value'), str):
                    self._fail('Invalid browser RPC result')
                    raise self.error_type(self._failure)
                return reply['value']
            finally:
                with self._lock:
                    self._pending.pop(ident, None)

    def create_runtime(self, label):
        self._start()
        ident = secrets.token_hex(16)
        runtime = _BrowserRuntime(self, ident, str(label))
        self._rpc('create', ident, label=runtime.label)
        with self._lock:
            self._check()
            self._runtimes[ident] = runtime
        return runtime

    def _fail(self, message):
        with self._lock:
            if self._stop.is_set():
                return
            self._failure = str(message).replace(self._token, '<redacted>')
        self.close()

    def close(self):
        """Invalidate waiters immediately; terminate only this session's process tree."""
        with self._lock:
            self._stop.set()
            self._state = 'failed' if self._failure else 'closed'
            self._ready.set()
            self._tasks.put(None)
            for _, target in self._pending.values():
                if not target.full():
                    target.put_nowait({'error': self._failure or 'Browser session is closed'})
        with self._cleanup_lock:
            proc = self._process
            if proc is not None:
                try:
                    if os.name == 'nt':
                        # Never kill by executable name, nor by a PID already reaped.
                        if proc.poll() is None:
                            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                                           stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                           stderr=subprocess.DEVNULL, timeout=3,
                                           creationflags=subprocess.CREATE_NO_WINDOW, check=False)
                    else:
                        try:
                            os.killpg(proc.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    if proc.poll() is None:
                        proc.kill()
                    self._returncode = proc.wait(timeout=2)
                except (OSError, subprocess.SubprocessError) as exc:
                    self._cleanup_errors.append('process: ' + str(exc))
                self._process = None
            if self._server is not None:
                self._server.shutdown()
                self._server.server_close()
                self._server = None
            if self._log is not None:
                self._log.close()
                self._log = None
            if self._temp is not None:
                try:
                    shutil.rmtree(self._temp)
                except OSError as exc:
                    self._cleanup_errors.append('temporary directory retained at %s: %s' % (self._temp_path, exc))
                self._temp = None
            atexit.unregister(self.close)

    def report(self):
        """Return status suitable for json.dumps; never expose session credentials."""
        with self._lock:
            return {'backend': 'browser-http', 'state': self._state, 'error': self._failure,
                    'browser': self.executable, 'mode': self.mode, 'timeout': self.timeout,
                    'pid': self._pid, 'returncode': self._returncode, 'url': self._url,
                    'connected': self._client is not None and not self._stop.is_set(),
                    'runtimes': [{'id': r.ident, 'label': r.label, 'closed': r._closed or self._stop.is_set()}
                                 for r in self._runtimes.values()],
                    'temporary_directory': self._temp_path,
                    'temporary_directory_retained': bool(self._temp_path and Path(self._temp_path).exists()),
                    'cleanup_errors': list(self._cleanup_errors)}


class _BrowserRuntime:
    def __init__(self, session, ident, label):
        self.session, self.ident, self.label = session, ident, label
        self._closed = False

    def _rpc(self, op, **payload):
        if self._closed:
            raise self.session.error_type('Browser runtime is closed: ' + self.label)
        return self.session._rpc(op, self.ident, **payload)

    def run(self, source, name='<javascript>'):
        if isinstance(source, bytes):
            try:
                source = source.decode('utf-8')
            except UnicodeError as exc:
                raise self.session.error_type('JavaScript source must be UTF-8: ' + str(exc)) from exc
        return self._rpc('eval', source=str(source), name=str(name))

    def run_file(self, path):
        try:
            filename = Path(path).resolve()
            source = filename.read_text(encoding='utf-8-sig')
        except (OSError, ValueError, UnicodeError) as exc:
            raise self.session.error_type('Cannot read JavaScript file %s: %s' % (path, exc)) from exc
        return self._rpc('load', source=source, name=filename.as_uri())

    def call(self, fn_name, payload=''):
        return self._rpc('call', fn_name=str(fn_name), payload=str(payload))

    def close(self):
        if self._closed:
            return
        try:
            if not self.session._stop.is_set():
                self._rpc('close')
        finally:
            self._closed = True
            with self.session._lock:
                self.session._runtimes.pop(self.ident, None)
