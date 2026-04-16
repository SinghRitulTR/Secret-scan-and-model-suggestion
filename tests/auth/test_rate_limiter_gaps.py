"""Gap tests for RateLimiter — edge cases not covered by existing test files."""

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


# --- Test 1: max_attempts=0 locks every user immediately ---

def test_zero_max_attempts_always_locked():
    """When max_attempts is 0, is_locked returns True for any user immediately
    because 0 failures >= 0 max_attempts."""
    clock, _ = _make_clock()
    limiter = RateLimiter(max_attempts=0, clock=clock)

    # No failures recorded — still locked due to 0 threshold
    assert limiter.is_locked("alice") is True


# --- Test 2: zero-length lockout window prunes failures immediately ---

def test_zero_lockout_window_prunes_on_same_tick():
    """When lockout_window=timedelta(0), a failure recorded at time T is at
    exactly the cutoff (T > T - 0 → T > T is False), so it is pruned on the
    very next call to is_locked at the same clock tick."""
    clock, _ = _make_clock()
    limiter = RateLimiter(max_attempts=1, lockout_window=timedelta(0), clock=clock)

    limiter.record_failure("alice")
    # The recorded timestamp equals clock() which equals cutoff, so it is pruned
    assert limiter.is_locked("alice") is False


# --- Test 3: is_locked on a user with an empty failures list after pruning ---

def test_is_locked_after_all_entries_pruned():
    """After the window expires and pruning empties the list, is_locked must
    return False (not raise on an empty list)."""
    clock, advance = _make_clock()
    window = timedelta(minutes=5)
    limiter = RateLimiter(max_attempts=2, lockout_window=window, clock=clock)

    limiter.record_failure("alice")
    advance(window + timedelta(seconds=1))

    # The single old failure is pruned; resulting list is empty
    assert limiter.is_locked("alice") is False


# --- Test 4: record_failure with max_attempts=1 locks on first failure ---

def test_single_failure_locks_with_max_attempts_1():
    """Boundary: with max_attempts=1 a single record_failure immediately locks.
    This differs from the existing test_exact_boundary_at_max_attempts which
    uses is_locked checks interleaved; here we verify the state after one call."""
    clock, _ = _make_clock()
    limiter = RateLimiter(max_attempts=1, clock=clock)

    assert limiter.is_locked("alice") is False
    limiter.record_failure("alice")
    assert limiter.is_locked("alice") is True


# --- Test 5: multiple resets do not corrupt internal state ---

def test_multiple_resets_are_idempotent():
    """Calling reset repeatedly on the same user (with and without prior failures)
    must leave the limiter in a clean, unlocked state."""
    clock, _ = _make_clock()
    limiter = RateLimiter(max_attempts=2, clock=clock)

    limiter.record_failure("alice")
    limiter.reset("alice")
    limiter.reset("alice")  # second reset — user not in _failures dict
    limiter.reset("alice")  # third reset — idempotent

    assert limiter.is_locked("alice") is False

    # Should still track new failures correctly after repeated resets
    limiter.record_failure("alice")
    limiter.record_failure("alice")
    assert limiter.is_locked("alice") is True
