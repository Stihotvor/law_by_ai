"""Map between store dicts and ORM rows, and validate document fields."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from data.models import DocumentStatus, LegalDocument
from plugins.relational_db.tenant_models import Tenant, User


def validate_status(value: Any) -> str:
    """Return *value* as a :class:`DocumentStatus` string; ``ValueError`` if unknown."""
    try:
        return DocumentStatus(value).value
    except ValueError:
        allowed = ", ".join(s.value for s in DocumentStatus)
        raise ValueError(f"Unknown document status {value!r}; expected one of: {allowed}") from None


def parse_dt(value: Any, *, default: datetime | None = None) -> datetime:
    if value is None:
        return default or datetime.now(UTC)
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def apply_update(row: LegalDocument, document: dict[str, Any]) -> None:
    """Merge ``document`` fields into a loaded row, in the caller's session."""
    for key, value in document.items():
        if key == "metadata":
            row.metadata_ = value
        elif key == "last_updated":
            row.last_updated = parse_dt(value)
        elif key != "id" and hasattr(row, key):
            setattr(row, key, value)


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
