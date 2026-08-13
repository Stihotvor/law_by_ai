"""Tenant context (ADR-0003, ADR-0004).

Threads ``tenant_id`` through the application via ``contextvars`` so that
every query path — SQL, vector search, graph traversal — can reference the
current tenant without explicitly passing the ID through every call site.

Usage pattern:

    # Somewhere early in the request/handler (Streamlit adapter, middleware):
    from core.security import set_current_tenant
    set_current_tenant("tenant-7")

    # In a plugin method or agent:
    from core.security import get_current_tenant
    tid = get_current_tenant()  # or use ``contextvars`` directly
    # ... construct query with ``tenant_id=tid``

Notes:
- ``contextvars`` are *not* thread-safe across OS threads, but they *are*
  task-safe (green threads, async, Streamlit reruns within the same process).
- For OS-thread parallelism (e.g., Celery workers with prefork), pass
  ``tenant_id`` explicitly or configure per-worker isolation.
- The default (``None``) means "no tenant isolation" — used for shared-document
  operations in MVP scope (issue #9). RLS policies should guard against
  ``None`` being treated as a valid tenant.
"""

import contextlib
import contextvars
import typing

# ---------------------------------------------------------------------------
# Context variable storing the current ``tenant_id``.
# Name chosen to avoid collisions with other libraries.
# ---------------------------------------------------------------------------

_TENANT_ID_VAR: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "core.tenant_id", default=None
)

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def set_current_tenant(tenant_id: str | None) -> None:
    """Set the current ``tenant_id`` in the context variable."""
    _TENANT_ID_VAR.set(tenant_id)


def get_current_tenant() -> str | None:
    """Return the current ``tenant_id``, or ``None`` if not set."""
    return _TENANT_ID_VAR.get()


def reset_current_tenant() -> None:
    """Clear the current ``tenant_id`` (set back to ``None``)."""
    set_current_tenant(None)


# ---------------------------------------------------------------------------
# Context manager helper (automatic cleanup on exit)
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def tenant_context(tenant_id: str | None):
    """``with``-context that sets ``tenant_id`` and restores the previous
    value on exit, even if an exception occurs.

    Example::

        from core.security import tenant_context, get_current_tenant

        with tenant_context("tenant-42"):
            # Inside this block, get_current_tenant() -> "tenant-42"
            ...
        # After the block, tenant_id is restored to whatever it was.
    """
    previous = get_current_tenant()
    set_current_tenant(tenant_id)
    try:
        yield
    finally:
        set_current_tenant(previous)


# ---------------------------------------------------------------------------
# Bulk-iteration safety: temporarily clear tenant when iterating over
# cross-tenant data (e.g., admin reports).
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def without_tenant():
    """Context manager that temporarily clears ``tenant_id``.

    Useful when iterating over shared-document collections where per-row
    tenant scoping is not desired (or must be explicitly re-applied per item).
    """
    previous = get_current_tenant()
    set_current_tenant(None)
    try:
        yield
    finally:
        set_current_tenant(previous)


# ---------------------------------------------------------------------------
# Protocol for external storage of ``tenant_id`` (e.g., Redis, DB).
# The core module only manages the *context variable*; storage-layer
# implementations live in ``src/core/security/token_store.py`` and the
# PostgreSQL plugin.  This function is a hook for middleware that wants to
# persist the current tenant alongside other session data.
# ---------------------------------------------------------------------------


def export_current_tenant() -> dict[str, typing.Any]:
    """Return a serialisable dict of the current tenant state.

    Intended for: saving to Redis session, embedding in JWT claims,
    or writing to request logs.
    """
    return {"tenant_id": get_current_tenant()}
