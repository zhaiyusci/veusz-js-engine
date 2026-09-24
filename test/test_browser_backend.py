"""Browser backend contract tests, with no third-party Python dependencies.

    python -S -m unittest discover -s test -p test_browser_backend.py

Mocked platform and browserless production HTTP tests run by default. Set
VEUSZ_TEST_BROWSER=1 to exercise a real browser; each real-browser class
owns one session.
"""
import http.client
import importlib
import json
import queue
import threading
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
WITH_BROWSER = os.environ.get('VEUSZ_TEST_BROWSER') == '1'


class BrowserDiscoveryTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Windows discovery fallback')
    def test_standard_install_found_without_programfiles_environment(self):
        from browser_backend import BrowserSession
        expected = Path('Z:/Program Files/Mozilla Firefox/firefox.exe')
        with mock.patch.dict(os.environ, {'SYSTEMDRIVE': 'Z:'}, clear=True), \
                mock.patch('browser_backend.shutil.which', return_value=None), \
                mock.patch.object(Path, 'is_file', lambda path: path == expected):
            session = BrowserSession()
            self.addCleanup(session.close)
            self.assertEqual(Path(session._detect_browser()), expected)


class BackendSelectionTests(unittest.TestCase):
    """No DLL, browser executable, Qt, or Veusz is needed by these tests."""

    @classmethod
    def setUpClass(cls):
        with mock.patch.dict(os.environ, {'VEUSZ_JS_ENGINE_DEFER': '1'}):
            cls.platform_module = importlib.import_module('veusz_js_engine')
        cls.script = PROJECT / 'jsapi.js'

    def setUp(self):
        self.env = mock.patch.dict(os.environ)
        self.env.start()
        self.addCleanup(self.env.stop)
        os.environ.pop('VEUSZ_JS_ENGINE_BACKEND', None)
        os.environ.pop('VEUSZ_JS_ENGINE_QUICKJS', None)
        self.session = mock.Mock(name='browser_session')
        self.session.report.return_value = {}
        self.handles = []

        def create_runtime(label):
            handle = mock.Mock(name='browser_runtime_' + str(len(self.handles)))
            handle.run.return_value = 'true'
            self.handles.append(handle)
            return handle

        self.session.create_runtime.side_effect = create_runtime
        patcher = mock.patch.object(self.platform_module, '_new_browser_session',
                                    return_value=self.session)
        self.new_session = patcher.start()
        self.addCleanup(patcher.stop)
        # Fail closed if a regression tries to load a native library.
        patcher = mock.patch.object(self.platform_module, '_QuickJS')
        self.quickjs = patcher.start()
        self.quickjs.return_value.run.return_value = 'true'
        self.addCleanup(patcher.stop)

    def test_default_platform_ignores_broken_quickjs_setting(self):
        os.environ['VEUSZ_JS_ENGINE_QUICKJS'] = str(PROJECT / 'missing-qjs.dll')
        with mock.patch.object(self.platform_module, 'find_quickjs',
                               side_effect=AssertionError('browser searched QuickJS')):
            platform = self.platform_module.Platform(PROJECT)
            self.addCleanup(platform.close_all)
            runtime = platform.runtime(self.script)
            self.assertEqual(runtime.backend, 'browser')
            self.assertFalse(runtime.started)
            runtime.start()
            self.assertTrue(runtime.started)
            self.new_session.assert_called_once()
            self.session.create_runtime.assert_called_once()
            self.quickjs.assert_not_called()

    def test_default_standalone_runtime_uses_browser(self):
        runtime = self.platform_module.Runtime(self.script)
        self.addCleanup(runtime.close)
        self.assertEqual(runtime.backend, 'browser')
        runtime.start()
        self.new_session.assert_called_once()
        self.quickjs.assert_not_called()

    def test_unknown_backend_is_an_error(self):
        for backend in ('typo', 'chromium', 'auto'):
            with self.subTest(backend=backend):
                with self.assertRaises(self.platform_module.JsEngineError):
                    self.platform_module.Runtime(self.script, backend=backend)
                with self.assertRaises(self.platform_module.JsEngineError):
                    self.platform_module.Platform(PROJECT, backend=backend)
        self.new_session.assert_not_called()
        self.quickjs.assert_not_called()

    def test_unknown_environment_backend_is_an_error(self):
        os.environ['VEUSZ_JS_ENGINE_BACKEND'] = 'not-an-engine'
        with self.assertRaises(self.platform_module.JsEngineError):
            self.platform_module.Platform(PROJECT)
        with self.assertRaises(self.platform_module.JsEngineError):
            self.platform_module.Runtime(self.script)

    def test_explicit_engine_preserves_quickjs_compatibility(self):
        engine = PROJECT / 'mock-qjs.dll'
        runtime = self.platform_module.Runtime(self.script, engine=engine)
        self.addCleanup(runtime.close)
        self.assertEqual(runtime.backend, 'quickjs')
        runtime.start()
        self.quickjs.assert_called_once_with(engine, self.script)
        self.new_session.assert_not_called()
        runtime.close()
        runtime.close()
        self.quickjs.return_value.close.assert_called_once()
        self.assertFalse(runtime.started)

    def test_browser_environment_overrides_legacy_engine_hint(self):
        os.environ['VEUSZ_JS_ENGINE_BACKEND'] = 'browser'
        runtime = self.platform_module.Runtime(self.script, engine='unused.dll')
        self.addCleanup(runtime.close)
        self.assertEqual(runtime.backend, 'browser')
        runtime.start()
        self.quickjs.assert_not_called()
        self.new_session.assert_called_once()

    def test_explicit_backend_overrides_environment(self):
        os.environ['VEUSZ_JS_ENGINE_BACKEND'] = 'browser'
        runtime = self.platform_module.Runtime(
            self.script, engine='mock-qjs.dll', backend='quickjs')
        self.addCleanup(runtime.close)
        runtime.start()
        self.assertEqual(runtime.backend, 'quickjs')
        self.quickjs.assert_called_once()
        self.new_session.assert_not_called()

    def test_explicit_quickjs_platform_selects_and_closes_native_runtime(self):
        engine = PROJECT / 'mock-qjs.dll'
        with mock.patch.object(self.platform_module, 'find_quickjs',
                               return_value=engine) as find:
            platform = self.platform_module.Platform(PROJECT, backend='quickjs')
            self.addCleanup(platform.close_all)
            runtime = platform.runtime(self.script)
            runtime.start()
            self.assertEqual(runtime.backend, 'quickjs')
            self.assertTrue(find.called)
            self.quickjs.assert_called_once()
            self.new_session.assert_not_called()
            platform.close_all()
            self.quickjs.return_value.close.assert_called_once()
            self.assertEqual(platform.runtimes(), {})

    def test_quickjs_environment_selects_native_platform(self):
        os.environ['VEUSZ_JS_ENGINE_BACKEND'] = 'quickjs'
        with mock.patch.object(self.platform_module, 'find_quickjs',
                               return_value=PROJECT / 'mock-qjs.dll'):
            platform = self.platform_module.Platform(PROJECT)
            self.addCleanup(platform.close_all)
            runtime = platform.runtime(self.script)
            runtime.start()
            self.assertEqual(runtime.backend, 'quickjs')
            self.quickjs.assert_called_once()
            self.new_session.assert_not_called()

    def test_platform_shares_session_and_closes_all_handles(self):
        platform = self.platform_module.Platform(PROJECT, backend='browser')
        self.addCleanup(platform.close_all)
        first = platform.runtime(self.script)
        second = platform.runtime(PROJECT / 'features' / 'mathjax' / 'feature.js')
        self.assertIs(platform.runtime(self.script), first)
        first.start()
        second.start()
        self.new_session.assert_called_once()
        self.assertEqual(self.session.create_runtime.call_count, 2)
        first.close()
        self.handles[0].close.assert_called_once()
        self.handles[1].close.assert_not_called()
        self.session.close.assert_not_called()
        self.assertTrue(second.started)
        platform.close_all()
        self.handles[1].close.assert_called_once()
        self.session.close.assert_called_once()
        self.assertEqual(platform.runtimes(), {})

    def test_standalone_runtime_closes_owned_session(self):
        runtime = self.platform_module.Runtime(self.script, backend='browser')
        self.addCleanup(runtime.close)
        runtime.start()
        runtime.close()
        runtime.close()
        self.handles[0].close.assert_called_once()
        self.session.close.assert_called_once()
        self.assertFalse(runtime.started)

    def test_injected_session_is_not_owned_by_runtime(self):
        runtime = self.platform_module.Runtime(
            self.script, backend='browser', browser_session=self.session)
        self.addCleanup(runtime.close)
        runtime.start()
        runtime.close()
        self.handles[0].close.assert_called_once()
        self.session.close.assert_not_called()
        self.new_session.assert_not_called()

    def launch_thread(self, operation):
        outcomes = queue.Queue()

        def invoke():
            try:
                outcomes.put(operation())
            except Exception as exc:
                outcomes.put(exc)

        thread = threading.Thread(target=invoke, daemon=True)
        thread.start()
        self.addCleanup(thread.join, 3)
        return thread, outcomes

    def finish_thread(self, thread, outcomes):
        thread.join(3)
        self.assertFalse(thread.is_alive(), 'lifecycle operation deadlocked')
        return outcomes.get(timeout=1)

    def test_close_during_session_factory_does_not_leak_new_session(self):
        entered, release = threading.Event(), threading.Event()

        def factory():
            entered.set()
            if not release.wait(3):
                raise AssertionError('test did not release factory')
            return self.session

        self.new_session.side_effect = factory
        runtime = self.platform_module.Runtime(self.script, backend='browser')
        self.addCleanup(runtime.close)
        starter, start_result = self.launch_thread(runtime.start)
        self.addCleanup(release.set)
        self.assertTrue(entered.wait(3))
        closer, close_result = self.launch_thread(runtime.close)
        self.addCleanup(release.set)
        self.assertTrue(runtime._closing.wait(3))
        release.set()
        self.assertIsInstance(self.finish_thread(starter, start_result),
                              self.platform_module.JsEngineError)
        self.assertIsNone(self.finish_thread(closer, close_result))
        self.session.close.assert_called()
        self.session.create_runtime.assert_not_called()
        self.assertFalse(runtime.started)
        self.assertIsNone(runtime._browser_session)

    def test_close_interrupts_pending_runtime_creation_before_taking_lock(self):
        entered, interrupted = threading.Event(), threading.Event()
        self.session.close.side_effect = interrupted.set

        def create_runtime(label):
            entered.set()
            if not interrupted.wait(3):
                raise AssertionError('close failed to interrupt pending creation')
            raise self.platform_module.JsEngineError('session closed during create')

        self.session.create_runtime.side_effect = create_runtime
        runtime = self.platform_module.Runtime(self.script, backend='browser')
        self.addCleanup(runtime.close)
        starter, start_result = self.launch_thread(runtime.start)
        self.addCleanup(interrupted.set)
        self.assertTrue(entered.wait(3))
        closer, close_result = self.launch_thread(runtime.close)
        self.addCleanup(interrupted.set)
        error = self.finish_thread(starter, start_result)
        self.assertIsInstance(error, self.platform_module.JsEngineError)
        self.assertIn('session closed during create', str(error))
        self.assertIsNone(self.finish_thread(closer, close_result))
        self.assertFalse(runtime.started)
        self.assertIsNone(runtime._browser_session)

    def test_platform_close_during_factory_prevents_runtime_publication(self):
        entered, release = threading.Event(), threading.Event()

        def factory():
            entered.set()
            if not release.wait(3):
                raise AssertionError('test did not release factory')
            return self.session

        self.new_session.side_effect = factory
        platform = self.platform_module.Platform(PROJECT, backend='browser')
        self.addCleanup(platform.close_all)
        starter, start_result = self.launch_thread(lambda: platform.runtime(self.script))
        self.addCleanup(release.set)
        self.assertTrue(entered.wait(3))
        closer, close_result = self.launch_thread(platform.close_all)
        self.addCleanup(release.set)
        self.assertTrue(platform._closed.wait(3))
        release.set()
        self.assertIsInstance(self.finish_thread(starter, start_result),
                              self.platform_module.JsEngineError)
        self.assertIsNone(self.finish_thread(closer, close_result))
        self.session.close.assert_called()
        self.assertEqual(platform.runtimes(), {})
        self.assertIsNone(platform._browser_session)

    def test_closed_platform_cannot_create_runtime_or_feature(self):
        platform = self.platform_module.Platform(PROJECT, backend='browser')
        platform.close_all()
        for operation in (platform.runtime, platform.feature_runtime):
            with self.subTest(operation=operation.__name__):
                with self.assertRaisesRegex(self.platform_module.JsEngineError, 'closed'):
                    operation(self.script)
        self.new_session.assert_not_called()
        self.assertEqual(platform.runtimes(), {})

    def test_close_preserves_browser_report_and_records_cleanup_errors(self):
        report = {'state': 'closed', 'cleanup_errors': ['temporary directory retained']}
        self.session.report.return_value = report
        platform = self.platform_module.Platform(PROJECT, backend='browser')
        self.addCleanup(platform.close_all)
        platform.runtime(self.script).start()
        platform.close_all()
        self.assertEqual(platform.report()['browser'], report)
        self.assertTrue(any('temporary directory retained' in note
                            for note in platform.state.notes))
        platform.close_all()
        self.assertEqual(platform.report()['browser'], report)

    def test_initial_feature_script_failure_is_removed_from_cache(self):
        platform = self.platform_module.Platform(PROJECT, backend='browser')
        self.addCleanup(platform.close_all)
        entry = PROJECT / 'features' / 'mathjax' / 'feature.js'
        broken = mock.Mock()
        broken.run.return_value = 'true'
        # The API loads successfully; only the subsequent feature script fails.
        broken.run_file.side_effect = [None, self.platform_module.JsEngineError('bad feature')]
        healthy = mock.Mock()
        healthy.run.return_value = 'true'
        self.session.create_runtime.side_effect = [broken, healthy]
        with mock.patch.object(self.platform_module, '_js_load_order', return_value=[entry]), \
                mock.patch.object(self.platform_module, '_deferred_bundles', return_value={}):
            with self.assertRaisesRegex(self.platform_module.JsEngineError, 'bad feature'):
                platform.feature_runtime(entry)
            self.assertEqual(platform.runtimes(), {})
            broken.close.assert_called_once()
            self.session.close.assert_not_called()
            recovered = platform.feature_runtime(entry)
            self.assertTrue(recovered.started)
            self.assertIs(recovered._js, healthy)
            self.assertIn(entry.resolve(), platform.runtimes())
            self.assertEqual(healthy.run_file.call_count, 2)

    def test_load_failure_closes_created_handle(self):
        broken = mock.Mock()
        broken.run_file.side_effect = self.platform_module.JsEngineError('bad JS')
        self.session.create_runtime.side_effect = None
        self.session.create_runtime.return_value = broken
        runtime = self.platform_module.Runtime(self.script, backend='browser')
        self.addCleanup(runtime.close)
        with self.assertRaisesRegex(self.platform_module.JsEngineError, 'bad JS'):
            runtime.start()
        broken.close.assert_called_once()
        self.assertFalse(runtime.started)


