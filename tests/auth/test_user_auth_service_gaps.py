"""Gap tests for UserAuthService — behaviours not covered by existing test files.

NOTE: The existing test files (test_user_auth_service.py and
test_user_auth_service_ratelimit.py) use plaintext 'password' entries in the
user_store, which the updated implementation rejects.  These gap tests use the
correct 'password_hash' + 'password_salt' format so they pass against the live
implementation.
"""

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
    """Return a (clock, advance) pair for deterministic time control."""
    state = {"now": start}

    def clock() -> datetime:
        return state["now"]

    def advance(delta: timedelta) -> None:
        state["now"] += delta

    return clock, advance


def _enroll_totp(totp_svc: TOTPService, user_id: str) -> pyotp.TOTP:
    """Enroll and activate TOTP for user_id, return the pyotp.TOTP helper."""
    secret, _ = totp_svc.generate_secret(user_id)
    totp = pyotp.TOTP(secret)
    totp_svc.activate_secret(user_id, secret, totp.now())
    return totp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def alice_password() -> str:
    return "correct-horse-battery-staple"


@pytest.fixture
def user_store(alice_password):
    return {
        "alice": _make_user_entry(alice_password),
        "bob": _make_user_entry("hunter2"),
    }


@pytest.fixture
def services(user_store):
    totp_svc = TOTPService()
    backup_svc = BackupCodeService()
    auth_svc = UserAuthService(totp_svc, backup_svc, user_store)
    return auth_svc, totp_svc, backup_svc


# ---------------------------------------------------------------------------
# confirm_enrollment — not covered anywhere in the existing test suite
# ---------------------------------------------------------------------------

def test_confirm_enrollment_returns_true_on_valid_code(services):
    """confirm_enrollment returns True when the confirmation code is valid."""
    auth_svc, totp_svc, _ = services
    secret, _ = totp_svc.generate_secret("alice")
    code = pyotp.TOTP(secret).now()

    result = auth_svc.confirm_enrollment("alice", secret, code)

    assert result is True


def test_confirm_enrollment_returns_false_on_invalid_code(services):
    """confirm_enrollment returns False when the confirmation code is wrong."""
    auth_svc, totp_svc, _ = services
    secret, _ = totp_svc.generate_secret("alice")

    result = auth_svc.confirm_enrollment("alice", secret, "000000")

    assert result is False


def test_confirm_enrollment_activates_credential(user_store, alice_password):
    """After a successful confirm_enrollment the credential is active, so
    password-only authentication must signal 2FA required."""
    totp_svc = TOTPService()
    backup_svc = BackupCodeService()
    auth_svc = UserAuthService(totp_svc, backup_svc, user_store)

    secret, _ = totp_svc.generate_secret("alice")
    # Use a code from a future time-step so activate_secret does not consume
    # the same code that verify_totp would see later.
    code = pyotp.TOTP(secret).now()
    auth_svc.confirm_enrollment("alice", secret, code)

    # TOTP is now active — password-only auth must signal 2FA required
    result = auth_svc.authenticate("alice", alice_password)
    assert result.success is False
    assert result.requires_2fa is True


# ---------------------------------------------------------------------------
# Invalid backup code — reason string assertion
# ---------------------------------------------------------------------------

def test_authenticate_fails_with_invalid_backup_code_reason(user_store, alice_password):
    """Authenticate with an invalid backup code returns the 'Invalid backup code' reason."""
    totp_svc = TOTPService()
    backup_svc = BackupCodeService()
    auth_svc = UserAuthService(totp_svc, backup_svc, user_store)
    _enroll_totp(totp_svc, "alice")

    result = auth_svc.authenticate("alice", alice_password, backup_code="BAD-CODE")

    assert result.success is False
    assert result.reason == "Invalid backup code"


# ---------------------------------------------------------------------------
# Both totp_code and backup_code supplied simultaneously
# ---------------------------------------------------------------------------

def test_totp_evaluated_before_backup_code_when_both_supplied(user_store, alice_password):
    """When both totp_code and backup_code are supplied, totp_code is evaluated
    first. If it is invalid the call fails with 'Invalid TOTP code' without
    falling through to try the (valid) backup_code, proving evaluation order."""
    totp_svc = TOTPService()
    backup_svc = BackupCodeService()
    auth_svc = UserAuthService(totp_svc, backup_svc, user_store)
    _enroll_totp(totp_svc, "alice")

    backup_codes = backup_svc.generate_codes("alice")

    result = auth_svc.authenticate(
        "alice", alice_password, totp_code="000000", backup_code=backup_codes[0]
    )

    assert result.success is False
    assert result.reason == "Invalid TOTP code"


