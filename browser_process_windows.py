"""Win32 browser ownership, using only documented APIs and the standard library.

A private, non-inheritable kill-on-close Job owns every descendant. Windows 10+
JOB_LIST assigns ownership atomically during suspended creation, eliminating the
create/assign owner-death gap. Unsupported systems fail with no fallback. Import is portable; launch requires Windows. This is lifecycle control,
not a security sandbox (processes must not deliberately escape/duplicate handles).
"""
import ctypes as C
import os
import subprocess
import threading
import time


# Use fixed-width Windows integers even when this module is imported on Unix.
DWORD = C.c_uint32
BOOL = C.c_int32
HANDLE = C.c_void_p
SIZE_T = C.c_size_t


class _IO_COUNTERS(C.Structure):
    _fields_ = [(n, C.c_uint64) for n in (
        'ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
        'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]


class _BASIC_LIMIT(C.Structure):
    _fields_ = [('PerProcessUserTimeLimit', C.c_int64),
                ('PerJobUserTimeLimit', C.c_int64), ('LimitFlags', DWORD),
                ('MinimumWorkingSetSize', SIZE_T), ('MaximumWorkingSetSize', SIZE_T),
                ('ActiveProcessLimit', DWORD), ('Affinity', SIZE_T),
                ('PriorityClass', DWORD), ('SchedulingClass', DWORD)]


class _EXTENDED_LIMIT(C.Structure):
    _fields_ = [('BasicLimitInformation', _BASIC_LIMIT), ('IoInfo', _IO_COUNTERS),
                ('ProcessMemoryLimit', SIZE_T), ('JobMemoryLimit', SIZE_T),
                ('PeakProcessMemoryUsed', SIZE_T), ('PeakJobMemoryUsed', SIZE_T)]


class _ACCOUNTING(C.Structure):
    _fields_ = [(n, C.c_int64) for n in (
        'TotalUserTime', 'TotalKernelTime', 'ThisPeriodTotalUserTime',
        'ThisPeriodTotalKernelTime')] + [(n, DWORD) for n in (
            'TotalPageFaultCount', 'TotalProcesses', 'ActiveProcesses',
            'TotalTerminatedProcesses')]


class _STARTUPINFO(C.Structure):
    _fields_ = [('cb', DWORD), ('lpReserved', C.c_wchar_p),
                ('lpDesktop', C.c_wchar_p), ('lpTitle', C.c_wchar_p)] + [
        (n, DWORD) for n in ('dwX', 'dwY', 'dwXSize', 'dwYSize',
                           'dwXCountChars', 'dwYCountChars', 'dwFillAttribute',
                           'dwFlags')] + [('wShowWindow', C.c_uint16),
        ('cbReserved2', C.c_uint16), ('lpReserved2', C.c_void_p),
        ('hStdInput', HANDLE), ('hStdOutput', HANDLE), ('hStdError', HANDLE)]


class _STARTUPINFOEX(C.Structure):
    _fields_ = [('StartupInfo', _STARTUPINFO), ('lpAttributeList', C.c_void_p)]


class _PROCESS_INFORMATION(C.Structure):
    _fields_ = [('hProcess', HANDLE), ('hThread', HANDLE),
                ('dwProcessId', DWORD), ('dwThreadId', DWORD)]


class _WinAPI:
    def __init__(self):
        if os.name != 'nt':
            raise OSError('Windows Job Objects require Windows')
        self.k = C.WinDLL('kernel32', use_last_error=True)
        signatures = {
            'CreateJobObjectW': (HANDLE, [C.c_void_p, C.c_wchar_p]),
            'SetInformationJobObject': (BOOL, [HANDLE, C.c_int, C.c_void_p, DWORD]),
            'QueryInformationJobObject': (BOOL, [HANDLE, C.c_int, C.c_void_p, DWORD, C.c_void_p]),
            'SetHandleInformation': (BOOL, [HANDLE, DWORD, DWORD]),
            'GetCurrentProcess': (HANDLE, []),
            'DuplicateHandle': (BOOL, [HANDLE, HANDLE, HANDLE, C.POINTER(HANDLE), DWORD, BOOL, DWORD]),
            'InitializeProcThreadAttributeList': (BOOL, [C.c_void_p, DWORD, DWORD, C.POINTER(SIZE_T)]),
            'UpdateProcThreadAttribute': (BOOL, [C.c_void_p, DWORD, SIZE_T, C.c_void_p, SIZE_T, C.c_void_p, C.c_void_p]),
            'DeleteProcThreadAttributeList': (None, [C.c_void_p]),
            'CreateProcessW': (BOOL, [C.c_wchar_p, C.c_wchar_p, C.c_void_p, C.c_void_p, BOOL, DWORD, C.c_void_p, C.c_wchar_p, C.c_void_p, C.POINTER(_PROCESS_INFORMATION)]),
            'ResumeThread': (DWORD, [HANDLE]),
            'TerminateProcess': (BOOL, [HANDLE, DWORD]),
            'TerminateJobObject': (BOOL, [HANDLE, DWORD]),
            'WaitForSingleObject': (DWORD, [HANDLE, DWORD]),
            'GetExitCodeProcess': (BOOL, [HANDLE, C.POINTER(DWORD)]),
            'CloseHandle': (BOOL, [HANDLE]),
        }
        for name, (restype, argtypes) in signatures.items():
            f = getattr(self.k, name)
            f.restype, f.argtypes = restype, argtypes

    @staticmethod
    def check(result):
        if not result:
            raise C.WinError(C.get_last_error())
        return result

    def close(self, handle):
        self.check(self.k.CloseHandle(handle))

    def create_job(self):
        job = self.check(self.k.CreateJobObjectW(None, None))
        try:
            self.check(self.k.SetHandleInformation(job, 1, 0))
            limits = _EXTENDED_LIMIT()
            limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
            self.check(self.k.SetInformationJobObject(job, 9, C.byref(limits), C.sizeof(limits)))
            return job
        except BaseException:
            self.close(job)
            raise

    def duplicate(self, handle):
        dup = HANDLE()
        current = self.k.GetCurrentProcess()
        self.check(self.k.DuplicateHandle(current, handle, current, C.byref(dup), 0, True, 2))
        return dup.value

    def create(self, args, log_file, info, job):
        import msvcrt
        # Only these two temporary duplicates are inheritable. The Job, primary
        # process and thread handles are never in the explicit inheritance list.
        handles = []
        attributes = None
        initialized = False
        try:
            with open(os.devnull, 'rb') as null:
                handles.append(self.duplicate(msvcrt.get_osfhandle(null.fileno())))
            handles.append(self.duplicate(msvcrt.get_osfhandle(log_file.fileno())))
            size = SIZE_T()
            self.k.InitializeProcThreadAttributeList(None, 2, 0, C.byref(size))
            if not size.value:
                raise C.WinError(C.get_last_error())
            attributes = C.create_string_buffer(size.value)
            self.check(self.k.InitializeProcThreadAttributeList(attributes, 2, 0, C.byref(size)))
            initialized = True
            inherited = (HANDLE * 2)(*handles)
            self.check(self.k.UpdateProcThreadAttribute(attributes, 0, 0x20002,
                       inherited, C.sizeof(inherited), None, None))
            # PROC_THREAD_ATTRIBUTE_JOB_LIST (Windows 10+): assignment is part
            # of CreateProcess itself, not a later user-mode operation. This
            # attribute does NOT make the Job handle inheritable or pass it to
            # the child. Unsupported attributes/jobs are fatal, never retried
            # without ownership.
            jobs = (HANDLE * 1)(job)
            self.check(self.k.UpdateProcThreadAttribute(attributes, 0, 0x2000d,
                       jobs, C.sizeof(jobs), None, None))
            startup = _STARTUPINFOEX()
            startup.StartupInfo.cb = C.sizeof(startup)
            startup.StartupInfo.dwFlags = 0x100  # STARTF_USESTDHANDLES
            startup.StartupInfo.hStdInput = handles[0]
            startup.StartupInfo.hStdOutput = handles[1]
            startup.StartupInfo.hStdError = handles[1]
            startup.lpAttributeList = C.cast(attributes, C.c_void_p)
            command = C.create_unicode_buffer(subprocess.list2cmdline(args))
            self.check(self.k.CreateProcessW(args[0], command, None, None, True,
                       0x4 | 0x80000 | 0x08000000, None, None, C.byref(startup), C.byref(info)))
        finally:
            if initialized:
                self.k.DeleteProcThreadAttributeList(attributes)
            errors = []
            for handle in handles:
                try:
                    self.close(handle)
                except OSError as exc:
                    errors.append(exc)
            if errors:
                raise OSError('Failed to close inherited-handle duplicates: %r' % errors)

    def resume(self, thread):
        if self.k.ResumeThread(thread) == 0xffffffff:
            raise C.WinError(C.get_last_error())

    def terminate_process(self, process):
        self.check(self.k.TerminateProcess(process, 1))

    def terminate_job(self, job):
        self.check(self.k.TerminateJobObject(job, 1))

    def active(self, job):
        info = _ACCOUNTING()
        self.check(self.k.QueryInformationJobObject(job, 1, C.byref(info), C.sizeof(info), None))
        return info.ActiveProcesses

    def poll(self, process):
        result = self.k.WaitForSingleObject(process, 0)
        if result == 258:
            return None
        if result != 0:
            raise C.WinError(C.get_last_error())
        code = DWORD()
        self.check(self.k.GetExitCodeProcess(process, C.byref(code)))
        return code.value


class WindowsProcess:
    """Popen-like root observation plus explicit whole-Job lifetime ownership."""
    def __init__(self, args, api):
        self.args = args
        self.pid = None
        self._api = api
        self._lock = threading.RLock()
        self._job = self._process = self._thread = None
        self._returncode = None
        self._tree_exited = False
        self._errors = []

    def poll(self):
        with self._lock:
            if self._returncode is None and self._process is not None:
                self._returncode = self._api.poll(self._process)
            return self._returncode

    def wait(self, timeout=None):
        deadline = None if timeout is None else time.monotonic() + max(0, timeout)
        while True:
            code = self.poll()
            if code is not None:
                return code
            if deadline is not None and time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(self.args, timeout)
            time.sleep(0.01)

    def _close(self, name):
        handle = getattr(self, name)
        if handle is not None:
            self._api.close(handle)
            setattr(self, name, None)

    def terminate_tree(self):
        """Kill and confirm *all* Job members gone before releasing ownership.

        Retain the Job on failure so a caller can retry. The 30-second cleanup
        bound reports an error rather than claiming successful cleanup.
        """
        with self._lock:
            try:
                if self._job is not None:
                    self._api.terminate_job(self._job)
                    deadline = time.monotonic() + 30
                    while self._api.active(self._job):
                        if time.monotonic() >= deadline:
                            raise TimeoutError('Windows Job subtree did not exit within 30 seconds')
                        time.sleep(0.01)
                    # Cache a signaled root's exit code before close_handles
                    # releases its handle; accounting and process signaling are
                    # distinct kernel observations.
                    if self._process is not None:
                        self.wait(timeout=30)
                    self._tree_exited = True
                    self._close('_job')
                self.poll()
            except BaseException as exc:
                self._errors.append(str(exc))
                raise

    def close_handles(self):
        with self._lock:
            self.terminate_tree()
            errors = []
            for name in ('_thread', '_process'):
                try:
                    self._close(name)
                except OSError as exc:
                    self._errors.append(str(exc))
                    errors.append(exc)
            if errors:
                raise OSError('Failed to close Windows process handles: %r' % errors)

    def report(self):
        with self._lock:
            return {'mechanism': 'windows-job-object', 'kill_on_job_close': True,
                    'suspended_assignment': True, 'explicit_handle_list': True,
                    'atomic_job_assignment': True,
                    'job_assignment': 'PROC_THREAD_ATTRIBUTE_JOB_LIST',
                    'minimum_windows_version': 'Windows 10',
                    'job_handle_inheritable': False, 'pid': self.pid,
                    'returncode': self._returncode, 'job_open': self._job is not None,
                    'process_handle_open': self._process is not None,
                    'tree_exited': self._tree_exited,
                    'cleanup_errors': list(self._errors)}


def launch(args, log_file):
    """Launch an argv sequence, logging to an existing open binary file or path.

    Frozen Python is supported: no helper interpreter or third-party package is
    involved. Assignment failure (including restrictive parent Jobs) is fatal.
    If rollback fails, the raised RuntimeError.process_owner retains ownership;
    callers must preserve it and retry close_handles() before deleting profiles.
    """
    if isinstance(args, (str, bytes)) or not args:
        raise ValueError('args must be a nonempty argv sequence')
    args = [os.fsdecode(arg) for arg in args]
    api = _WinAPI()
    obj = WindowsProcess(args, api)
    info = _PROCESS_INFORMATION()
    owned_log = None
    try:
        obj._job = api.create_job()
        if isinstance(log_file, (str, bytes, os.PathLike)):
            owned_log = open(log_file, 'ab')
            log_file = owned_log
        log_file.flush()
        try:
            api.create(args, log_file, info, obj._job)
        finally:
            # Also capture handles if create succeeded but its local cleanup failed.
            obj._process, obj._thread = info.hProcess, info.hThread
            obj.pid = info.dwProcessId or None
        api.resume(obj._thread)
        obj._close('_thread')
        if owned_log is not None:
            owned_log.close()
            owned_log = None
        return obj
    except BaseException as original:
        errors = []
        if obj._process is not None:
            try:
                # Atomic creation guarantees ownership even when create() raises
                # in local cleanup. Do not discard the only retryable Job handle
                # if termination/accounting fails: the caller must retain it.
                obj.close_handles()
            except BaseException as exc:
                errors.append(exc)
        else:
            # No process was created, so only empty ownership handles remain.
            obj._tree_exited = True
            for name in ('_job', '_thread', '_process'):
                try:
                    obj._close(name)
                except BaseException as exc:
                    obj._errors.append(str(exc))
                    errors.append(exc)
        if owned_log is not None:
            try:
                owned_log.close()
            except BaseException as exc:
                obj._errors.append(str(exc))
                errors.append(exc)
        if errors:
            failure = RuntimeError('Windows launch rollback failed: %r' % errors)
            failure.process_owner = obj
            raise failure from original
        raise
