"""Tests for RateLimiter — 5 unit tests using injectable clock for time control."""

from datetime import datetime, timedelta

from src.auth.rate_limiter import RateLimiter


def _make_clock(start: datetime = datetime(2026, 1, 1)):
    """Return a callable clock whose current time can be advanced."""
    state = {"now": start}

    def clock() -> datetime:
        return state["now"]

    def advance(delta: timedelta) -> None:
        state["now"] += delta

    return clock, advance


# --- Test 1: user is not locked initially ---

def test_user_not_locked_initially():
    limiter = RateLimiter()
    assert limiter.is_locked("alice") is False


# --- Test 2: user is locked after max_attempts failures ---

def test_lockout_after_max_failures():
    clock, _ = _make_clock()
    limiter = RateLimiter(max_attempts=3, clock=clock)

    for _ in range(3):
        limiter.record_failure("alice")

    assert limiter.is_locked("alice") is True


# --- Test 3: lockout expires after the window passes ---

def test_lockout_expires_after_window():
    clock, advance = _make_clock()
    window = timedelta(minutes=10)
    limiter = RateLimiter(max_attempts=3, lockout_window=window, clock=clock)

    for _ in range(3):
        limiter.record_failure("alice")

    assert limiter.is_locked("alice") is True

    # Advance clock past the lockout window
    advance(window + timedelta(seconds=1))
    assert limiter.is_locked("alice") is False


# --- Test 4: reset clears failure records ---

def test_reset_clears_failures():
    clock, _ = _make_clock()
    limiter = RateLimiter(max_attempts=3, clock=clock)

    for _ in range(3):
        limiter.record_failure("alice")

    assert limiter.is_locked("alice") is True

    limiter.reset("alice")
    assert limiter.is_locked("alice") is False


# --- Test 5: failures below max_attempts do not lock ---

def test_failures_below_max_do_not_lock():
    clock, _ = _make_clock()
    limiter = RateLimiter(max_attempts=5, clock=clock)

    for _ in range(4):
        limiter.record_failure("alice")

    assert limiter.is_locked("alice") is False
