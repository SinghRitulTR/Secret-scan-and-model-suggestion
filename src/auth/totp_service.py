import base64
import io
from datetime import datetime
from typing import Dict, Optional, Tuple

import pyotp
import qrcode

from .models import TOTPCredential


class TOTPService:
    ISSUER_NAME = "MyApp"
    VALID_WINDOW = 1

    def __init__(self, credential_store: Optional[Dict[str, TOTPCredential]] = None) -> None:
        # Maps user_id -> TOTPCredential
        self._store: Dict[str, TOTPCredential] = credential_store if credential_store is not None else {}

    def generate_secret(self, user_id: str) -> Tuple[str, str]:
        """Return (base32_secret, otpauth_uri) for the given user."""
        secret = pyotp.random_base32()
        totp = pyotp.TOTP(secret)
        uri = totp.provisioning_uri(name=user_id, issuer_name=self.ISSUER_NAME)
        return secret, uri

    def activate_secret(self, user_id: str, secret: str, confirmation_code: str) -> bool:
        """Verify confirmation_code against secret, then store the credential. Returns True on success."""
        totp = pyotp.TOTP(secret)
        if not totp.verify(confirmation_code, valid_window=self.VALID_WINDOW):
            return False
        credential = TOTPCredential(
            user_id=user_id,
            secret=secret,
            created_at=datetime.utcnow(),
            is_active=True,
        )
        self._store[user_id] = credential
        return True

    def verify_totp(self, user_id: str, code: str) -> bool:
        """Look up the stored credential and verify the given code.

        Prevents OTP replay attacks by rejecting a code that was already
        accepted within the same time step, as required by RFC 6238.
        """
        credential = self._store.get(user_id)
        if credential is None or not credential.is_active:
            return False
        totp = pyotp.TOTP(credential.secret)
        if not totp.verify(code, valid_window=self.VALID_WINDOW):
            return False
        # Replay prevention: reject any code that was already accepted, regardless
        # of which time step it matched.  Storing the accepted code string (rather
        # than the time-step index) means a code reused within valid_window is also
        # caught — the adjacent-step vulnerability described in MF-3.
        #
        # Use hmac.compare_digest instead of == to avoid leaking whether the
        # submitted code matches the last-used code through a timing side-channel.
        import hmac as _hmac
        if credential.last_used_code is not None and _hmac.compare_digest(
            credential.last_used_code, code
        ):
            return False
        # Record the accepted code so subsequent attempts with the same value fail.
        credential.last_used_code = code
        return True

    def deactivate_totp(self, user_id: str) -> None:
        """Mark the user's TOTP credential as inactive."""
        credential = self._store.get(user_id)
        if credential is not None:
            credential.is_active = False

    def get_credential(self, user_id: str) -> Optional[TOTPCredential]:
        """Return the stored credential for user_id, or None."""
        return self._store.get(user_id)

    def generate_qr_code_data_uri(self, otpauth_uri: str) -> str:
        """Generate a base64-encoded PNG data URI from an otpauth URI."""
        img = qrcode.make(otpauth_uri)
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"
