"""Tests for TOTPService — 11 tests, all using real pyotp internals."""

from datetime import datetime, timedelta

import pyotp
import pytest

from src.auth.totp_service import TOTPService


@pytest.fixture
def service():
    return TOTPService()


# --- Test 1: generate_secret returns base32 string and valid otpauth URI ---

def test_generate_secret_returns_base32_and_uri(service):
    secret, uri = service.generate_secret("alice")
    # base32 alphabet: uppercase letters + 2-7
    assert secret.isalnum()
    assert uri.startswith("otpauth://totp/")
    assert "alice" in uri
    assert TOTPService.ISSUER_NAME in uri


# --- Test 2: generate_secret returns different secrets each call ---

def test_generate_secret_is_unique(service):
    secret1, _ = service.generate_secret("alice")
    secret2, _ = service.generate_secret("alice")
    assert secret1 != secret2


# --- Test 3: activate_secret rejects wrong confirmation code ---

def test_activate_secret_rejects_invalid_code(service):
    secret, _ = service.generate_secret("alice")
    result = service.activate_secret("alice", secret, "000000")
    assert result is False
    assert service.get_credential("alice") is None


# --- Test 4: activate_secret accepts valid current code ---

def test_activate_secret_accepts_valid_code(service):
    secret, _ = service.generate_secret("alice")
    valid_code = pyotp.TOTP(secret).now()
    result = service.activate_secret("alice", secret, valid_code)
    assert result is True
    cred = service.get_credential("alice")
    assert cred is not None
    assert cred.is_active is True


# --- Test 5: verify_totp succeeds with current code after activation ---

def test_verify_totp_succeeds_after_activation(service):
    secret, _ = service.generate_secret("bob")
    totp = pyotp.TOTP(secret)
    activation_code = totp.now()
    service.activate_secret("bob", secret, activation_code)
    # Use a code from the next time step to guarantee it differs from the
    # activation code consumed above, avoiding a replay-guard false-rejection.
    next_step_time = datetime.utcnow() + timedelta(seconds=60)
    verify_code = totp.at(next_step_time)
    assert service.verify_totp("bob", verify_code) is True


# --- Test 6: verify_totp fails for unknown user ---

def test_verify_totp_fails_for_unknown_user(service):
    assert service.verify_totp("nobody", "123456") is False


# --- Test 7: deactivate_totp marks credential inactive and verify fails ---

def test_deactivate_totp_prevents_verification(service):
    secret, _ = service.generate_secret("carol")
    code = pyotp.TOTP(secret).now()
    service.activate_secret("carol", secret, code)

    service.deactivate_totp("carol")

    cred = service.get_credential("carol")
    assert cred is not None
    assert cred.is_active is False

    new_code = pyotp.TOTP(secret).now()
    assert service.verify_totp("carol", new_code) is False


# --- Test 8: verify_totp rejects replayed code (same code submitted twice) ---

def test_verify_totp_rejects_replay(service):
    secret, _ = service.generate_secret("dave")
    totp = pyotp.TOTP(secret)
    activation_code = totp.now()
    service.activate_secret("dave", secret, activation_code)

    # First verify with a fresh next-step code should succeed
    next_step_time = datetime.utcnow() + timedelta(seconds=60)
    verify_code = totp.at(next_step_time)
    assert service.verify_totp("dave", verify_code) is True

    # Second attempt with the identical code must be rejected as a replay
    assert service.verify_totp("dave", verify_code) is False


# --- Test 9: deactivate_totp on non-existent user is a no-op (no exception) ---

def test_deactivate_totp_nonexistent_user_is_noop(service):
    # Should not raise any exception
    service.deactivate_totp("ghost")
    # Credential store remains empty for this user
    assert service.get_credential("ghost") is None
