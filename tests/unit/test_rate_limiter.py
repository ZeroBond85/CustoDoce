import time

import pytest

from services.rate_limiter import RateLimiter


class _FakeClock:
    """Relogio controlavel — substitui time.time() no modulo sob teste."""

    def __init__(self):
        self._t = time.time()

    def advance(self, seconds: float) -> None:
        self._t += seconds

    def __call__(self) -> float:
        return self._t


@pytest.fixture
def fake_clock(monkeypatch):
    clock = _FakeClock()
    monkeypatch.setattr("services.rate_limiter.time.time", clock)
    return clock


@pytest.fixture
def temp_limiter(tmp_path):
    db_file = tmp_path / "test_rate.db"
    return RateLimiter(db_path=str(db_file), max_attempts=3, window_seconds=1)


def test_rate_limiter_basic(temp_limiter):
    key = "user1"
    assert temp_limiter.is_limited(key) is False

    temp_limiter.record_attempt(key)
    temp_limiter.record_attempt(key)
    temp_limiter.record_attempt(key)

    assert temp_limiter.is_limited(key) is True
    assert temp_limiter.remaining_attempts(key) == 0


def test_rate_limiter_window_expiry(temp_limiter, fake_clock):
    key = "user2"
    temp_limiter.record_attempt(key)
    temp_limiter.record_attempt(key)
    temp_limiter.record_attempt(key)
    assert temp_limiter.is_limited(key) is True

    fake_clock.advance(1.1)
    assert temp_limiter.is_limited(key) is False
    assert temp_limiter.remaining_attempts(key) == 3


def test_rate_limiter_clear(temp_limiter):
    key = "user3"
    temp_limiter.record_attempt(key)
    temp_limiter.record_attempt(key)
    temp_limiter.record_attempt(key)
    temp_limiter.clear_attempts(key)
    assert temp_limiter.is_limited(key) is False


def test_retry_after(temp_limiter, fake_clock):
    key = "user4"
    temp_limiter.record_attempt(key)
    temp_limiter.record_attempt(key)
    temp_limiter.record_attempt(key)

    fake_clock.advance(0.01)
    retry = temp_limiter.retry_after(key)
    assert retry >= 0
    assert retry <= 1


def test_multiple_keys(temp_limiter):
    k1, k2 = "u1", "u2"
    temp_limiter.record_attempt(k1)
    temp_limiter.record_attempt(k1)
    temp_limiter.record_attempt(k1)

    assert temp_limiter.is_limited(k1) is True
    assert temp_limiter.is_limited(k2) is False


@pytest.mark.parametrize(
    "attempts, is_limited",
    [
        (1, False),
        (2, False),
        (3, True),
        (4, True),
    ],
)
def test_attempt_thresholds(temp_limiter, attempts, is_limited):
    key = f"user_{attempts}"
    for _ in range(attempts):
        temp_limiter.record_attempt(key)
    assert temp_limiter.is_limited(key) == is_limited


def test_persistence(tmp_path):
    db_file = str(tmp_path / "persist.db")
    lim1 = RateLimiter(db_path=db_file, max_attempts=2)
    lim1.record_attempt("user")
    lim1.record_attempt("user")

    lim2 = RateLimiter(db_path=db_file, max_attempts=2)
    assert lim2.is_limited("user") is True
