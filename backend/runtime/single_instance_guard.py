import atexit
import ctypes
import json
import os
import time
import hashlib
from contextlib import suppress
from datetime import datetime
from pathlib import Path

try:
    import msvcrt
except Exception:  # pragma: no cover - non-Windows fallback
    msvcrt = None


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class SingleInstanceError(RuntimeError):
    pass


def _is_process_alive(pid):
    try:
        pid = int(pid)
    except Exception:
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


class SingleInstanceGuard:
    def __init__(self, name, lock_dir=None):
        normalized = str(name or "").strip().lower().replace(" ", "_")
        if not normalized:
            raise ValueError("single instance guard name is required")
        self.name = normalized
        self.lock_dir = Path(lock_dir or Path("logs") / "runtime_locks")
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        self.pid_path = self.lock_dir / f"{self.name}.pid"
        self.lock_path = self.lock_dir / f"{self.name}.lock"
        self._fh = None
        self._held = False
        self._mutex_handle = None
        mutex_key = f"{Path.cwd()}::{self.name}".encode("utf-8", errors="ignore")
        self._mutex_name = f"Global\\NEXUS_{hashlib.sha256(mutex_key).hexdigest()[:24]}"

    def acquire(self):
        if self._held:
            return self

        self._acquire_named_mutex()
        self._cleanup_stale_metadata()
        self._fh = open(self.lock_path, "a+b")
        self._prime_lock_file()
        try:
            self._lock_handle()
        except Exception:
            with suppress(Exception):
                self._fh.close()
            self._fh = None
            self._release_named_mutex()
            meta = self._read_metadata()
            pid = meta.get("pid")
            if _is_process_alive(pid):
                raise SingleInstanceError(
                    f"{self.name} is already running (pid={pid}, started_at={meta.get('started_at', '')})"
                )
            raise SingleInstanceError(f"{self.name} lock is held and could not be recovered")

        self._write_metadata()
        self._held = True
        atexit.register(self.release)
        return self

    def release(self):
        if not self._held:
            return
        with suppress(Exception):
            if self._fh:
                self._unlock_handle()
        with suppress(Exception):
            meta = self._read_metadata()
            if int(meta.get("pid") or 0) == os.getpid():
                self.pid_path.unlink(missing_ok=True)
        with suppress(Exception):
            if self._fh:
                self._fh.close()
        self._fh = None
        self._release_named_mutex()
        self._held = False

    def snapshot(self):
        return {
            "name": self.name,
            "single_instance": bool(self._held),
            "pid": os.getpid() if self._held else None,
            "lock_path": str(self.lock_path),
            "pid_path": str(self.pid_path),
        }

    def _cleanup_stale_metadata(self):
        meta = self._read_metadata()
        pid = meta.get("pid")
        if pid and not _is_process_alive(pid):
            with suppress(Exception):
                self.pid_path.unlink(missing_ok=True)

    def _read_metadata(self):
        if not self.pid_path.exists():
            return {}
        try:
            return json.loads(self.pid_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_metadata(self):
        payload = {
            "name": self.name,
            "pid": os.getpid(),
            "started_at": _now(),
            "lock_path": str(self.lock_path),
            "pid_path": str(self.pid_path),
        }
        self.pid_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _lock_handle(self):
        if msvcrt is None:  # pragma: no cover - non-Windows fallback
            return
        self._fh.seek(0)
        msvcrt.locking(self._fh.fileno(), msvcrt.LK_NBLCK, 1)

    def _unlock_handle(self):
        if msvcrt is None:  # pragma: no cover - non-Windows fallback
            return
        self._fh.seek(0)
        msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)

    def _prime_lock_file(self):
        if self._fh is None:
            return
        self._fh.seek(0, os.SEEK_END)
        if self._fh.tell() == 0:
            self._fh.write(b"0")
            self._fh.flush()
        self._fh.seek(0)

    def _acquire_named_mutex(self):
        if os.name != "nt":
            return
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.GetLastError.restype = ctypes.c_uint
        handle = kernel32.CreateMutexW(None, False, self._mutex_name)
        if not handle:
            raise SingleInstanceError(f"{self.name} mutex acquisition failed")
        last_error = kernel32.GetLastError()
        if last_error == 183:  # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(handle)
            meta = self._read_metadata()
            raise SingleInstanceError(
                f"{self.name} is already running (pid={meta.get('pid', 'unknown')}, started_at={meta.get('started_at', '')})"
            )
        self._mutex_handle = handle

    def _release_named_mutex(self):
        if os.name != "nt" or not self._mutex_handle:
            self._mutex_handle = None
            return
        kernel32 = ctypes.windll.kernel32
        with suppress(Exception):
            kernel32.ReleaseMutex(self._mutex_handle)
        with suppress(Exception):
            kernel32.CloseHandle(self._mutex_handle)
        self._mutex_handle = None
