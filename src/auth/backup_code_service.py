import hashlib
import hmac
import os
import secrets
from datetime import datetime
from typing import Dict, List, Optional

from .models import BackupCode


class BackupCodeService:
    CODE_COUNT = 10
    CODE_LENGTH = 8
    # NIST SP 800-132 (2023) recommends >= 600,000 iterations for PBKDF2-SHA256.
    # The previous value of 100_000 met the 2021 OWASP minimum but is now below
    # the current guidance.
    ITERATIONS = 600_000

    def __init__(self, code_store: Optional[Dict[str, List[BackupCode]]] = None) -> None:
        # Maps user_id -> list of BackupCode
        self._store: Dict[str, List[BackupCode]] = code_store if code_store is not None else {}

    def _hash_code(self, code: str, salt: bytes) -> str:
        """Return hex digest of PBKDF2-HMAC-SHA256 for the given code and salt."""
        dk = hashlib.pbkdf2_hmac(
            "sha256",
            code.encode("utf-8"),
            salt,
            self.ITERATIONS,
        )
        return dk.hex()

    def generate_codes(self, user_id: str) -> List[str]:
        """
        Generate CODE_COUNT fresh backup codes, store their hashes, and return
        the plaintext codes. Replaces any existing codes for user_id.
        """
        plaintext_codes: List[str] = []
        hashed_codes: List[BackupCode] = []

        for _ in range(self.CODE_COUNT):
            code = secrets.token_urlsafe(self.CODE_LENGTH)
            salt = os.urandom(16)
            code_hash = self._hash_code(code, salt)
            hashed_codes.append(
                BackupCode(
                    user_id=user_id,
                    code_hash=code_hash,
                    salt=salt,
                    used=False,
                    created_at=datetime.utcnow(),
                )
            )
            plaintext_codes.append(code)

        self._store[user_id] = hashed_codes
        return plaintext_codes

    def verify_code(self, user_id: str, submitted_code: str) -> bool:
        """
        Verify submitted_code against stored hashes using constant-time comparison.
        Marks the matched code as used. Returns True if a valid unused code matched.
        """
        codes = self._store.get(user_id, [])
        for backup_code in codes:
            if backup_code.used:
                continue
            candidate_hash = self._hash_code(submitted_code, backup_code.salt)
            if hmac.compare_digest(candidate_hash, backup_code.code_hash):
                backup_code.used = True
                return True
        return False

    def remaining_count(self, user_id: str) -> int:
        """Return the number of unused backup codes for user_id."""
        codes = self._store.get(user_id, [])
        return sum(1 for c in codes if not c.used)