class BrowserProcessCleanupTests(unittest.TestCase):
    def test_empty_job_rollback_owner_does_not_wait_for_nonexistent_process(self):
        from browser_backend import BrowserSession
        session = BrowserSession()
        self.addCleanup(session.close)
        owner = mock.Mock(pid=None)
        owner.report.return_value = {'mechanism': 'test-owner', 'tree_exited': True}
        session._process = owner
        session.close()
        owner.terminate_tree.assert_called_once()
        owner.wait.assert_not_called()
        owner.close_handles.assert_called_once()
        self.assertIsNone(session._process)
        self.assertEqual(session.report()['cleanup_errors'], [])

    def test_driver_closes_tree_even_when_root_has_exited(self):
        from browser_backend import BrowserSession
        session = BrowserSession()
        self.addCleanup(session.close)
        process = mock.Mock()
        process.poll.return_value = 0
        process.wait.return_value = 0
        process.report.return_value = {'mechanism': 'test-owner', 'tree_exited': True}
        session._process = process
        session.close()
        process.terminate_tree.assert_called_once()
        process.close_handles.assert_called_once()
        self.assertIsNone(session._process)
        self.assertEqual(session.report()['process_lifetime']['mechanism'], 'test-owner')

    def test_failed_cleanup_retains_owner_profile_and_can_retry(self):
        from browser_backend import BrowserSession
        session = BrowserSession()
        self.addCleanup(session.close)
        process = mock.Mock()
        process.terminate_tree.side_effect = [TimeoutError('tree alive'), None]
        process.wait.return_value = 1
        process.report.return_value = {'mechanism': 'test-owner'}
        session._process = process
        session._temp = session._temp_path = 'mock-owned-profile'
        with mock.patch('browser_backend.shutil.rmtree') as remove:
            session.close()
            self.assertIs(session._process, process)
            self.assertEqual(session._temp, 'mock-owned-profile')
            remove.assert_not_called()
            process.close_handles.assert_not_called()
            session.close()
            remove.assert_called_once_with('mock-owned-profile')
        self.assertIsNone(session._process)
        self.assertIsNone(session._temp)
        self.assertIn('tree alive', session.report()['cleanup_errors'][0])

    def test_launch_rollback_failure_adopts_owner_before_session_cleanup(self):
        import browser_backend
        session = browser_backend.BrowserSession()
        self.addCleanup(session.close)
        owner = mock.Mock(pid=123)
        owner.terminate_tree.side_effect = TimeoutError('still alive')
        owner.wait.return_value = 1
        owner.report.return_value = {'mechanism': 'test-owner'}
        failure = RuntimeError('launch rollback failed')
        failure.process_owner = owner
        server = mock.Mock(server_port=12345)
        with mock.patch.object(session, '_detect_browser', return_value='mock-browser'), \
                mock.patch.object(session, '_make_server', return_value=server), \
                mock.patch.object(browser_backend, '_launch_owned_process', side_effect=failure), \
                mock.patch.object(browser_backend.tempfile, 'mkdtemp', return_value='mock-profile'), \
                mock.patch.object(Path, 'mkdir'), mock.patch.object(Path, 'open'), \
                mock.patch.object(browser_backend.shutil, 'rmtree') as remove:
            with self.assertRaisesRegex(RuntimeError, 'launch rollback failed'):
                session._start()
            self.assertIs(session._process, owner)
            self.assertEqual(session._pid, 123)
            self.assertEqual(session._temp, 'mock-profile')
            remove.assert_not_called()
            owner.terminate_tree.side_effect = None
            session.close()
            remove.assert_called_once_with('mock-profile')

    def test_cleanup_diagnostics_redact_bootstrap_token(self):
        from browser_backend import BrowserSession
        session = BrowserSession()
        self.addCleanup(session.close)
        owner = mock.Mock()
        owner.terminate_tree.side_effect = [TimeoutError('argv token=' + session._token), None]
        owner.wait.return_value = 1
        owner.report.return_value = {'cleanup_errors': ['argv token=' + session._token]}
        session._process = owner
        session.close()
        self.assertNotIn(session._token, json.dumps(session.report()))
        session.close()
        self.assertNotIn(session._token, json.dumps(session.report()))

    def test_driver_load_failure_is_not_an_unowned_popen_fallback(self):
        import browser_backend
        with mock.patch.object(browser_backend.importlib.util, 'spec_from_file_location',
                               side_effect=OSError('missing lifetime driver')), \
                mock.patch.dict(sys.modules):
            sys.modules.pop('_veusz_browser_process_windows', None)
            sys.modules.pop('_veusz_browser_process_posix', None)
            with self.assertRaisesRegex(OSError, 'missing lifetime driver'):
                browser_backend._launch_owned_process(['never-execute'], None)


