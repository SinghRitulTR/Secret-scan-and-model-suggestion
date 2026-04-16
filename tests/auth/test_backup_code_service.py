"""Tests for BackupCodeService — 6 tests, using in-memory store."""

import pytest

from src.auth.backup_code_service import BackupCodeService


@pytest.fixture
def service():
    return BackupCodeService()


# --- Test 1: generate_codes returns CODE_COUNT plaintext codes ---

def test_generate_codes_returns_correct_count(service):
    codes = service.generate_codes("alice")
    assert len(codes) == BackupCodeService.CODE_COUNT


# --- Test 2: generated codes are unique strings ---

def test_generate_codes_are_unique(service):
    codes = service.generate_codes("alice")
    assert len(set(codes)) == len(codes)


# --- Test 3: verify_code succeeds with a valid code ---

def test_verify_code_accepts_valid_code(service):
    codes = service.generate_codes("bob")
    assert service.verify_code("bob", codes[0]) is True


# --- Test 4: verify_code marks the code as used (cannot reuse) ---

def test_verify_code_cannot_reuse(service):
    codes = service.generate_codes("carol")
    service.verify_code("carol", codes[0])
    assert service.verify_code("carol", codes[0]) is False


# --- Test 5: verify_code rejects a code that was never generated ---

def test_verify_code_rejects_unknown_code(service):
    service.generate_codes("dave")
    assert service.verify_code("dave", "not-a-real-code") is False


# --- Test 6: remaining_count decrements after each use ---

def test_remaining_count_decrements(service):
    codes = service.generate_codes("eve")
    assert service.remaining_count("eve") == BackupCodeService.CODE_COUNT

    service.verify_code("eve", codes[0])
    assert service.remaining_count("eve") == BackupCodeService.CODE_COUNT - 1

    service.verify_code("eve", codes[1])
    assert service.remaining_count("eve") == BackupCodeService.CODE_COUNT - 2