# ---------------------------------------------------------------------------
# Plaintext 'password' key in user_store is rejected
# ---------------------------------------------------------------------------

def test_plaintext_password_entry_is_rejected_with_warning():
    """A user_store entry with a plaintext 'password' key (no 'password_hash')
    is treated as if the user does not exist, returning Invalid credentials
    and emitting a UserWarning."""
    user_store = {"alice": {"password": "s3cr3t"}}
    auth_svc = UserAuthService(TOTPService(), BackupCodeService(), user_store)

    with pytest.warns(UserWarning, match="plaintext 'password' field"):
        result = auth_svc.authenticate("alice", "s3cr3t")

    assert result.success is False
    assert result.reason == "Invalid credentials"


def test_user_store_entry_with_no_credentials_rejected():
    """A user_store entry that exists but has neither 'password' nor 'password_hash'
    keys fails authentication — the empty stored_hash will not match any real password."""
    user_store = {"alice": {}}  # no password fields at all
    auth_svc = UserAuthService(TOTPService(), BackupCodeService(), user_store)

    result = auth_svc.authenticate("alice", "anything")

    assert result.success is False
    assert result.reason == "Invalid credentials"


# ---------------------------------------------------------------------------
# Rate limiter: TOTP failures leading to lockout block subsequent valid TOTP
# ---------------------------------------------------------------------------

def test_totp_failure_lockout_blocks_subsequent_valid_totp():
    """Invalid TOTP codes accumulate failures; once locked a correct TOTP attempt
    is still rejected with 'Account temporarily locked'."""
    salt = os.urandom(16)
    password = "secure-pass"
    user_store = {
        "alice": {
            "password_hash": _hash_password(password, salt),
            "password_salt": salt.hex(),
        }
    }
    clock, _ = _make_clock()
    limiter = RateLimiter(max_attempts=2, clock=clock)
    totp_svc = TOTPService()
    backup_svc = BackupCodeService()
    auth_svc = UserAuthService(totp_svc, backup_svc, user_store, rate_limiter=limiter)

    totp = _enroll_totp(totp_svc, "alice")

    auth_svc.authenticate("alice", password, totp_code="000000")
    auth_svc.authenticate("alice", password, totp_code="000000")

    # Now locked — a correct TOTP code must still be rejected
    verify_code = totp.at(datetime.utcnow() + timedelta(seconds=30))
    result = auth_svc.authenticate("alice", password, totp_code=verify_code)

    assert result.success is False
    assert result.reason == "Account temporarily locked"


# ---------------------------------------------------------------------------
# Rate limiter: backup code failures leading to lockout block subsequent valid
# ---------------------------------------------------------------------------

def test_backup_code_failure_lockout_blocks_subsequent_valid_backup_code():
    """Invalid backup codes accumulate failures; once locked a correct backup
    code attempt is still rejected with 'Account temporarily locked'."""
    salt = os.urandom(16)
    password = "secure-pass"
    user_store = {
        "alice": {
            "password_hash": _hash_password(password, salt),
            "password_salt": salt.hex(),
        }
    }
    clock, _ = _make_clock()
    limiter = RateLimiter(max_attempts=2, clock=clock)
    totp_svc = TOTPService()
    backup_svc = BackupCodeService()
    auth_svc = UserAuthService(totp_svc, backup_svc, user_store, rate_limiter=limiter)

    _enroll_totp(totp_svc, "alice")
    valid_codes = backup_svc.generate_codes("alice")

    auth_svc.authenticate("alice", password, backup_code="BAD-1")
    auth_svc.authenticate("alice", password, backup_code="BAD-2")

    # Now locked — a valid backup code must still be rejected
    result = auth_svc.authenticate("alice", password, backup_code=valid_codes[0])

    assert result.success is False
    assert result.reason == "Account temporarily locked"


# ---------------------------------------------------------------------------
# authenticate: nonexistent user — no rate limiter, wrong password
# ---------------------------------------------------------------------------

def test_authenticate_nonexistent_user_returns_invalid_credentials():
    """Authenticating a user_id not present in user_store returns Invalid credentials
    (not a KeyError) and does not reveal whether the user exists."""
    auth_svc = UserAuthService(TOTPService(), BackupCodeService(), user_store={})

    result = auth_svc.authenticate("ghost", "any-password")

    assert result.success is False
    assert result.reason == "Invalid credentials"