class BrowserHTTPTests(unittest.TestCase):
    """Exercise the production loopback HTTP handler without launching a browser."""

    @classmethod
    def setUpClass(cls):
        cls.backend = importlib.import_module('browser_backend')

    def setUp(self):
        environment = mock.patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        for name in ('VEUSZ_JS_ENGINE_BROWSER', 'VEUSZ_JS_ENGINE_BROWSER_MODE',
                     'VEUSZ_JS_ENGINE_BROWSER_TIMEOUT'):
            os.environ.pop(name, None)
        launcher = mock.patch.object(self.backend, '_launch_owned_process',
                                    side_effect=AssertionError('must not launch browser'))
        self.launcher = launcher.start()
        self.addCleanup(launcher.stop)
        self.addCleanup(self.launcher.assert_not_called)
        self.session = self.backend.BrowserSession(error_type=RuntimeError)
        self.server = self.session._make_server()
        self.session._server = self.server
        self.thread = threading.Thread(target=self.server.serve_forever,
                                       kwargs={'poll_interval': 0.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.thread.join, 3)
        self.addCleanup(self.session.close)
        self.host = '127.0.0.1:%d' % self.server.server_port
        self.client = 'test-client'

    def request(self, path, body=None, headers=None, authenticated=True):
        defaults = {'Host': self.host, 'Origin': 'http://' + self.host,
                    'X-Client-Id': self.client}
        if authenticated:
            defaults['X-Session-Token'] = self.session._token
        defaults.update(headers or {})
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port,
                                                timeout=3)
        try:
            connection.request('GET' if body is None else 'POST', path,
                               body=None if body is None else json.dumps(body),
                               headers=defaults)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def attach(self):
        self.assertEqual(self.request('/hello', {})[0], 200)

    def pending_rpc(self):
        result = queue.Queue()

        def invoke():
            try:
                result.put(self.session._rpc('eval', 'runtime-one', source='1+1'))
            except Exception as exc:
                result.put(exc)

        thread = threading.Thread(target=invoke, daemon=True)
        thread.start()
        # close must happen before joining even if an assertion fails.
        self.addCleanup(thread.join, 3)
        self.addCleanup(self.session.close)
        task = self.session._tasks.get(timeout=3)
        return task, thread, result

    def test_assets_require_token_and_accept_authenticated_bootstrap(self):
        for path in ('/', '/page.js', '/worker.js'):
            with self.subTest(path=path):
                self.assertEqual(self.request(path, authenticated=False)[0], 403)
                self.assertEqual(self.request(path, headers={
                    'X-Session-Token': 'wrong-token'})[0], 403)
                self.assertEqual(self.request(path)[0], 200)
        self.assertEqual(self.request('/?token=' + self.session._token,
                                      authenticated=False)[0], 200)

    def test_wrong_host_origin_and_cross_site_are_rejected(self):
        for headers in ({'Host': 'attacker.example'},
                        {'Origin': 'http://attacker.example'},
                        {'Origin': 'null'}, {'Sec-Fetch-Site': 'cross-site'}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request('/', headers=headers)[0], 403)
                self.assertEqual(self.request('/hello', {}, headers=headers)[0], 403)
        self.assertFalse(self.session._ready.is_set())

    def test_task_and_result_require_attached_client_and_token(self):
        self.assertEqual(self.request('/task')[0], 409)
        self.assertEqual(self.request('/hello', {}, authenticated=False)[0], 403)
        self.attach()
        self.assertEqual(self.request('/hello', {})[0], 409)
        for path, body in (('/task', None), ('/result', {'id': 'anything'})):
            with self.subTest(path=path):
                self.assertEqual(self.request(path, body, authenticated=False)[0], 403)
                self.assertEqual(self.request(path, body, headers={
                    'X-Client-Id': 'wrong-client'})[0], 409)

    def test_wrong_task_or_runtime_id_does_not_resolve_pending_rpc(self):
        self.attach()
        task, thread, result = self.pending_rpc()
        for ident, runtime in (('wrong-task', task['runtime']),
                               (task['id'], 'wrong-runtime'),
                               ([], task['runtime'])):
            with self.subTest(ident=ident, runtime=runtime):
                status, _ = self.request('/result', {
                    'id': ident, 'runtime': runtime, 'value': 'incorrect'})
                self.assertEqual(status, 409)
                self.assertTrue(result.empty())
        reply = {'id': task['id'], 'runtime': task['runtime'], 'value': '2'}
        self.assertEqual(self.request('/result', reply)[0], 200)
        self.assertEqual(result.get(timeout=3), '2')
        thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.request('/result', reply)[0], 409)

    def test_close_wakes_pending_rpc_without_waiting_for_timeout(self):
        task, thread, result = self.pending_rpc()
        self.assertIn(task['id'], self.session._pending)
        self.session.close()
        thread.join(3)
        self.assertFalse(thread.is_alive(), 'close left RPC blocked until timeout')
        error = result.get(timeout=1)
        self.assertIsInstance(error, RuntimeError)
        self.assertIn('closed', str(error).lower())
        self.assertEqual(self.session._pending, {})
        self.assertNotIn(self.session._token, str(error))

    def test_rpc_error_redacts_token_and_session_remains_usable(self):
        self.attach()
        task, thread, result = self.pending_rpc()
        status, _ = self.request('/result', {
            'id': task['id'], 'runtime': task['runtime'],
            'error': 'boom http://localhost/?token=' + self.session._token})
        self.assertEqual(status, 200)
        error = result.get(timeout=3)
        self.assertIsInstance(error, RuntimeError)
        self.assertIn('boom', str(error))
        self.assertNotIn(self.session._token, str(error))
        thread.join(3)
        self.session._check()
        self.assertNotIn(self.session._token, json.dumps(self.session.report()))

    def test_terminal_failure_redacts_token_in_error_and_report(self):
        self.session._fail('disconnected ' + self.session._token)
        with self.assertRaises(RuntimeError) as caught:
            self.session._check()
        self.assertIn('disconnected', str(caught.exception))
        self.assertNotIn(self.session._token, str(caught.exception))
        self.assertNotIn(self.session._token, json.dumps(self.session.report()))


