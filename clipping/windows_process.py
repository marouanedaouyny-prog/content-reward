"""Own each Windows media process tree without process enumeration or elevation."""

import ctypes
import subprocess
import sys
from contextlib import contextmanager
from ctypes import wintypes
from pathlib import Path


# Win32 layouts and kill-on-close semantics:
# https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
# https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information
class BasicLimits(ctypes.Structure):
    _fields_ = [
        ('PerProcessUserTimeLimit', ctypes.c_longlong),
        ('PerJobUserTimeLimit', ctypes.c_longlong), ('LimitFlags', wintypes.DWORD),
        ('MinimumWorkingSetSize', ctypes.c_size_t), ('MaximumWorkingSetSize', ctypes.c_size_t),
        ('ActiveProcessLimit', wintypes.DWORD), ('Affinity', ctypes.c_size_t),
        ('PriorityClass', wintypes.DWORD), ('SchedulingClass', wintypes.DWORD),
    ]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [
        ('BasicLimitInformation', BasicLimits), ('IoInfo', ctypes.c_ulonglong * 6),
        ('ProcessMemoryLimit', ctypes.c_size_t), ('JobMemoryLimit', ctypes.c_size_t),
        ('PeakProcessMemoryUsed', ctypes.c_size_t), ('PeakJobMemoryUsed', ctypes.c_size_t),
    ]


class WindowsJob:
    def __init__(self):
        self.api = ctypes.WinDLL('kernel32', use_last_error=True)
        for name, args, result in (
            ('CreateJobObjectW', [ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
            ('SetInformationJobObject', [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
            ('AssignProcessToJobObject', [wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
            ('CloseHandle', [wintypes.HANDLE], wintypes.BOOL),
        ):
            function = getattr(self.api, name)
            function.argtypes, function.restype = args, result
        self.handle = self.api.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
            error = ctypes.WinError(ctypes.get_last_error())
            self.close()
            raise error

    def assign(self, process):
        # CPython owns this handle from CreateProcess; no PID lookup is needed.
        if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            if not self.api.CloseHandle(self.handle):
                raise ctypes.WinError(ctypes.get_last_error())
            self.handle = None


@contextmanager
def launch(args, cwd=None):
    """Release the media launcher only after it belongs to a kill-on-close job."""
    try:
        job = WindowsJob()
    except OSError as exc:
        raise ValueError('Windows could not manage the media process tree') from exc
    try:
        launcher = Path(__file__).with_name('_media_launcher.py')
        with subprocess.Popen([sys.executable, '-I', str(launcher), *args], cwd=cwd,
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, encoding='utf-8', errors='replace',
                              creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW) as process:
            try:
                try:
                    job.assign(process)
                    process.stdin.write('1')
                    process.stdin.close()
                    process.stdin = None
                except OSError as exc:
                    raise ValueError('Windows could not manage the media process tree') from exc
                yield process
            finally:
                # This also handles successful commands leaving detached children,
                # unexpected exceptions and termination of the workspace itself.
                job.close()
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=10)
    finally:
        job.close()
