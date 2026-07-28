from __future__ import annotations

import os
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path


class RateLimiter:
    def __init__(self, db_path: str = "", max_attempts: int = 5, window_seconds: int = 300):
        if not db_path:
            db_path = str(Path(__file__).parent.parent / "data" / "rate_limiter.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._max_attempts = max_attempts
        self._window = window_seconds
        self._local: dict[str, list] = {}
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("CREATE TABLE IF NOT EXISTS attempts (key TEXT PRIMARY KEY, timestamps TEXT)")
        self._conn.commit()

    def _load(self, key: str) -> list:
        row = self._conn.execute("SELECT timestamps FROM attempts WHERE key = ?", (key,)).fetchone()
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


@dataclass
class TokenBucketConfig:
    capacity: float = 30.0
    refill_rate: float = 1.0
    max_backlog: float = 60.0


class TokenBucket:
    """Token bucket rate limiter — proactive, per-key."""

    _buckets: dict[str, _BucketState] = {}
    _lock = threading.Lock()

    def __init__(self, config: TokenBucketConfig | None = None):
        self._config = config or TokenBucketConfig()

    def consume(self, key: str, tokens: float = 1.0) -> bool:
        """Try to consume tokens. Returns True if allowed."""
        with self._lock:
            state = self._get_state(key)
            now = time.monotonic()
            state._refill(now, self._config)
            if state.tokens >= tokens:
                state.tokens -= tokens
                state.last_refill = now
                return True
            return False

    def wait_time(self, key: str, tokens: float = 1.0) -> float:
        """Seconds until `tokens` are available."""
        with self._lock:
            state = self._get_state(key)
            now = time.monotonic()
            state._refill(now, self._config)
            if state.tokens >= tokens:
                return 0.0
            deficit = tokens - state.tokens
            return deficit / self._config.refill_rate

    def reset(self, key: str):
        with self._lock:
            self._buckets.pop(key, None)

    def reset_all(self):
        with self._lock:
            self._buckets.clear()

    def _get_state(self, key: str) -> _BucketState:
        if key not in self._buckets:
            self._buckets[key] = _BucketState(
                tokens=self._config.capacity,
                last_refill=time.monotonic(),
            )
        return self._buckets[key]


@dataclass
class _BucketState:
    tokens: float
    last_refill: float

    def _refill(self, now: float, config: TokenBucketConfig):
        elapsed = now - self.last_refill
        added = elapsed * config.refill_rate
        self.tokens = min(self.tokens + added, config.capacity + config.max_backlog)
        self.last_refill = now