@unittest.skipUnless(WITH_BROWSER, 'set VEUSZ_TEST_BROWSER=1 for real browser tests')
class BrowserRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Kept here so mocked tests work before browser_backend.py is installed.
        backend = importlib.import_module('browser_backend')
        cls.session = backend.BrowserSession(error_type=RuntimeError)
        cls.addClassCleanup(cls.session.close)
        cls.directory = tempfile.TemporaryDirectory(prefix='browser-test-', dir=PROJECT)
        cls.addClassCleanup(cls.directory.cleanup)

    def runtime(self, label):
        runtime = self.session.create_runtime(label)
        self.addCleanup(runtime.close)
        return runtime

    def test_multiple_runtimes_keep_globals_isolated(self):
        first = self.runtime('isolation-one')
        second = self.runtime('isolation-two')
        first.run('globalThis.marker = "first"', 'first.js')
        second.run('globalThis.marker = "second"', 'second.js')
        self.assertEqual(first.run('marker', 'check.js'), 'first')
        self.assertEqual(second.run('marker', 'check.js'), 'second')
        first.run('globalThis.onlyFirst = 42', 'first-only.js')
        self.assertEqual(second.run('typeof onlyFirst', 'check.js'), 'undefined')

    def test_run_file_preserves_classic_script_global_let(self):
        runtime = self.runtime('classic-scripts')
        directory = Path(self.directory.name)
        first = directory / 'first.js'
        second = directory / 'second.js'
        first.write_text('let persistentValue = 40;\n', encoding='utf-8')
        second.write_text(
            'persistentValue += 2;\n'
            'globalThis.readValue = function () { return String(persistentValue); };\n',
            encoding='utf-8')
        runtime.run_file(first)
        runtime.run_file(second)
        self.assertEqual(runtime.call('readValue', ''), '42')
        self.assertEqual(runtime.run('persistentValue', 'probe.js'), '42')
        self.assertEqual(runtime.run('typeof globalThis.persistentValue', 'probe.js'),
                         'undefined', 'let must remain a lexical global, not a property')

    def test_call_round_trips_json_unicode_and_escaping(self):
        runtime = self.runtime('unicode-json')
        runtime.run('globalThis.echo = function (text) { '
                    'return JSON.stringify(JSON.parse(text)); };', 'echo.js')
        payload = {'text': '\u4e2d\u6587 \U0001f600 \u00e9 " \\ \n \u2028 \u2029',
                   'values': [None, True, 0, {'key': '\u03b1'}]}
        result = runtime.call('echo', json.dumps(payload, ensure_ascii=False))
        self.assertIsInstance(result, str)
        self.assertEqual(json.loads(result), payload)

    def test_call_treats_special_global_property_names_as_data(self):
        runtime = self.runtime('literal-function-names')
        names = ['name with spaces', 'container.method', 'quote"and\\slash',
                 '(globalThis.injected = true, globalThis.echo)']
        runtime.run('globalThis.injected = false; globalThis.echo = function (s) {'
                    'return "wrong:" + s; };', 'setup.js')
        for name in names:
            runtime.run('globalThis[%s] = function (s) { return "literal:" + s; };'
                        % json.dumps(name), 'define.js')
            with self.subTest(name=name):
                self.assertEqual(runtime.call(name, 'payload'), 'literal:payload')
        self.assertEqual(runtime.run('String(injected)', 'check.js'), 'false')
        with self.assertRaises(RuntimeError):
            runtime.call('(globalThis.injected = true, globalThis.echo)()', '')
        self.assertEqual(runtime.run('String(injected)', 'check.js'), 'false')

    def test_network_and_nested_worker_apis_are_unavailable(self):
        runtime = self.runtime('pure-computation')
        for name in ('fetch', 'XMLHttpRequest', 'WebSocket', 'EventSource',
                     'Worker', 'SharedWorker', 'importScripts'):
            with self.subTest(name=name):
                self.assertEqual(runtime.run('typeof globalThis[%s]' % json.dumps(name),
                                             'network-api-check.js'), 'undefined')

    def test_run_accepts_utf8_bytes_and_rejects_invalid_bytes(self):
        runtime = self.runtime('bytes-source')
        self.assertEqual(runtime.run('"中文"'.encode('utf-8'), 'unicode.js'),
                         '\u4e2d\u6587')
        with self.assertRaisesRegex(RuntimeError, 'UTF-8'):
            runtime.run(b'\xff', 'invalid.js')
        self.assertEqual(runtime.run(b'6 * 7', 'still-alive.js'), '42')

    def test_javascript_error_does_not_expose_session_token(self):
        runtime = self.runtime('redacted-errors')
        with self.assertRaises(RuntimeError) as caught:
            runtime.run('throw new Error(%s)' % json.dumps(
                'token must be hidden: ' + self.session._token), 'error.js')
        self.assertIn('token must be hidden', str(caught.exception))
        self.assertNotIn(self.session._token, str(caught.exception))
        self.assertNotIn(self.session._token, json.dumps(self.session.report()))

    def test_javascript_exception_does_not_poison_runtime(self):
        runtime = self.runtime('exceptions')
        runtime.run('globalThis.saved = 17; globalThis.fail = function () {'
                    ' throw new Error("call boom"); };', 'setup.js')
        with self.assertRaisesRegex(RuntimeError, 'eval boom'):
            runtime.run('throw new Error("eval boom")', 'throw.js')
        with self.assertRaisesRegex(RuntimeError, 'call boom'):
            runtime.call('fail', '')
        self.assertEqual(runtime.run('saved + 1', 'still-alive.js'), '18')

    def test_closing_one_runtime_does_not_close_another(self):
        first = self.runtime('closed-runtime')
        second = self.runtime('surviving-runtime')
        second.run('globalThis.saved = "survived"', 'setup.js')
        first.close()
        first.close()
        with self.assertRaises(RuntimeError):
            first.run('1 + 1', 'closed.js')
        self.assertEqual(second.run('saved', 'check.js'), 'survived')
        third = self.runtime('new-runtime')
        self.assertEqual(third.run('6 * 7', 'check.js'), '42')


