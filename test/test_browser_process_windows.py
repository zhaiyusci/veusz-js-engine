"""Real benign Python process trees; never launches or touches a browser."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import browser_process_windows as win


# Each process records its own PID in workspace files, with no captured pipes.
TREE = r'''
import os, pathlib, subprocess, sys, time
folder, level = pathlib.Path(sys.argv[1]), int(sys.argv[2])
(folder / ('pid%d' % level)).write_text(str(os.getpid()))
if level:
    subprocess.Popen([sys.executable, '-c', sys.argv[3], str(folder), str(level-1), sys.argv[3]],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
if level == 2 and (folder / 'root_exit').exists():
    time.sleep(.3)
else:
    time.sleep(120)
'''


class FakeAPI:
    def __init__(self, fail=None):
        self.fail = fail
        self.closed = []
        self.killed = False
        self.assigned = False
        self.resumed = False
        self.active_calls = 0

    def create_job(self):
        return 10

    def create(self, args, log, info, job):
        assert job == 10
        if self.fail in ('attributes', 'create'):
            raise OSError(self.fail + ' failure')
        info.hProcess, info.hThread, info.dwProcessId = 11, 12, 13
        self.assigned = True  # Atomic: no returned child exists outside the Job.
        if self.fail == 'create_cleanup':
            raise OSError('duplicate close failure')

    def resume(self, thread):
        if self.fail == 'resume':
            raise OSError('resume failure')
        assert self.assigned
        self.resumed = True

    def close(self, handle):
        assert handle not in self.closed
        self.closed.append(handle)

    def terminate_process(self, process):
        self.killed = True

    def terminate_job(self, job):
        self.killed = True

    def active(self, job):
        self.active_calls += 1
        return 1 if self.active_calls == 1 else 0

    def poll(self, process):
        return 1 if self.killed else None


class RollbackTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Win32 native handle test')
    def test_native_job_is_noninheritable_and_kill_on_close(self):
        api = win._WinAPI()
        job = api.create_job()
        try:
            flags = win.DWORD()
            api.k.GetHandleInformation.argtypes = [win.HANDLE, win.C.POINTER(win.DWORD)]
            api.k.GetHandleInformation.restype = win.BOOL
            api.check(api.k.GetHandleInformation(job, win.C.byref(flags)))
            self.assertFalse(flags.value & 1)
            limits = win._EXTENDED_LIMIT()
            api.check(api.k.QueryInformationJobObject(job, 9, win.C.byref(limits),
                                                       win.C.sizeof(limits), None))
            self.assertEqual(limits.BasicLimitInformation.LimitFlags, 0x2000)
            self.assertEqual(api.active(job), 0)
        finally:
            api.close(job)

    def test_native_create_builds_both_attributes_without_inheriting_job(self):
        for failure in (None, 'attributes', 'create'):
            with self.subTest(failure=failure):
                api = win._WinAPI.__new__(win._WinAPI)
                api.k = mock.Mock()
                initialized_counts = []
                updates = {}

                def initialize(buffer, count, flags, size):
                    initialized_counts.append(count)
                    win.C.cast(size, win.C.POINTER(win.SIZE_T))[0] = 128
                    return bool(buffer is not None)

                def update(buffer, flags, attribute, value, size, previous, returned):
                    count = size // win.C.sizeof(win.HANDLE)
                    updates[attribute] = list(win.C.cast(value, win.C.POINTER(win.HANDLE))[:count])
                    if failure == 'attributes' and attribute == 0x2000d:
                        raise OSError('unsupported JOB_LIST')
                    return 1

                def create(app, command, pa, ta, inherit, flags, env, cwd, startup, info):
                    self.assertTrue(inherit)
                    self.assertTrue(flags & 0x4)
                    self.assertTrue(flags & 0x80000)
                    self.assertEqual(updates, {0x20002: [21, 22], 0x2000d: [10]})
                    if failure == 'create':
                        raise OSError('CreateProcess failure')
                    return 1

                api.k.InitializeProcThreadAttributeList.side_effect = initialize
                api.k.UpdateProcThreadAttribute.side_effect = update
                api.k.CreateProcessW.side_effect = create
                api.duplicate = mock.Mock(side_effect=[21, 22])
                api.close = mock.Mock()
                with mock.patch.dict(sys.modules, {'msvcrt': mock.Mock()}), mock.patch(
                        'builtins.open', mock.mock_open()):
                    if failure:
                        with self.assertRaises(OSError):
                            api.create(['python'], mock.Mock(), win._PROCESS_INFORMATION(), 10)
                    else:
                        api.create(['python'], mock.Mock(), win._PROCESS_INFORMATION(), 10)
                self.assertEqual(initialized_counts, [2, 2])
                self.assertEqual(api.close.call_args_list, [mock.call(21), mock.call(22)])
                api.k.DeleteProcThreadAttributeList.assert_called_once()
                self.assertEqual(api.k.CreateProcessW.call_count, 0 if failure == 'attributes' else 1)

    def test_non_windows_launch_fails_safely(self):
        with mock.patch.object(win.os, 'name', 'posix'):
            with self.assertRaisesRegex(OSError, 'require Windows'):
                win.launch(['python'], mock.Mock())

    def test_startup_failure_rolls_back_every_stage(self):
        for stage in ('attributes', 'create', 'create_cleanup', 'resume'):
            with self.subTest(stage=stage):
                api = FakeAPI(stage)
                with mock.patch.object(win, '_WinAPI', return_value=api):
                    with self.assertRaises(OSError):
                        win.launch(['python', 'benign'], mock.Mock())
                created = stage in ('create_cleanup', 'resume')
                self.assertEqual(set(api.closed), {10, 11, 12} if created else {10})
                self.assertEqual(api.killed, created)
                self.assertFalse(api.resumed)

    def test_failed_startup_rollback_transfers_retryable_owner(self):
        for stage in ('terminate_job', 'active', 'poll', 'close_job',
                      'close_thread', 'close_process', 'empty_job_close'):
            with self.subTest(stage=stage):
                original = OSError('original startup failure')
                api = FakeAPI()
                startup_method = 'create' if stage == 'empty_job_close' else 'resume'
                if stage.startswith('close_') or stage == 'empty_job_close':
                    target = {'close_job': 10, 'close_thread': 12,
                              'close_process': 11, 'empty_job_close': 10}[stage]
                    close = api.close

                    def fail_close(handle):
                        if handle == target:
                            raise OSError('rollback close failure')
                        close(handle)

                    cleanup_patch = mock.patch.object(api, 'close', side_effect=fail_close)
                else:
                    cleanup_patch = mock.patch.object(api, stage,
                                                      side_effect=OSError('rollback API failure'))
                with mock.patch.object(win, '_WinAPI', return_value=api), mock.patch.object(
                        api, startup_method, side_effect=original), cleanup_patch:
                    with self.assertRaises(RuntimeError) as raised:
                        win.launch(['python'], mock.Mock())
                failure = raised.exception
                self.assertIs(failure.__cause__, original)
                owner = failure.process_owner
                self.assertTrue(owner.report()['cleanup_errors'])
                if stage in ('terminate_job', 'active', 'poll'):
                    self.assertTrue(owner.report()['job_open'])
                    self.assertTrue(owner.report()['process_handle_open'])
                    self.assertNotIn(10, api.closed)
                    self.assertNotIn(11, api.closed)
                owner.close_handles()
                owner.close_handles()
                self.assertFalse(owner.report()['job_open'])
                self.assertFalse(owner.report()['process_handle_open'])
                self.assertTrue(owner.report()['tree_exited'])
                self.assertEqual(set(api.closed), {10} if stage == 'empty_job_close' else {10, 11, 12})

    def test_wait_timeout_and_idempotent_close(self):
        api = FakeAPI()
        with mock.patch.object(win, '_WinAPI', return_value=api):
            process = win.launch(['python'], mock.Mock())
        with self.assertRaises(subprocess.TimeoutExpired):
            process.wait(0)
        process.close_handles()
        process.close_handles()
        self.assertEqual(process.wait(0), 1)
        self.assertGreaterEqual(api.active_calls, 2)
        self.assertEqual(set(api.closed), {10, 11, 12})
        self.assertTrue(process.report()['tree_exited'])
        self.assertTrue(process.report()['atomic_job_assignment'])
        self.assertEqual(process.report()['job_assignment'], 'PROC_THREAD_ATTRIBUTE_JOB_LIST')

    def test_cleanup_error_retains_ownership_and_is_reported(self):
        api = FakeAPI()
        with mock.patch.object(win, '_WinAPI', return_value=api):
            process = win.launch(['python'], mock.Mock())
        with mock.patch.object(api, 'terminate_job', side_effect=OSError('cleanup denied')):
            with self.assertRaises(OSError):
                process.close_handles()
        self.assertTrue(process.report()['job_open'])
        self.assertIn('cleanup denied', process.report()['cleanup_errors'])
        process.close_handles()


@unittest.skipUnless(os.name == 'nt', 'Win32 integration tests')
class WindowsTreeTests(unittest.TestCase):
    def setUp(self):
        # Explicit workspace handshake storage, not system-temp pipe endpoints.
        self.temp = tempfile.TemporaryDirectory(prefix='win-process-test-', dir=ROOT / 'test')
        self.folder = Path(self.temp.name)
        self.api = win._WinAPI()
        self.observers = []
        self.process = None
        self.host = None
        self.log = (self.folder / 'browser.log').open('ab')
        k = self.api.k
        k.OpenProcess.argtypes = [win.DWORD, win.BOOL, win.DWORD]
        k.OpenProcess.restype = win.HANDLE

    def tearDown(self):
        if self.host is not None and self.host.poll() is None:
            self.host.terminate()
            self.host.wait(timeout=10)
        if self.process is not None:
            self.process.close_handles()
        for handle in self.observers:
            self.api.close(handle)
        self.log.close()
        self.temp.cleanup()

    def argv(self):
        return [sys.executable, '-c', TREE, str(self.folder), '2', TREE]

    def observe_tree(self):
        deadline = time.monotonic() + 15
        for level in (2, 1, 0):
            path = self.folder / ('pid%d' % level)
            while not path.exists() or not path.stat().st_size:
                if time.monotonic() > deadline:
                    self.fail('tree handshake timed out: %s' % path)
                time.sleep(.01)
            handle = self.api.k.OpenProcess(0x100000 | 0x1000, False, int(path.read_text()))
            self.assertTrue(handle, 'unable to open benign tree observer handle')
            self.observers.append(handle)

    def assert_tree_dead(self):
        for handle in self.observers:
            self.assertEqual(self.api.k.WaitForSingleObject(handle, 10000), 0,
                             'a job descendant survived cleanup')

    def test_normal_close_kills_whole_tree_with_concurrent_poll(self):
        self.process = win.launch(self.argv(), self.log)
        self.observe_tree()
        stop = threading.Event()
        errors = []

        def monitor():
            try:
                while not stop.wait(.001):
                    self.process.poll()
            except BaseException as exc:
                errors.append(exc)

        thread = threading.Thread(target=monitor)
        thread.start()
        try:
            self.process.close_handles()
            self.process.close_handles()
        finally:
            stop.set()
            thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assert_tree_dead()
        self.assertTrue(self.process.report()['tree_exited'])

    def test_root_exit_does_not_release_descendant_ownership(self):
        (self.folder / 'root_exit').touch()
        self.process = win.launch(self.argv(), self.log)
        self.observe_tree()
        self.assertEqual(self.process.wait(10), 0)
        self.assertEqual(self.api.k.WaitForSingleObject(self.observers[-1], 0), 258)
        self.process.close_handles()
        self.assert_tree_dead()

    def test_external_host_kill_without_tree_flag(self):
        code = '''
import json, pathlib, sys, time
sys.path.insert(0, sys.argv[1])
import browser_process_windows as win
folder = pathlib.Path(sys.argv[2])
with (folder / 'owner.log').open('ab') as log:
    process = win.launch(json.loads(sys.argv[3]), log)
    (folder / 'owner_ready').write_text(str(process.pid))
    time.sleep(120)
'''
        self.host = subprocess.Popen([sys.executable, '-c', code, str(ROOT),
                                      str(self.folder), json.dumps(self.argv())],
                                     stdin=subprocess.DEVNULL, stdout=self.log, stderr=self.log)
        self.observe_tree()
        # Popen.terminate is TerminateProcess(host), NOT taskkill /T. The OS must
        # close the only Job handle; no Python finalizer/atexit can run here.
        self.host.terminate()
        self.host.wait(timeout=10)
        self.assert_tree_dead()

    def test_real_suspended_child_create_cleanup_failure_is_reaped(self):
        original = win._WinAPI.create

        def capture(api, args, log, info, job):
            original(api, args, log, info, job)
            self.observers.append(api.duplicate(info.hProcess))
            raise OSError('injected post-create cleanup failure')

        with mock.patch.object(win._WinAPI, 'create', capture):
            with self.assertRaisesRegex(OSError, 'injected post-create'):
                win.launch(self.argv(), self.log)
        self.assert_tree_dead()
        self.assertFalse((self.folder / 'pid2').exists(), 'suspended child executed before resume')

    def test_owner_death_immediately_after_atomic_create_before_resume(self):
        code = '''
import json, pathlib, sys, time
sys.path.insert(0, sys.argv[1])
import browser_process_windows as win
folder = pathlib.Path(sys.argv[2])
original = win._WinAPI.create
def pause(api, args, log, info, job):
    original(api, args, log, info, job)
    (folder / 'suspended_pid').write_text(str(info.dwProcessId))
    time.sleep(120)
win._WinAPI.create = pause
with (folder / 'owner.log').open('ab') as log:
    win.launch(json.loads(sys.argv[3]), log)
'''
        self.host = subprocess.Popen([sys.executable, '-c', code, str(ROOT),
                                      str(self.folder), json.dumps(self.argv())],
                                     stdin=subprocess.DEVNULL, stdout=self.log, stderr=self.log)
        path = self.folder / 'suspended_pid'
        deadline = time.monotonic() + 15
        while not path.exists() or not path.stat().st_size:
            if time.monotonic() > deadline:
                self.fail('suspended creation handshake timed out')
            time.sleep(.01)
        handle = self.api.k.OpenProcess(0x100000 | 0x1000, False, int(path.read_text()))
        self.assertTrue(handle)
        self.observers.append(handle)
        self.host.terminate()
        self.host.wait(timeout=10)
        self.assert_tree_dead()
        self.assertFalse((self.folder / 'pid2').exists())

    def test_native_resume_failure_is_reaped(self):
        original = win._WinAPI.create

        def capture(api, args, log, info, job):
            original(api, args, log, info, job)
            self.observers.append(api.duplicate(info.hProcess))

        with mock.patch.object(win._WinAPI, 'create', capture), mock.patch.object(
                win._WinAPI, 'resume', side_effect=OSError('injected resume failure')):
            with self.assertRaisesRegex(OSError, 'injected resume'):
                win.launch(self.argv(), self.log)
        self.assert_tree_dead()
        self.assertFalse((self.folder / 'pid2').exists())


if __name__ == '__main__':
    unittest.main()
