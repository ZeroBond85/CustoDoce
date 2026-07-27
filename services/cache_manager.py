from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from threading import Lock


class CacheEntry:
    def __init__(self, data: str, etag: str = "", md5: str = "", ttl: float = 0):
        self.data = data
        self.etag = etag
        self.md5 = md5
        self.created_at = time.time()
        self.ttl = ttl

    def is_expired(self) -> bool:
        if self.ttl <= 0:
            return False
        return time.time() - self.created_at > self.ttl


class CacheManager:
    def __init__(self, cache_dir: str = ""):
        if not cache_dir:
            cache_dir = str(Path(__file__).parent.parent / "data" / "cache")
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._memory: dict[str, CacheEntry] = {}

    def _path(self, key: str) -> Path:
        hashed = hashlib.sha256(key.encode()).hexdigest()[:32]
        return self._cache_dir / hashed

    def _path_meta(self, key: str) -> Path:
        return self._path(key).with_suffix(".meta")

    def get(self, key: str) -> str | None:
        with self._lock:
            mem = self._memory.get(key)
            if mem and not mem.is_expired():
                return mem.data
            disk = self._path(key)
            meta = self._path_meta(key)
            if disk.exists() and meta.exists():
                try:
                    m = json.loads(meta.read_text())
                    entry = CacheEntry(
                        data=disk.read_text(encoding="utf-8"),
                        etag=m.get("etag", ""),
                        md5=m.get("md5", ""),
                        ttl=m.get("ttl", 0),
                    )
                    entry.created_at = m.get("created_at", 0)
                    if not entry.is_expired():
                        self._memory[key] = entry
                        return entry.data
                except (OSError, json.JSONDecodeError):
                    pass
        return None

    def set(self, key: str, data: str, etag: str = "", md5: str = "", ttl: float = 0):
        with self._lock:
            entry = CacheEntry(data, etag=etag, md5=md5, ttl=ttl)
            self._memory[key] = entry
            path = self._path(key)
            meta = self._path_meta(key)
            try:
                path.write_text(data, encoding="utf-8")
                with open(meta, "w") as f:
                    json.dump(
                        {
                            "etag": etag,
                            "md5": md5,
                            "ttl": ttl,
                            "created_at": entry.created_at,
                        },
                        f,
                    )
            except OSError:
                pass

    def get_etag(self, key: str) -> str:
        with self._lock:
            mem = self._memory.get(key)
            if mem:
                return mem.etag
            meta = self._path_meta(key)
            if meta.exists():
                try:
                    m = json.loads(meta.read_text())
                    return m.get("etag", "")
                except (OSError, json.JSONDecodeError):
                    pass
        return ""

    def get_md5(self, key: str) -> str:
        with self._lock:
            mem = self._memory.get(key)
            if mem:
                return mem.md5
            meta = self._path_meta(key)
            if meta.exists():
                try:
                    m = json.loads(meta.read_text())
                    return m.get("md5", "")
                except (OSError, json.JSONDecodeError):
                    pass
        return ""

    def has_changed(self, key: str, new_md5: str) -> bool:
        return self.get_md5(key) != new_md5

    def invalidate(self, key: str):
        with self._lock:
            self._memory.pop(key, None)
            path = self._path(key)
            meta = self._path_meta(key)
            path.unlink(missing_ok=True)
            meta.unlink(missing_ok=True)

    def clear(self):
        with self._lock:
            self._memory.clear()
            for f in self._cache_dir.iterdir():
                if f.is_file():
                    f.unlink(missing_ok=True)