@unittest.skipUnless(WITH_BROWSER, 'set VEUSZ_TEST_BROWSER=1 for real browser tests')
class BrowserTimeoutTests(unittest.TestCase):
    """A deliberately poisoned session must not affect the other test class."""

    @classmethod
    def setUpClass(cls):
        backend = importlib.import_module('browser_backend')
        cls.environment = mock.patch.dict(os.environ, {
            'VEUSZ_JS_ENGINE_BROWSER_TIMEOUT': '2',
        })
        cls.environment.start()
        cls.addClassCleanup(cls.environment.stop)
        cls.session = backend.BrowserSession(error_type=RuntimeError)
        cls.addClassCleanup(cls.session.close)

    def test_timeout_is_terminal_and_never_recreates_runtime(self):
        first = self.session.create_runtime('timeout')
        self.addCleanup(first.close)
        second = self.session.create_runtime('timeout-peer')
        self.addCleanup(second.close)
        first.run('globalThis.saved = 123', 'setup.js')
        with self.assertRaisesRegex(RuntimeError, r'(?i)timed?\s*out|timeout'):
            first.run('while (true) {}', 'infinite-loop.js')
        with self.assertRaises(RuntimeError):
            first.run('typeof saved', 'must-not-restart.js')
        with self.assertRaises(RuntimeError):
            second.run('1 + 1', 'poisoned-session.js')
        with self.assertRaises(RuntimeError):
            self.session.create_runtime('must-not-restart-session')


if __name__ == '__main__':
    unittest.main()
