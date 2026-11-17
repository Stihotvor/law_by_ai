"""Map between store dicts and ORM rows."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from data.models import LegalDocument
from plugins.relational_db.tenant_models import Tenant, User


def parse_dt(value: Any, *, default: datetime | None = None) -> datetime:
    if value is None:
        return default or datetime.now(UTC)
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


# Fixed allowlist: payload key -> model attribute. Payload keys are never used
# as attribute names; ``last_updated`` is handled separately via ``parse_dt``.
_EDITABLE: dict[str, str] = {
    "title": "title",
    "content": "content",
    "source": "source",
    "source_url": "source_url",
    "is_processed": "is_processed",
    "metadata": "metadata_",
}


def apply_update(row: LegalDocument, document: dict[str, Any]) -> list[str]:
    """Copy allowlisted ``document`` fields into a loaded row, in the caller's session.

    Returns the sorted names of the dropped keys (``status``, ``tenant_id``,
    unknown keys); ``id`` is ignored and not reported. ``document`` is not changed.
    """
    dropped: list[str] = []
    for key, value in document.items():
        attr = _EDITABLE.get(key)
        if attr is not None:
            setattr(row, attr, value)
        elif key == "last_updated":
            row.last_updated = parse_dt(value)
        elif key != "id":
            dropped.append(key)
    return sorted(dropped)


def doc_to_dict(row: LegalDocument) -> dict[str, Any]:
    return {
        "id": row.id,
        "title": row.title,
        "content": row.content,
        "source": row.source,
        "source_url": row.source_url,
        "last_updated": row.last_updated.isoformat(),
        "metadata": row.metadata_,
        "is_processed": row.is_processed,
        "tenant_id": row.tenant_id,
        "status": row.status,
    }


def user_to_dict(row: User) -> dict[str, Any]:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "email": row.email,
        "role": row.role,
        "name": row.name,
        "is_active": row.is_active,
    }


def login_user_to_dict(row: User) -> dict[str, Any]:
    return {
        **user_to_dict(row),
        "password_hash": row.password_hash,
        "session_version": row.session_version,
    }


def tenant_to_dict(row: Tenant) -> dict[str, Any]:
    return {"id": row.id, "name": row.name}
