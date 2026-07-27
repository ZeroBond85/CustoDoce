import hashlib
import time

import pytest

from services.cache_manager import CacheManager


@pytest.fixture
def cache(tmp_path):
    return CacheManager(cache_dir=str(tmp_path / "cache_test"))


def test_set_and_get(cache):
    cache.set("key1", "value1")
    assert cache.get("key1") == "value1"


def test_get_missing(cache):
    assert cache.get("nonexistent") is None


def test_etag(cache):
    cache.set("key_etag", "data", etag="abc123")
    assert cache.get_etag("key_etag") == "abc123"


def test_md5(cache):
    md5 = hashlib.md5(b"data").hexdigest()  # noqa: S324
    cache.set("key_md5", "data", md5=md5)
    assert cache.get_md5("key_md5") == md5


def test_has_changed(cache):
    md5_old = hashlib.md5(b"old").hexdigest()  # noqa: S324
    md5_new = hashlib.md5(b"new").hexdigest()  # noqa: S324
    cache.set("key_changed", "old", md5=md5_old)
    assert cache.has_changed("key_changed", md5_new) is True
    assert cache.has_changed("key_changed", md5_old) is False


def test_invalidate(cache):
    cache.set("key_inv", "data")
    assert cache.get("key_inv") == "data"
    cache.invalidate("key_inv")
    assert cache.get("key_inv") is None


def test_ttl_expiry(cache):
    cache.set("key_ttl", "data", ttl=0.1)
    assert cache.get("key_ttl") == "data"
    time.sleep(0.15)
    assert cache.get("key_ttl") is None


def test_clear(cache):
    cache.set("a", "1")
    cache.set("b", "2")
    cache.clear()
    assert cache.get("a") is None
    assert cache.get("b") is None


def test_persistence(tmp_path):
    dir_path = str(tmp_path / "persist_cache")
    c1 = CacheManager(cache_dir=dir_path)
    c1.set("persist_key", "stored data", etag="etag123")

    c2 = CacheManager(cache_dir=dir_path)
    assert c2.get("persist_key") == "stored data"
    assert c2.get_etag("persist_key") == "etag123"


def test_empty_etag_for_missing(cache):
    assert cache.get_etag("missing") == ""


def test_empty_md5_for_missing(cache):
    assert cache.get_md5("missing") == ""


def test_overwrite(cache):
    cache.set("key", "old_val")
    cache.set("key", "new_val")
    assert cache.get("key") == "new_val"


def test_multiple_keys(cache):
    cache.set("k1", "v1", etag="e1")
    cache.set("k2", "v2", etag="e2")
    assert cache.get("k1") == "v1"
    assert cache.get("k2") == "v2"
    assert cache.get_etag("k1") == "e1"
    assert cache.get_etag("k2") == "e2"


def test_special_chars_key(cache):
    cache.set("key/with/slashes:and spaces!", "data")
    assert cache.get("key/with/slashes:and spaces!") == "data"


def test_large_data(cache):
    large = "x" * 100_000
    cache.set("large", large)
    assert cache.get("large") == large
