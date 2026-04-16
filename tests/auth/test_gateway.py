"""Tests for gateway.py — 6 tests covering require_admin_2fa decorator."""

import pytest

from src.auth.gateway import RequestContext, TwoFactorRequiredError, require_admin_2fa


# Helper: a simple admin-only function using the decorator

@require_admin_2fa
def admin_action(context: RequestContext) -> str:
    return "action performed"


# Helper: a function that accepts context as keyword argument

@require_admin_2fa
def admin_dashboard(*, context: RequestContext) -> str:
    return "dashboard"


# --- Test 1: non-admin user passes without 2FA ---

def test_non_admin_passes_without_2fa():
    ctx = RequestContext(user_id="alice", roles=["viewer"])
    result = admin_action(ctx)
    assert result == "action performed"


# --- Test 2: admin with totp_verified passes ---

def test_admin_with_totp_verified_passes():
    ctx = RequestContext(user_id="admin1", roles=["admin"], totp_verified=True)
    result = admin_action(ctx)
    assert result == "action performed"


# --- Test 3: admin with backup_verified passes ---

def test_admin_with_backup_verified_passes():
    ctx = RequestContext(user_id="admin2", roles=["admin"], backup_verified=True)
    result = admin_action(ctx)
    assert result == "action performed"


# --- Test 4: admin without any 2FA raises TwoFactorRequiredError ---

def test_admin_without_2fa_raises():
    ctx = RequestContext(user_id="admin3", roles=["admin"])
    with pytest.raises(TwoFactorRequiredError):
        admin_action(ctx)


# --- Test 5: TwoFactorRequiredError has http_status 401 ---

def test_two_factor_error_has_correct_status():
    err = TwoFactorRequiredError()
    assert err.http_status == 401


# --- Test 6: decorator works with context passed as keyword argument ---

def test_decorator_works_with_keyword_context():
    ctx = RequestContext(user_id="admin4", roles=["admin"], totp_verified=True)
    result = admin_dashboard(context=ctx)
    assert result == "dashboard"
