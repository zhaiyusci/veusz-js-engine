"""POSIX browser lifetime management using an owner pipe and /bin/sh.

No installed Python interpreter is needed by the supervisor, including in a
frozen Veusz build. Popen performs session setup without Python preexec_fn or
running Python after a multithreaded fork. The host owns the only pipe writer;
even host SIGKILL during startup therefore eventually delivers EOF. The shell
installs cleanup traps before launching the browser and retains the read end.

This is cooperative process-group containment, NOT a Windows Job equivalent:
descendants can escape with setsid/setpgid, and killing only the supervisor with
SIGKILL defeats cleanup. Browser-root exit is intentionally detected by the
caller's startup timeout/HTTP heartbeat, not by poll() (which tracks the shell).
"""
import os
import subprocess
import threading


# No shell interpolation of browser arguments: "$@" preserves them verbatim.
# Non-interactive /bin/sh has job control disabled, so the background browser
# inherits the supervisor's process group. Redirect its stdin explicitly: it
# must never consume the owner's EOF channel. POSIX `kill -s KILL 0` avoids the
# incompatible negative-PID/-- syntax of various shell builtins. Never kill a
# numeric process group from the host after its leader may have been reaped.
_SUPERVISOR_SCRIPT = r'''
set +m
cleanup() {
    trap '' TERM HUP INT
    kill -s KILL 0
    exit 125
}
trap cleanup TERM HUP INT
"$@" </dev/null &
while IFS= read -r owner_message; do
    :
done
cleanup
'''
_CLEANUP_TIMEOUT = 5.0


class PosixBrowserProcess:
    """Popen-like owner; pid, poll and wait refer to the shell supervisor.

    terminate_tree and close_handles are identical, idempotent cleanup
    operations. They release ownership then wait a bounded time for the live
    supervisor to kill its own group. Timeout is an error, not proof of cleanup;
    report retains it and a later cleanup call may retry the wait. The caller
    owns log_file and must retain diagnostic artifacts on cleanup failure.
    """

    def __init__(self, process=None):
        # Allocate all owner state before launch() spawns a supervisor. After
        # Popen returns, binding the process is just one attribute assignment.
        self._cleanup_lock = threading.Lock()
        self._owner_pipe_closed = False
        self._cleanup_error = None
        self._process = process

    @property
    def pid(self):
        return self._process.pid if self._process is not None else None

    @property
    def _owner(self):
        return self._process.stdin

    def poll(self):
        return self._process.poll()

    def wait(self, timeout=None):
        return self._process.wait(timeout=timeout)

    def terminate_tree(self):
        with self._cleanup_lock:
            try:
                if not self._owner_pipe_closed:
                    self._owner.close()
                    self._owner_pipe_closed = True
                returncode = self._process.wait(timeout=_CLEANUP_TIMEOUT)
                if returncode != -9:  # SIGKILL on both Linux and macOS
                    raise RuntimeError(
                        'POSIX supervisor exited unexpectedly with code %r; '
                        'process-group cleanup is unconfirmed' % returncode)
            except BaseException as exc:
                self._cleanup_error = '%s: %s' % (type(exc).__name__, exc)
                raise

    def close_handles(self):
        self.terminate_tree()

    def report(self):
        return {
            'backend': 'posix-owner-pipe',
            'pid': self.pid,
            'pid_role': 'supervisor',
            'supervisor_pid': self.pid,
            'root_pid': None,
            'returncode': self.poll(),
            'owner_pipe_closed': self._owner_pipe_closed,
            'cleanup_error': self._cleanup_error,
            'containment': 'process-group (not a security boundary)',
            'limitations': [
                'setsid/setpgid descendants can escape',
                'supervisor-only SIGKILL defeats group cleanup',
                'root exit detected by caller startup timeout/HTTP heartbeat',
            ],
        }


def launch(args, log_file):
    """Launch argv under a POSIX shell supervisor; log_file stays caller-owned.

    An unexecutable browser is logged by /bin/sh but is not synchronously
    reported here: the caller's startup timeout must close this owner. No
    browser can be started before its supervisor exists, even if the host is
    killed before Popen returns. The owner's descriptor is non-inheritable
    (Python's Popen pipe contract), and close_fds excludes other descriptors.
    If post-spawn setup and its rollback both fail, the raised exception's
    process_owner attribute preserves ownership for caller cleanup retries.
    """
    if os.name != 'posix':
        raise OSError('POSIX browser supervision requires a POSIX platform')
    args = list(args)
    if not args:
        raise ValueError('browser argv must not be empty')
    owner = PosixBrowserProcess()
    owner._process = subprocess.Popen(
        ['/bin/sh', '-c', _SUPERVISOR_SCRIPT, 'veusz-browser-supervisor'] + args,
        stdin=subprocess.PIPE, stdout=log_file, stderr=log_file,
        start_new_session=True, close_fds=True, bufsize=0,
    )
    try:
        # Popen already creates a non-inheritable descriptor; make that
        # invariant explicit without dup() or any additional writer lifetime.
        os.set_inheritable(owner._owner.fileno(), False)
        return owner
    except BaseException as original:
        try:
            owner.terminate_tree()
        except BaseException as cleanup:
            # A failed launch must not lose the only retryable process owner.
            # BrowserSession adopts this attribute and retains log/profile
            # evidence until cleanup can be confirmed. Preserve the initiating
            # failure as the cause, and the rollback failure in the report.
            failure = RuntimeError('POSIX launch rollback failed: %s' % cleanup)
            failure.process_owner = owner
            raise failure from original
        raise
