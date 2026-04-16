"""Extended tests for RateLimiter — edge cases, isolation, and boundary conditions."""

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


# --- Test 1: failures from different users are isolated ---

def test_failures_are_isolated_per_user():
    clock, _ = _make_clock()
    limiter = RateLimiter(max_attempts=3, clock=clock)

    for _ in range(3):
        limiter.record_failure("alice")

    assert limiter.is_locked("alice") is True
    assert limiter.is_locked("bob") is False


# --- Test 2: reset on user with no failures is a no-op ---

def test_reset_on_unknown_user_is_noop():
    limiter = RateLimiter()
    # Should not raise
    limiter.reset("nobody")
    assert limiter.is_locked("nobody") is False


# --- Test 3: partial window pruning — old failures expire, recent ones remain ---

def test_partial_pruning_keeps_recent_failures():
    clock, advance = _make_clock()
    window = timedelta(minutes=10)
    limiter = RateLimiter(max_attempts=3, lockout_window=window, clock=clock)

    # Record 2 failures at t=0
    limiter.record_failure("alice")
    limiter.record_failure("alice")

    # Advance past the window so these 2 will be pruned
    advance(window + timedelta(seconds=1))

    # Record 2 more failures at t=10:01
    limiter.record_failure("alice")
    limiter.record_failure("alice")

    # Only 2 recent failures remain, below threshold of 3
    assert limiter.is_locked("alice") is False


# --- Test 4: failures accumulate across the window boundary when not yet expired ---

def test_failures_within_window_accumulate():
    clock, advance = _make_clock()
    window = timedelta(minutes=10)
    limiter = RateLimiter(max_attempts=3, lockout_window=window, clock=clock)

    limiter.record_failure("alice")
    advance(timedelta(minutes=3))
    limiter.record_failure("alice")
    advance(timedelta(minutes=3))
    limiter.record_failure("alice")

    # All 3 within the 10-minute window
    assert limiter.is_locked("alice") is True


# --- Test 5: default parameters use max_attempts=5 and lockout_window=15min ---

def test_default_parameters():
    clock, advance = _make_clock()
    limiter = RateLimiter(clock=clock)

    # 4 failures should not lock
    for _ in range(4):
        limiter.record_failure("alice")
    assert limiter.is_locked("alice") is False

    # 5th failure triggers lockout
    limiter.record_failure("alice")
    assert limiter.is_locked("alice") is True

    # Should clear after 15 minutes
    advance(timedelta(minutes=15, seconds=1))
    assert limiter.is_locked("alice") is False


# --- Test 6: recording a failure while already locked does not break state ---

def test_record_failure_while_locked():
    clock, _ = _make_clock()
    limiter = RateLimiter(max_attempts=2, clock=clock)

    limiter.record_failure("alice")
    limiter.record_failure("alice")
    assert limiter.is_locked("alice") is True

    # Additional failures should not raise or corrupt state
    limiter.record_failure("alice")
    assert limiter.is_locked("alice") is True


# --- Test 7: exact boundary — failures at exactly max_attempts locks ---

def test_exact_boundary_at_max_attempts():
    clock, _ = _make_clock()
    limiter = RateLimiter(max_attempts=1, clock=clock)

    assert limiter.is_locked("alice") is False
    limiter.record_failure("alice")
    assert limiter.is_locked("alice") is True


# --- Test 8: failures exactly at window cutoff are pruned (ts > cutoff, not >=) ---

def test_failure_at_exact_cutoff_is_pruned():
    clock, advance = _make_clock()
    window = timedelta(minutes=10)
    limiter = RateLimiter(max_attempts=1, lockout_window=window, clock=clock)

    limiter.record_failure("alice")
    assert limiter.is_locked("alice") is True

    # Advance exactly to the window boundary
    advance(window)
    # The failure at t=0 has ts == cutoff (now - window), and the code
    # keeps only ts > cutoff, so it should be pruned
    assert limiter.is_locked("alice") is False


# --- Test 9: reset one user does not affect another ---

def test_reset_does_not_affect_other_users():
    clock, _ = _make_clock()
    limiter = RateLimiter(max_attempts=2, clock=clock)

    for _ in range(2):
        limiter.record_failure("alice")
        limiter.record_failure("bob")

    assert limiter.is_locked("alice") is True
    assert limiter.is_locked("bob") is True

    limiter.reset("alice")
    assert limiter.is_locked("alice") is False
    assert limiter.is_locked("bob") is True


# --- Test 10: can re-lock after reset and new failures ---

def test_relock_after_reset():
    clock, _ = _make_clock()
    limiter = RateLimiter(max_attempts=2, clock=clock)

    limiter.record_failure("alice")
    limiter.record_failure("alice")
    assert limiter.is_locked("alice") is True

    limiter.reset("alice")
    assert limiter.is_locked("alice") is False

    limiter.record_failure("alice")
    limiter.record_failure("alice")
    assert limiter.is_locked("alice") is True
