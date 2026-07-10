#!/usr/bin/env python3
"""
Sync lock mechanism to prevent concurrent sync operations.
Creates .sync.lock file with timeout and PID tracking.
"""

import os
import sys
import time
from pathlib import Path
from contextlib import contextmanager

LOCK_FILE = Path(".sync.lock")
LOCK_TIMEOUT = 300  # 5 minutes max


class SyncLock:
    """File-based lock with timeout and PID tracking."""

    def __init__(self, timeout: int = LOCK_TIMEOUT):
        self.lock_file = LOCK_FILE
        self.timeout = timeout
        self.acquired = False
        self.pid = os.getpid()

    def acquire(self) -> bool:
        """Try to acquire lock. Returns True if successful."""
        start = time.time()
        while True:
            try:
                # Try to create lock file exclusively (atomic)
                fd = os.open(self.lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, f"{os.getpid()}\n{time.time()}\n".encode())
                os.close(fd)
                self.acquired = True
                print(f"[LOCK] Acquired by PID {self.pid}")
                return True
            except FileExistsError:
                # Check if lock is stale (older than timeout)
                if self._is_stale():
                    self._force_release()
                    continue
                if time.time() - start > self.timeout:
                    print("[LOCK] Timeout waiting for lock (held by another process)")
                    return False
                time.sleep(0.5)

    def _is_stale(self) -> bool:
        """Check if lock file is older than timeout."""
        try:
            with open(self.lock_file) as f:
                lines = f.read().strip().split("\n")
                if len(lines) >= 2:
                    lock_time = float(lines[1])
                    return time.time() - lock_time > LOCK_TIMEOUT
        except Exception:
            pass
        return True

    def _force_release(self):
        """Force release stale lock."""
        try:
            self.lock_file.unlink()
            print("[LOCK] Released stale lock")
        except Exception:
            pass

    def release(self):
        """Release lock if we own it."""
        if self.acquired:
            try:
                if self.lock_file.exists():
                    content = self.lock_file.read_text().strip().split("\n")
                    if content and int(content[0]) == self.pid:
                        self.lock_file.unlink()
                        print(f"[LOCK] Released by PID {self.pid}")
            except Exception:
                pass
            self.acquired = False

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError("Could not acquire sync lock")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False


@contextmanager
def sync_lock(timeout: int = LOCK_TIMEOUT):
    """Context manager for sync lock."""
    lock = SyncLock(timeout)
    try:
        lock.acquire()
        yield
    finally:
        lock.release()


def check_lock() -> bool:
    """Check if lock is currently held. Returns True if locked."""
    if not LOCK_FILE.exists():
        return False
    try:
        with open(LOCK_FILE) as f:
            lines = f.read().strip().split("\n")
            if len(lines) >= 2:
                pid = int(lines[0])
                lock_time = float(lines[1])
                age = time.time() - lock_time
                return not age > LOCK_TIMEOUT
    except Exception:
        return False
    return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Sync lock manager")
    parser.add_argument("--check", action="store_true", help="Check if lock is held")
    parser.add_argument("--force-release", action="store_true", help="Force release lock")
    args = parser.parse_args()

    if args.check:
        if check_lock():
            print("LOCKED")
            sys.exit(0)
        else:
            print("UNLOCKED")
            sys.exit(1)
    elif args.force_release:
        Path(".sync.lock").unlink(missing_ok=True)
        print("Force released")
    else:
        print("Usage: python scripts/sync_lock.py --check|--force-release")