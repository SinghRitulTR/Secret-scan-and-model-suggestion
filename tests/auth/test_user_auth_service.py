"""Tests for UserAuthService — 11 tests, using injected in-memory dependencies."""

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


@pytest.fixture
def user_store():
    return {
        "alice": _make_user_entry("s3cr3t"),
        "bob": _make_user_entry("hunter2"),
    }


@pytest.fixture
def services(user_store):
    totp_svc = TOTPService()
    backup_svc = BackupCodeService()
    auth_svc = UserAuthService(totp_svc, backup_svc, user_store)
    return auth_svc, totp_svc, backup_svc


# --- Test 1: authenticate fails with wrong password ---

def test_authenticate_wrong_password(services):
    auth_svc, _, _ = services
    result = auth_svc.authenticate("alice", "wrong")
    assert result.success is False
    assert result.reason == "Invalid credentials"


# --- Test 2: authenticate succeeds with correct password and no TOTP enrolled ---

def test_authenticate_correct_password_no_totp(services):
    auth_svc, _, _ = services
    result = auth_svc.authenticate("alice", "s3cr3t")
    assert result.success is True
    assert result.requires_2fa is False


# --- Test 3: authenticate signals 2FA required when TOTP active but no code given ---

def test_authenticate_requires_2fa_when_enrolled(services):
    auth_svc, totp_svc, _ = services
    secret, _ = totp_svc.generate_secret("alice")
    code = pyotp.TOTP(secret).now()
    totp_svc.activate_secret("alice", secret, code)

    result = auth_svc.authenticate("alice", "s3cr3t")
    assert result.success is False
    assert result.requires_2fa is True


# --- Test 4: authenticate succeeds with valid TOTP code ---

def test_authenticate_succeeds_with_valid_totp(services):
    auth_svc, totp_svc, _ = services
    secret, _ = totp_svc.generate_secret("alice")
    totp = pyotp.TOTP(secret)
    activation_code = totp.now()
    totp_svc.activate_secret("alice", secret, activation_code)

    # Use the next time-step code to avoid replay-guard rejection
    verify_code = totp.at(datetime.utcnow() + timedelta(seconds=30))
    result = auth_svc.authenticate("alice", "s3cr3t", totp_code=verify_code)
    assert result.success is True


# --- Test 5: authenticate fails with invalid TOTP code ---

def test_authenticate_fails_with_invalid_totp(services):
    auth_svc, totp_svc, _ = services
    secret, _ = totp_svc.generate_secret("alice")
    code = pyotp.TOTP(secret).now()
    totp_svc.activate_secret("alice", secret, code)

    result = auth_svc.authenticate("alice", "s3cr3t", totp_code="000000")
    assert result.success is False
    assert "TOTP" in result.reason


# --- Test 6: authenticate succeeds with valid backup code ---

def test_authenticate_succeeds_with_backup_code(services):
    auth_svc, totp_svc, backup_svc = services
    # Activate TOTP so second factor is required
    secret, _ = totp_svc.generate_secret("alice")
    code = pyotp.TOTP(secret).now()
    totp_svc.activate_secret("alice", secret, code)

    # Generate backup codes directly
    backup_codes = backup_svc.generate_codes("alice")
    result = auth_svc.authenticate("alice", "s3cr3t", backup_code=backup_codes[0])
    assert result.success is True


# --- Test 7: enroll_totp returns URI, secret, and backup codes ---

def test_enroll_totp_returns_uri_secret_and_codes(services):
    auth_svc, _, _ = services
    uri, secret, codes = auth_svc.enroll_totp("bob")
    assert uri.startswith("otpauth://totp/")
    assert isinstance(secret, str) and len(secret) > 0
    assert len(codes) == 10


# --- Rate-limiter integration helpers ---

def _make_clock(start: datetime = datetime(2026, 1, 1)):
    """Return a callable clock whose current time can be advanced."""
    state = {"now": start}

    def clock() -> datetime:
        return state["now"]

    def advance(delta: timedelta) -> None:
        state["now"] += delta

    return clock, advance


# --- Test 8: lockout after N failed attempts ---

def test_lockout_after_n_failed_attempts(user_store):
    clock, _ = _make_clock()
    limiter = RateLimiter(max_attempts=3, clock=clock)
    auth_svc = UserAuthService(TOTPService(), BackupCodeService(), user_store, rate_limiter=limiter)

    for _ in range(3):
        auth_svc.authenticate("alice", "wrong")

    result = auth_svc.authenticate("alice", "s3cr3t")
    assert result.success is False
    assert result.reason == "Account temporarily locked"


# --- Test 9: lockout lifts after window ---

def test_lockout_lifts_after_window(user_store):
    clock, advance = _make_clock()
    window = timedelta(minutes=15)
    limiter = RateLimiter(max_attempts=3, lockout_window=window, clock=clock)
    auth_svc = UserAuthService(TOTPService(), BackupCodeService(), user_store, rate_limiter=limiter)

    for _ in range(3):
        auth_svc.authenticate("alice", "wrong")

    assert auth_svc.authenticate("alice", "s3cr3t").success is False

    advance(window + timedelta(seconds=1))
    result = auth_svc.authenticate("alice", "s3cr3t")
    assert result.success is True


# --- Test 10: successful auth resets counter ---

def test_successful_auth_resets_counter(user_store):
    clock, _ = _make_clock()
    limiter = RateLimiter(max_attempts=3, clock=clock)
    auth_svc = UserAuthService(TOTPService(), BackupCodeService(), user_store, rate_limiter=limiter)

    # Record 2 failures (below threshold)
    auth_svc.authenticate("alice", "wrong")
    auth_svc.authenticate("alice", "wrong")

    # Successful login resets the counter
    result = auth_svc.authenticate("alice", "s3cr3t")
    assert result.success is True

    # Two more failures should NOT lock (counter was reset)
    auth_svc.authenticate("alice", "wrong")
    auth_svc.authenticate("alice", "wrong")
    result = auth_svc.authenticate("alice", "s3cr3t")
    assert result.success is True


# --- Test 11: no rate limiter is backwards compatible ---

def test_no_rate_limiter_backwards_compatible(user_store):
    auth_svc = UserAuthService(TOTPService(), BackupCodeService(), user_store)

    # Multiple failures should not cause lockout when no rate limiter is set
    for _ in range(10):
        auth_svc.authenticate("alice", "wrong")

    result = auth_svc.authenticate("alice", "s3cr3t")
    assert result.success is True
