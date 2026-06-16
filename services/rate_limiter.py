import os
import sqlite3
import time
import threading
from pathlib import Path
from typing import Dict


class RateLimiter:
    def __init__(self, db_path: str = "", max_attempts: int = 5, window_seconds: int = 300):
        if not db_path:
            db_path = str(Path(__file__).parent.parent / "data" / "rate_limiter.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._max_attempts = max_attempts
        self._window = window_seconds
        self._local: Dict[str, list] = {}
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS attempts "
            "(key TEXT PRIMARY KEY, timestamps TEXT)"
        )
        self._conn.commit()

    def _load(self, key: str) -> list:
        row = self._conn.execute(
            "SELECT timestamps FROM attempts WHERE key = ?", (key,)
        ).fetchone()
        if row:
            return [float(t) for t in row[0].split(",") if t]
        return []

    def _save(self, key: str, timestamps: list):
        val = ",".join(f"{t:.3f}" for t in timestamps)
        self._conn.execute(
            "INSERT OR REPLACE INTO attempts (key, timestamps) VALUES (?, ?)",
            (key, val),
        )
        self._conn.commit()

    def _prune(self, timestamps: list) -> list:
        cutoff = time.time() - self._window
        return [t for t in timestamps if t > cutoff]

    def is_limited(self, key: str) -> bool:
        with self._lock:
            ts = self._prune(self._load(key))
            return len(ts) >= self._max_attempts

    def record_attempt(self, key: str):
        with self._lock:
            now = time.time()
            ts = self._prune(self._load(key))
            ts.append(now)
            self._local[key] = ts
            self._save(key, ts)

    def clear_attempts(self, key: str):
        with self._lock:
            self._local.pop(key, None)
            self._conn.execute("DELETE FROM attempts WHERE key = ?", (key,))
            self._conn.commit()

    def remaining_attempts(self, key: str) -> int:
        with self._lock:
            ts = self._prune(self._load(key))
            return max(0, self._max_attempts - len(ts))

    def retry_after(self, key: str) -> int:
        with self._lock:
            now = time.time()
            ts = self._prune(self._load(key))
            if len(ts) >= self._max_attempts:
                wait = int(self._window - (now - ts[0]))
                return max(0, wait)
            return 0
