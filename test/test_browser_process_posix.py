"""Browserless POSIX lifecycle tests, plus platform-independent contract mocks.

Run: python -S -m unittest discover -s test -p test_browser_process_posix.py
Real tests require Linux/macOS and use sys.executable ONLY as a benign fixture;
the production supervisor never launches Python. Windows skips are not POSIX
validation. Zombies are treated as exited (a container PID 1 may reap slowly).
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))
import browser_process_posix as backend


class ContractTests(unittest.TestCase):
    def fake_process(self):
        process = mock.Mock()
        process.pid = 4321
        process.stdin.fileno.return_value = 99
        process.poll.return_value = None
        process.wait.return_value = -9
        return process

    def test_launch_uses_shell_positional_argv_and_safe_popen_options(self):
        process = self.fake_process()
        log = object()
        argv = ['/path with spaces/browser', '$(touch never)', '; exit', 'a\nb']
        with mock.patch.object(backend.os, 'name', 'posix'), \
                mock.patch.object(backend.subprocess, 'Popen', return_value=process) as popen, \
                mock.patch.object(backend.os, 'set_inheritable') as inheritable:
            owner = backend.launch(argv, log)
        cmd = popen.call_args.args[0]
        self.assertEqual(cmd[:2], ['/bin/sh', '-c'])
        self.assertEqual(cmd[4:], argv)
        self.assertIn('"$@" </dev/null &', cmd[2])
        self.assertIn('kill -s KILL 0', cmd[2])
        self.assertLess(cmd[2].index('trap cleanup TERM HUP INT'),
                        cmd[2].index('"$@" </dev/null &'))
        self.assertEqual(popen.call_args.kwargs, dict(
            stdin=subprocess.PIPE, stdout=log, stderr=log,
            start_new_session=True, close_fds=True, bufsize=0))
        inheritable.assert_called_once_with(99, False)
        self.assertEqual(owner.pid, 4321)
        self.assertEqual(owner.report()['pid_role'], 'supervisor')
        self.assertIsNone(owner.report()['root_pid'])
        json.dumps(owner.report())

    def test_poll_wait_delegate_and_close_is_idempotent(self):
        process = self.fake_process()
        owner = backend.PosixBrowserProcess(process)
        self.assertIsNone(owner.poll())
        self.assertEqual(owner.wait(timeout=0.01), -9)
        process.wait.assert_called_with(timeout=0.01)
        owner.terminate_tree()
        owner.close_handles()
        owner.close_handles()
        process.stdin.close.assert_called_once_with()
        self.assertTrue(owner.report()['owner_pipe_closed'])

    def test_timeout_is_raised_and_retained_even_after_retry(self):
        process = self.fake_process()
        process.wait.side_effect = [subprocess.TimeoutExpired('supervisor', 5), -9]
        owner = backend.PosixBrowserProcess(process)
        with self.assertRaises(subprocess.TimeoutExpired):
            owner.close_handles()
        self.assertIn('TimeoutExpired', owner.report()['cleanup_error'])
        self.assertTrue(owner.report()['owner_pipe_closed'])
        owner.terminate_tree()
        process.stdin.close.assert_called_once_with()
        self.assertIn('TimeoutExpired', owner.report()['cleanup_error'])
        process.kill.assert_not_called()
        process.terminate.assert_not_called()

    def test_unexpected_supervisor_exit_is_not_silent_success(self):
        process = self.fake_process()
        process.wait.return_value = 125
        owner = backend.PosixBrowserProcess(process)
        with self.assertRaisesRegex(RuntimeError, 'cleanup is unconfirmed'):
            owner.close_handles()
        self.assertIn('125', owner.report()['cleanup_error'])

    def test_reaped_supervisor_never_receives_numeric_group_kill(self):
        process = self.fake_process()
        process.poll.return_value = -9
        owner = backend.PosixBrowserProcess(process)
        with mock.patch.object(backend.os, 'kill') as kill:
            owner.poll()
            owner.terminate_tree()
        kill.assert_not_called()
        process.kill.assert_not_called()
        process.terminate.assert_not_called()

    def test_constructor_failure_occurs_before_popen(self):
        with mock.patch.object(backend.os, 'name', 'posix'), \
                mock.patch.object(backend.subprocess, 'Popen') as popen, \
                mock.patch.object(backend, 'PosixBrowserProcess', side_effect=MemoryError('owner')):
            with self.assertRaisesRegex(MemoryError, 'owner'):
                backend.launch(['browser'], object())
        popen.assert_not_called()

    def test_post_spawn_setup_failure_releases_owner(self):
        process = self.fake_process()
        with mock.patch.object(backend.os, 'name', 'posix'), \
                mock.patch.object(backend.subprocess, 'Popen', return_value=process), \
                mock.patch.object(backend.os, 'set_inheritable', side_effect=OSError('fixture')):
            with self.assertRaisesRegex(OSError, 'fixture'):
                backend.launch(['browser'], object())
        process.stdin.close.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=backend._CLEANUP_TIMEOUT)

    def test_launch_rollback_timeout_preserves_owner_for_retry(self):
        process = self.fake_process()
        original = OSError('set inheritable failed')
        process.wait.side_effect = [subprocess.TimeoutExpired('supervisor', 5), -9]
        with mock.patch.object(backend.os, 'name', 'posix'), \
                mock.patch.object(backend.subprocess, 'Popen', return_value=process), \
                mock.patch.object(backend.os, 'set_inheritable', side_effect=original):
            with self.assertRaisesRegex(RuntimeError, 'POSIX launch rollback failed') as raised:
                backend.launch(['browser'], object())
        self.assertIs(raised.exception.__cause__, original)
        owner = raised.exception.process_owner
        self.assertIs(owner._process, process)
        self.assertEqual(owner.pid, process.pid)
        self.assertTrue(owner.report()['owner_pipe_closed'])
        self.assertIn('TimeoutExpired', owner.report()['cleanup_error'])
        owner.close_handles()
        process.stdin.close.assert_called_once_with()
        self.assertEqual(process.wait.call_count, 2)
        self.assertIn('TimeoutExpired', owner.report()['cleanup_error'])

    def test_launch_rollback_pipe_close_failure_can_retry(self):
        process = self.fake_process()
        process.stdin.close.side_effect = [OSError('close failed'), None]
        with mock.patch.object(backend.os, 'name', 'posix'), \
                mock.patch.object(backend.subprocess, 'Popen', return_value=process), \
                mock.patch.object(backend.os, 'set_inheritable', side_effect=OSError('setup')):
            with self.assertRaisesRegex(RuntimeError, 'rollback failed') as raised:
                backend.launch(['browser'], object())
        owner = raised.exception.process_owner
        self.assertFalse(owner.report()['owner_pipe_closed'])
        process.wait.assert_not_called()
        owner.close_handles()
        self.assertTrue(owner.report()['owner_pipe_closed'])
        self.assertEqual(process.stdin.close.call_count, 2)
        process.wait.assert_called_once_with(timeout=backend._CLEANUP_TIMEOUT)

    def test_popen_startup_failure_propagates(self):
        with mock.patch.object(backend.os, 'name', 'posix'), \
                mock.patch.object(backend.subprocess, 'Popen', side_effect=OSError('no shell')):
            with self.assertRaisesRegex(OSError, 'no shell'):
                backend.launch(['browser'], object())

    def test_embedded_fixture_scripts_compile_on_every_platform(self):
        compile(_HOST, '<host fixture>', 'exec')
        compile(_TREE, '<tree fixture>', 'exec')
        compile(_TREE.replace('time.sleep(120)\n', 'sys.exit(7)\n'),
                '<root exit fixture>', 'exec')

    def test_invalid_platform_and_empty_args(self):
        with mock.patch.object(backend.os, 'name', 'nt'):
            with self.assertRaisesRegex(OSError, 'POSIX'):
                backend.launch(['browser'], object())
        with mock.patch.object(backend.os, 'name', 'posix'):
            with self.assertRaises(ValueError):
                backend.launch([], object())


# A root and a child that both stay in the inherited group. stdin EOF is
# recorded to verify the root does not accidentally inherit the owner reader.
_TREE = r'''
import json, os, pathlib, subprocess, sys, time
child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])
pathlib.Path(sys.argv[1]).write_text(json.dumps({
    'root': os.getpid(), 'child': child.pid, 'group': os.getpgrp(),
    'stdin_eof': sys.stdin.read() == ''}))
time.sleep(120)
'''

# Interpose after actual OS spawn but before Popen returns to launch(), allowing
# deterministic SIGKILL in the startup window before any owner object exists.
_HOST = r'''
import json, os, pathlib, subprocess, sys, time
import browser_process_posix as backend
mode, ready, log_path, tree_path, tree_code = sys.argv[1:]
real_popen = subprocess.Popen
if mode == 'before-browser':
    backend._SUPERVISOR_SCRIPT = 'IFS= read -r startup_gate\n' + backend._SUPERVISOR_SCRIPT
if mode in ('during-launch', 'before-browser'):
    def delayed_popen(*args, **kwargs):
        p = real_popen(*args, **kwargs)
        pathlib.Path(ready).write_text(str(p.pid))
        time.sleep(120)
        return p
    backend.subprocess.Popen = delayed_popen
with open(log_path, 'ab') as log:
    p = backend.launch([sys.executable, '-c', tree_code, tree_path], log)
    pathlib.Path(ready).write_text(str(p.pid))
    time.sleep(120)
'''


@unittest.skipUnless(os.name == 'posix', 'requires real POSIX process groups and /bin/sh')
class PosixLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='posix-process-test-', dir=PROJECT)
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.log = (self.directory / 'browser.log').open('ab', buffering=0)
        self.addCleanup(self.log.close)

    def wait_until(self, predicate, message, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.02)
        self.fail(message)

    @staticmethod
    def running(pid):
        result = subprocess.run(['ps', '-o', 'stat=', '-p', str(pid)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode not in (0, 1):
            raise RuntimeError('ps failed: ' + result.stderr)
        status = result.stdout.strip()
        return bool(status) and not status.startswith('Z')

    def assert_gone(self, *pids):
        self.wait_until(lambda: all(not self.running(pid) for pid in pids),
                        'processes still running: %r' % (pids,))

    def read_tree(self, path):
        def ready():
            try:
                json.loads(path.read_text())
                return True
            except (FileNotFoundError, ValueError):
                return False
        self.wait_until(ready, 'fixture root did not become ready')
        data = json.loads(path.read_text())
        # Safety net for a broken implementation. Tests alone may kill known
        # fixture PIDs; production never uses this fallback.
        self.addCleanup(self.cleanup_fixture, data['root'], data['child'])
        return data

    def cleanup_fixture(self, *pids):
        for pid in pids:
            if self.running(pid):
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def launch_tree(self):
        path = self.directory / 'tree.json'
        owner = backend.launch([sys.executable, '-c', _TREE, str(path)], self.log)
        self.addCleanup(owner.close_handles)
        tree = self.read_tree(path)
        self.assertEqual(tree['group'], owner.pid)
        self.assertTrue(tree['stdin_eof'])
        self.assertFalse(os.get_inheritable(owner._owner.fileno()))
        return owner, tree

    def test_normal_close_kills_root_and_descendant(self):
        owner, tree = self.launch_tree()
        self.assertIsNone(owner.poll())
        owner.close_handles()
        owner.close_handles()
        self.assertEqual(owner.wait(timeout=1), -signal.SIGKILL)
        self.assert_gone(tree['root'], tree['child'])

    def test_term_hup_int_traps_cleanup_group(self):
        for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            with self.subTest(signal=sig):
                path = self.directory / ('tree-%s.json' % sig)
                owner = backend.launch([sys.executable, '-c', _TREE, str(path)], self.log)
                self.addCleanup(owner.close_handles)
                tree = self.read_tree(path)
                os.kill(owner.pid, sig)
                self.assertEqual(owner.wait(timeout=5), -signal.SIGKILL)
                self.assert_gone(tree['root'], tree['child'])

    def test_direct_host_sigkill_and_kill_during_popen(self):
        for mode in ('running', 'during-launch'):
            with self.subTest(mode=mode):
                ready = self.directory / (mode + '.ready')
                tree_path = self.directory / (mode + '.json')
                host = subprocess.Popen(
                    [sys.executable, '-c', _HOST, mode, str(ready),
                     str(self.directory / 'host-browser.log'), str(tree_path), _TREE],
                    cwd=PROJECT, stdin=subprocess.DEVNULL, stdout=self.log, stderr=self.log)
                self.addCleanup(self.reap_host, host)
                self.wait_until(lambda: ready.exists() and bool(ready.read_text()),
                                'host did not finish OS spawn')
                supervisor_pid = int(ready.read_text())
                tree = self.read_tree(tree_path)
                self.assertNotEqual(supervisor_pid, host.pid)
                self.assertEqual(tree['group'], supervisor_pid)
                # Kill exactly the host PID, NOT its process group.
                os.kill(host.pid, signal.SIGKILL)
                self.assertEqual(host.wait(timeout=5), -signal.SIGKILL)
                self.assert_gone(supervisor_pid, tree['root'], tree['child'])

    def test_host_sigkill_before_browser_launch(self):
        ready = self.directory / 'early.ready'
        tree_path = self.directory / 'early.json'
        host = subprocess.Popen(
            [sys.executable, '-c', _HOST, 'before-browser', str(ready),
             str(self.directory / 'early.log'), str(tree_path), _TREE],
            cwd=PROJECT, stdin=subprocess.DEVNULL, stdout=self.log, stderr=self.log)
        self.addCleanup(self.reap_host, host)
        self.wait_until(lambda: ready.exists() and bool(ready.read_text()),
                        'host did not spawn gated supervisor')
        supervisor_pid = int(ready.read_text())
        self.assertFalse(tree_path.exists())
        os.kill(host.pid, signal.SIGKILL)
        host.wait(timeout=5)
        self.assert_gone(supervisor_pid)
        # EOF can race browser exec; inspect the whole group, not just a
        # fixture PID file that might never have been written.
        def group_gone():
            result = subprocess.run(['ps', '-ax', '-o', 'pid=,pgid=,stat='],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, check=True)
            for line in result.stdout.splitlines():
                pid, group, status = line.split()[:3]
                if int(group) == supervisor_pid and not status.startswith('Z'):
                    return False
            return True
        self.wait_until(group_gone, 'live member survived pre-launch owner EOF')

    @staticmethod
    def reap_host(host):
        if host.poll() is None:
            host.kill()
        host.wait(timeout=5)

    def test_browser_exec_failure_is_logged_and_owner_can_close(self):
        owner = backend.launch([str(self.directory / 'missing-browser')], self.log)
        self.addCleanup(owner.close_handles)
        self.wait_until(lambda: (self.directory / 'browser.log').stat().st_size > 0,
                        'shell did not log exec failure')
        self.assertIsNone(owner.poll())  # supervisor waits for caller's startup timeout
        owner.close_handles()
        self.assertEqual(owner.wait(timeout=1), -signal.SIGKILL)

    def test_root_runexit_leaves_descendant_owned_until_close(self):
        tree_path = self.directory / 'exited-root.json'
        code = _TREE.replace('time.sleep(120)\n', 'sys.exit(7)\n')
        owner = backend.launch([sys.executable, '-c', code, str(tree_path)], self.log)
        self.addCleanup(owner.close_handles)
        tree = self.read_tree(tree_path)
        self.assert_gone(tree['root'])
        self.assertIsNone(owner.poll())
        self.assertTrue(self.running(tree['child']))
        owner.close_handles()
        self.assert_gone(tree['child'])

    def test_wait_timeout_does_not_close_owner(self):
        owner, tree = self.launch_tree()
        with self.assertRaises(subprocess.TimeoutExpired):
            owner.wait(timeout=0.02)
        self.assertFalse(owner.report()['owner_pipe_closed'])
        self.assertTrue(self.running(tree['root']))
        owner.terminate_tree()
        self.assert_gone(tree['root'], tree['child'])

    def test_shell_arguments_are_not_evaluated(self):
        output = self.directory / 'arguments.json'
        marker = self.directory / 'must-not-exist'
        args = ['a b', '; exit 9', '$(touch %s)' % marker, 'quote\"\'value', 'line\nbreak']
        code = 'import json,pathlib,sys; pathlib.Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:]))'
        owner = backend.launch([sys.executable, '-c', code, str(output)] + args, self.log)
        self.addCleanup(owner.close_handles)
        self.wait_until(lambda: output.exists() and output.stat().st_size > 0,
                        'argv fixture did not run')
        self.assertEqual(json.loads(output.read_text()), args)
        self.assertFalse(marker.exists())
        owner.close_handles()


if __name__ == '__main__':
    unittest.main()
