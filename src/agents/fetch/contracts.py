"""Pydantic contracts for fetching documents."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _require_aware(value: datetime | None) -> datetime | None:
    if value is not None and value.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return value


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class DocumentRef(_Model):
    source: str = Field(min_length=1)
    external_id: str = Field(min_length=1)
    url: str = Field(min_length=1)


class DocumentMeta(_Model):
    ref: DocumentRef
    title: str
    doc_type: str | None = None
    published_at: datetime | None = None
    language: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    @field_validator("published_at")
    @classmethod
    def _aware(cls, value: datetime | None) -> datetime | None:
        return _require_aware(value)


class DocumentFilter(_Model):
    date_from: datetime | None = None
    date_to: datetime | None = None
    doc_type: str | None = None
    keyword: str | None = None
    limit: int = Field(default=50, ge=1, le=500)
    cursor: str | None = None

    @field_validator("date_from", "date_to")
    @classmethod
    def _aware(cls, value: datetime | None) -> datetime | None:
        return _require_aware(value)

    @model_validator(mode="after")
    def _ordered(self) -> "DocumentFilter":
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must be <= date_to")
        return self


class DocumentPage(_Model):
    items: tuple[DocumentRef, ...]
    next_cursor: str | None = None


class FetchedDocument(_Model):
    meta: DocumentMeta
    content: bytes
    content_type: str | None = None
    fetched_at: datetime
    tenant_id: str | None = None

    @field_validator("fetched_at")
    @classmethod
    def _aware(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value
