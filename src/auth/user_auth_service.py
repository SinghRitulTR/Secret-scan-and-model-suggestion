import hashlib
import hmac
import warnings
from typing import Dict, List, Optional, Tuple

from .backup_code_service import BackupCodeService
from .models import AuthResult
from .rate_limiter import RateLimiter
from .totp_service import TOTPService


class UserAuthService:
    """
    Orchestrates password authentication and two-factor authentication.

    user_store format: {user_id: {"password_hash": str, "password_salt": str}}

    IMPORTANT: Passwords must be stored as hashed values (PBKDF2-HMAC-SHA256 or
    bcrypt/argon2 in production).  This implementation uses PBKDF2-HMAC-SHA256
    with a per-user salt as a minimum secure baseline.  Plain-text passwords in
    user_store are rejected at runtime with a warning and will fail authentication.
    """

    _HASH_ITERATIONS = 600_000  # NIST SP 800-132 (2023) recommendation for PBKDF2-SHA256

    def __init__(
        self,
        totp_service: TOTPService,
        backup_code_service: BackupCodeService,
        user_store: Optional[Dict[str, Dict]] = None,
        rate_limiter: Optional[RateLimiter] = None,
    ) -> None:
        self._totp = totp_service
        self._backup = backup_code_service
        self._user_store: Dict[str, Dict] = user_store if user_store is not None else {}
        self._rate_limiter = rate_limiter

    def enroll_totp(self, user_id: str) -> Tuple[str, str, List[str]]:
        """
        Begin TOTP enrollment for user_id.
        Returns (otpauth_uri, secret, backup_codes).
        The secret must be passed back to confirm_enrollment() to activate the credential.
        The secret is not yet persisted as active — caller must call confirm_enrollment().
        """
        secret, otpauth_uri = self._totp.generate_secret(user_id)
        backup_codes = self._backup.generate_codes(user_id)
        return otpauth_uri, secret, backup_codes

    def confirm_enrollment(self, user_id: str, secret: str, confirmation_code: str) -> bool:
        """
        Confirm TOTP enrollment by verifying confirmation_code against secret.
        Activates the credential on success.
        """
        return self._totp.activate_secret(user_id, secret, confirmation_code)

    def authenticate(
        self,
        user_id: str,
        password: str,
        totp_code: Optional[str] = None,
        backup_code: Optional[str] = None,
    ) -> AuthResult:
        """
        Step 1: Verify password (plaintext stub comparison against user_store).
        Step 2: If user has active TOTP, require totp_code or backup_code.
        Step 3: Verify second factor and return AuthResult.
        """
        if self._rate_limiter and self._rate_limiter.is_locked(user_id):
            return AuthResult(success=False, reason="Account temporarily locked")

        user = self._user_store.get(user_id)

        # Detect legacy plaintext-password entries and refuse them.  Production
        # records must carry "password_hash" + "password_salt"; the old "password"
        # key is plaintext and is a critical cryptographic failure (OWASP A02).
        if user is not None and "password" in user and "password_hash" not in user:
            warnings.warn(
                f"user_store entry for '{user_id}' contains a plaintext 'password' field. "
                "Store hashed credentials ('password_hash' + 'password_salt') instead.",
                UserWarning,
                stacklevel=2,
            )
            # Treat as invalid to prevent plaintext-password logins.
            user = None

        # Derive a candidate hash from the submitted password so that the
        # constant-time comparison below always operates on equal-length byte
        # strings, preventing timing-based user-enumeration attacks regardless
        # of whether the user exists.
        if user is not None:
            stored_hash: str = user.get("password_hash", "")
            stored_salt_hex: str = user.get("password_salt", "")
            try:
                salt = bytes.fromhex(stored_salt_hex)
            except ValueError:
                salt = b""
        else:
            # Dummy values — still run PBKDF2 so timing is indistinguishable
            # from a real user lookup (constant-time user enumeration defence).
            stored_hash = "0" * 64
            salt = b"\x00" * 16

        candidate_hash = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            self._HASH_ITERATIONS,
        ).hex()

        # Constant-time comparison prevents password oracle attacks.
        # compare_digest ALWAYS runs — even when user is None — so the branch
        # condition cannot leak user-ID existence via a timing side-channel.
        password_ok = hmac.compare_digest(stored_hash, candidate_hash)
        if user is None or not password_ok:
            if self._rate_limiter:
                self._rate_limiter.record_failure(user_id)
            return AuthResult(success=False, reason="Invalid credentials")

        # Check whether TOTP is active for this user
        credential = self._totp.get_credential(user_id)
        totp_active = credential is not None and credential.is_active

        if not totp_active:
            # No second factor required
            if self._rate_limiter:
                self._rate_limiter.reset(user_id)
            return AuthResult(success=True, reason="")

        # Second factor required
        if totp_code is None and backup_code is None:
            # "2FA required" is a flow signal, not a failure
            return AuthResult(success=False, reason="2FA required", requires_2fa=True)

        if totp_code is not None:
            if self._totp.verify_totp(user_id, totp_code):
                if self._rate_limiter:
                    self._rate_limiter.reset(user_id)
                return AuthResult(success=True, reason="")
            if self._rate_limiter:
                self._rate_limiter.record_failure(user_id)
            return AuthResult(success=False, reason="Invalid TOTP code")

        if backup_code is not None:
            if self._backup.verify_code(user_id, backup_code):
                if self._rate_limiter:
                    self._rate_limiter.reset(user_id)
                return AuthResult(success=True, reason="")
            if self._rate_limiter:
                self._rate_limiter.record_failure(user_id)
            return AuthResult(success=False, reason="Invalid backup code")

        if self._rate_limiter:
            self._rate_limiter.record_failure(user_id)
        return AuthResult(success=False, reason="2FA verification failed")
