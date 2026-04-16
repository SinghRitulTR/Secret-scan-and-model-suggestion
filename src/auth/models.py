from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class TOTPCredential:
    user_id: str
    # The TOTP secret is a sensitive credential.  It is stored as a plain str
    # here because this is an in-memory reference implementation.  In production,
    # encrypt this field at rest (e.g. with a KMS-managed key) before persisting.
    secret: str
    created_at: datetime
    is_active: bool = True
    last_used_code: Optional[str] = None

    def __repr__(self) -> str:
        # Exclude secret and last_used_code from repr to prevent accidental
        # logging of sensitive credential material (OWASP A09 – Logging Failures).
        return (
            f"TOTPCredential(user_id={self.user_id!r}, "
            f"created_at={self.created_at!r}, "
            f"is_active={self.is_active!r}, "
            f"secret=<redacted>, last_used_code=<redacted>)"
        )


@dataclass
class BackupCode:
    user_id: str
    code_hash: str
    salt: bytes
    used: bool = False
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AuthResult:
    success: bool
    reason: str = ""
    requires_2fa: bool = False
