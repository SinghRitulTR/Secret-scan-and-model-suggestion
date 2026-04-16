"""Extended rate-limiter integration tests for UserAuthService."""

import hashlib
import os
from datetime import datetime, timedelta

import pyotp
import pytest

from src.auth.backup_code_service import BackupCodeService
from src.auth.rate_limiter import RateLimiter
from src.auth.totp_service import TOTPService
from src.auth.user_auth_service import UserAuthService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PBKDF2_ITERATIONS = 600_000


def _hash_password(password: str, salt: bytes) -> str:
    """Return a PBKDF2-HMAC-SHA256 hex digest matching UserAuthService._HASH_ITERATIONS."""
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, _PBKDF2_ITERATIONS
    ).hex()


def _make_user_entry(password: str) -> dict:
    """Return a user_store dict entry with correct password_hash + password_salt fields."""
    salt = os.urandom(16)
    return {
        "password_hash": _hash_password(password, salt),
        "password_salt": salt.hex(),
    }


def _make_clock(start: datetime = datetime(2026, 1, 1)):
    """Return a callable clock whose current time can be advanced."""
    state = {"now": start}

    def clock() -> datetime:
        return state["now"]

    def advance(delta: timedelta) -> None:
        state["now"] += delta

    return clock, advance


@pytest.fixture
def user_store():
    return {
        "alice": _make_user_entry("s3cr3t"),
        "bob": _make_user_entry("hunter2"),
    }


def _build_service(user_store, max_attempts=3):
    """Create UserAuthService wired with a rate limiter and return (auth_svc, totp_svc, backup_svc, limiter, advance)."""
    clock, advance = _make_clock()
    limiter = RateLimiter(max_attempts=max_attempts, clock=clock)
    totp_svc = TOTPService()
    backup_svc = BackupCodeService()
    auth_svc = UserAuthService(totp_svc, backup_svc, user_store, rate_limiter=limiter)
    return auth_svc, totp_svc, backup_svc, limiter, advance


def _enroll_totp(totp_svc, user_id):
    """Enroll and activate TOTP for a user, return the pyotp.TOTP helper."""
    secret, _ = totp_svc.generate_secret(user_id)
    totp = pyotp.TOTP(secret)
    code = totp.now()
    totp_svc.activate_secret(user_id, secret, code)
    return totp


# --- Test 1: invalid TOTP code records a failure ---

def test_invalid_totp_records_failure(user_store):
    auth_svc, totp_svc, _, limiter, _ = _build_service(user_store)
    _enroll_totp(totp_svc, "alice")

    auth_svc.authenticate("alice", "s3cr3t", totp_code="000000")

    assert limiter.is_locked("alice") is False  # 1 failure < 3 max
    auth_svc.authenticate("alice", "s3cr3t", totp_code="000000")
    auth_svc.authenticate("alice", "s3cr3t", totp_code="000000")

    assert limiter.is_locked("alice") is True


# --- Test 2: invalid backup code records a failure ---

def test_invalid_backup_code_records_failure(user_store):
    auth_svc, totp_svc, _, limiter, _ = _build_service(user_store)
    _enroll_totp(totp_svc, "alice")

    for _ in range(3):
        auth_svc.authenticate("alice", "s3cr3t", backup_code="BOGUS-CODE")

    assert limiter.is_locked("alice") is True


# --- Test 3: 2FA-required signal does NOT record a failure ---

def test_2fa_required_does_not_record_failure(user_store):
    auth_svc, totp_svc, _, limiter, _ = _build_service(user_store)
    _enroll_totp(totp_svc, "alice")

    # Password correct, no 2FA code provided -> "2FA required" signal
    for _ in range(5):
        result = auth_svc.authenticate("alice", "s3cr3t")
        assert result.requires_2fa is True

    # Should NOT be locked — "2FA required" is a flow signal, not a failure
    assert limiter.is_locked("alice") is False


# --- Test 4: lockout blocks correct password + TOTP ---

def test_lockout_blocks_correct_credentials_with_totp(user_store):
    auth_svc, totp_svc, _, limiter, _ = _build_service(user_store)
    totp = _enroll_totp(totp_svc, "alice")

    # Trigger lockout with wrong passwords
    for _ in range(3):
        auth_svc.authenticate("alice", "wrong")

    # Even correct password + valid TOTP should be blocked
    verify_code = totp.at(datetime.utcnow() + timedelta(seconds=30))
    result = auth_svc.authenticate("alice", "s3cr3t", totp_code=verify_code)
    assert result.success is False
    assert result.reason == "Account temporarily locked"


