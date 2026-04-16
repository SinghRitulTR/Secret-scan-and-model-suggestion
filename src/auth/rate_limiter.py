import threading
from datetime import datetime, timedelta
from typing import Callable, Dict, List


class RateLimiter:
    """
    Tracks failed authentication attempts per user and enforces
    a temporary lockout after a configurable number of failures
    within a sliding time window.

    Thread-safety: all mutations of _failures are protected by _lock so that
    concurrent authentication requests cannot bypass the lockout through a
    check-then-act (TOCTOU) race condition.
    """

    def __init__(
        self,
        max_attempts: int = 5,
        lockout_window: timedelta = timedelta(minutes=15),
        clock: Callable[[], datetime] = datetime.utcnow,
    ) -> None:
        self._max_attempts = max_attempts
        self._lockout_window = lockout_window
        self._clock = clock
        self._failures: Dict[str, List[datetime]] = {}
        # Protects _failures against concurrent read-modify-write races.
        self._lock = threading.Lock()

    def is_locked(self, user_id: str) -> bool:
        """Return True if user_id has reached max_attempts within the lockout window."""
        with self._lock:
            self._prune_unlocked(user_id)
            failures = self._failures.get(user_id, [])
            return len(failures) >= self._max_attempts

    def record_failure(self, user_id: str) -> None:
        """Record a failed authentication attempt for user_id."""
        with self._lock:
            self._prune_unlocked(user_id)
            self._failures.setdefault(user_id, []).append(self._clock())

    def reset(self, user_id: str) -> None:
        """Clear all failure records for user_id."""
        with self._lock:
            self._failures.pop(user_id, None)

    def _prune_unlocked(self, user_id: str) -> None:
        """Remove failure timestamps older than the lockout window.

        Must be called with _lock already held.
        """
        entries = self._failures.get(user_id)
        if entries is None:
            return
        cutoff = self._clock() - self._lockout_window
        self._failures[user_id] = [ts for ts in entries if ts > cutoff]

    # Keep the old name as an internal alias so existing call-sites that call
    # _prune directly (e.g. in subclasses or tests) continue to work while the
    # public API now uses the locked variant.
    _prune = _prune_unlocked
