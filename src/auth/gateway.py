import functools
from dataclasses import dataclass, field
from typing import Callable, List


class TwoFactorRequiredError(Exception):
    """Raised when an admin endpoint is accessed without a verified second factor."""

    http_status: int = 401

    def __init__(self, message: str = "Two-factor authentication required") -> None:
        super().__init__(message)
        self.http_status = 401


@dataclass
class RequestContext:
    user_id: str
    roles: List[str] = field(default_factory=list)
    totp_verified: bool = False
    backup_verified: bool = False


def require_admin_2fa(func: Callable) -> Callable:
    """
    Decorator that enforces two-factor authentication for admin users.

    The decorated function must accept a `context` keyword argument of type
    RequestContext as its first or only argument. If the user has the "admin"
    role but has neither totp_verified nor backup_verified, a
    TwoFactorRequiredError is raised before the wrapped function executes.
    """

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Locate the RequestContext — check kwargs first, then positional args
        context: RequestContext = kwargs.get("context")
        if context is None:
            for arg in args:
                if isinstance(arg, RequestContext):
                    context = arg
                    break

        if context is None:
            raise ValueError("require_admin_2fa: no RequestContext found in arguments")

        if "admin" in context.roles:
            if not (context.totp_verified or context.backup_verified):
                raise TwoFactorRequiredError()

        return func(*args, **kwargs)

    return wrapper
