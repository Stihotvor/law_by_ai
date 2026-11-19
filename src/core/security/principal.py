"""Request principal context.

Carries the authenticated actor (email and role) of the current request via
``contextvars``. The auth layer sets it; the store reads it so that audit
fields come from a trusted source instead of a free argument.

Usage pattern:

    from core.security import principal_context, RequestPrincipal

    with principal_context(RequestPrincipal(email="a@x.pl", role="admin")):
        ...  # require_admin_principal() returns the principal here

The principal carries no ``tenant_id``; tenancy lives in ``tenant.py``.
"""

import contextlib
import contextvars
from collections.abc import Generator
from dataclasses import dataclass, replace

from .rbac import ADMIN


@dataclass(frozen=True)
class RequestPrincipal:
    """Authenticated actor of the current request."""

    email: str
    role: str


class PrincipalRequiredError(PermissionError):
    """Raised when an admin principal is required but not available."""


_PRINCIPAL_VAR: contextvars.ContextVar[RequestPrincipal | None] = contextvars.ContextVar(
    "core.request_principal", default=None
)


def set_principal(principal: RequestPrincipal | None) -> None:
    """Set the current request principal."""
    _PRINCIPAL_VAR.set(principal)


def get_principal() -> RequestPrincipal | None:
    """Return the current request principal, or ``None`` if not set."""
    return _PRINCIPAL_VAR.get()


def reset_principal() -> None:
    """Clear the current request principal (set back to ``None``)."""
    set_principal(None)


@contextlib.contextmanager
def principal_context(principal: RequestPrincipal | None) -> Generator[None]:
    """Set ``principal`` for the block and restore the previous value on exit,
    even if an exception occurs."""
    previous = get_principal()
    set_principal(principal)
    try:
        yield
    finally:
        set_principal(previous)


def require_admin_principal() -> RequestPrincipal:
    """Return the current admin principal with its email stripped.

    Raises:
        PrincipalRequiredError: no principal is set, its role is not
            ``ADMIN``, or its email is blank.
    """
    principal = get_principal()
    if principal is None:
        raise PrincipalRequiredError("no request principal is set")
    if principal.role != ADMIN:
        raise PrincipalRequiredError("request principal is not an admin")
    email = principal.email.strip()
    if not email:
        raise PrincipalRequiredError("request principal has a blank email")
    return replace(principal, email=email)