# --- Test 5: different users are isolated ---

def test_rate_limiter_isolates_users(user_store):
    auth_svc, _, _, limiter, _ = _build_service(user_store)

    # Lock out alice
    for _ in range(3):
        auth_svc.authenticate("alice", "wrong")

    assert limiter.is_locked("alice") is True

    # Bob should still authenticate fine
    result = auth_svc.authenticate("bob", "hunter2")
    assert result.success is True


# --- Test 6: successful TOTP auth resets the rate limiter ---

def test_successful_totp_resets_rate_limiter(user_store):
    auth_svc, totp_svc, _, limiter, _ = _build_service(user_store)
    totp = _enroll_totp(totp_svc, "alice")

    # Record 2 failures (below threshold of 3)
    auth_svc.authenticate("alice", "wrong")
    auth_svc.authenticate("alice", "wrong")

    # Successful auth with TOTP should reset counter.
    # Use +60s to guarantee a different time step from the activation code,
    # avoiding replay-guard rejection.
    verify_code = totp.at(datetime.utcnow() + timedelta(seconds=60))
    result = auth_svc.authenticate("alice", "s3cr3t", totp_code=verify_code)
    assert result.success is True

    # Two more failures should NOT lock (counter was reset)
    auth_svc.authenticate("alice", "wrong")
    auth_svc.authenticate("alice", "wrong")
    assert limiter.is_locked("alice") is False


# --- Test 7: successful backup code auth resets the rate limiter ---

def test_successful_backup_code_resets_rate_limiter(user_store):
    auth_svc, totp_svc, backup_svc, limiter, _ = _build_service(user_store)
    _enroll_totp(totp_svc, "alice")

    # Record 2 failures
    auth_svc.authenticate("alice", "wrong")
    auth_svc.authenticate("alice", "wrong")

    # Successful auth with backup code resets counter
    codes = backup_svc.generate_codes("alice")
    result = auth_svc.authenticate("alice", "s3cr3t", backup_code=codes[0])
    assert result.success is True

    # Two more failures should NOT lock
    auth_svc.authenticate("alice", "wrong")
    auth_svc.authenticate("alice", "wrong")
    assert limiter.is_locked("alice") is False


# --- Test 8: locked user gets locked response even for nonexistent user ---

def test_lockout_for_nonexistent_user():
    clock, _ = _make_clock()
    limiter = RateLimiter(max_attempts=2, clock=clock)
    auth_svc = UserAuthService(
        TOTPService(), BackupCodeService(), {}, rate_limiter=limiter,
    )

    # Trigger lockout on a user not in the store
    auth_svc.authenticate("ghost", "pw")
    auth_svc.authenticate("ghost", "pw")

    result = auth_svc.authenticate("ghost", "pw")
    assert result.success is False
    assert result.reason == "Account temporarily locked"


# --- Test 9: mixed failure types accumulate ---

def test_mixed_failure_types_accumulate(user_store):
    auth_svc, totp_svc, _, limiter, _ = _build_service(user_store)
    _enroll_totp(totp_svc, "alice")

    # 1 password failure
    auth_svc.authenticate("alice", "wrong")
    # 1 TOTP failure
    auth_svc.authenticate("alice", "s3cr3t", totp_code="000000")
    # 1 backup code failure
    auth_svc.authenticate("alice", "s3cr3t", backup_code="BOGUS")

    # 3 total failures -> locked
    assert limiter.is_locked("alice") is True


# --- Test 10: successful no-TOTP auth resets rate limiter ---

def test_successful_no_totp_auth_resets_rate_limiter(user_store):
    auth_svc, _, _, limiter, _ = _build_service(user_store)

    # Record 2 failures
    auth_svc.authenticate("alice", "wrong")
    auth_svc.authenticate("alice", "wrong")

    # Successful password-only login resets
    result = auth_svc.authenticate("alice", "s3cr3t")
    assert result.success is True

    # Verify reset happened: 2 more failures should not lock
    auth_svc.authenticate("alice", "wrong")
    auth_svc.authenticate("alice", "wrong")
    assert limiter.is_locked("alice") is False
