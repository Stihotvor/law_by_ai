"""Frozen procedure models (schema version pinned by a unit test)."""

from datetime import date
from typing import Annotated, Literal, cast
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
)
from pydantic_core import PydanticCustomError

SCHEMA_VERSION = 1

KEBAB_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"

KebabStr = Annotated[str, StringConstraints(pattern=KEBAB_PATTERN)]


def _check_not_blank(value: str) -> str:
    if not value.strip():
        raise PydanticCustomError("blank_string", "value must not be blank")
    return value


NonEmptyStr = Annotated[str, AfterValidator(_check_not_blank)]


def _check_source_url(value: str) -> str:
    """Syntax check only: https, a host, no credentials. No network."""
    parts = urlsplit(value)
    if parts.scheme != "https":
        raise PydanticCustomError("url_scheme", "source_url must use https")
    if not parts.hostname:
        raise PydanticCustomError("url_host", "source_url needs a host")
    if "@" in parts.netloc:
        raise PydanticCustomError("url_credentials", "source_url must not hold credentials")
    return value


HttpsUrl = Annotated[str, AfterValidator(_check_source_url)]

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class Step(BaseModel):
    """One curated step. ``last_checked`` must not lie after ``context['today']``."""

    model_config = _FROZEN

    key: KebabStr
    text: NonEmptyStr
    source_url: HttpsUrl
    last_checked: date
    verify_with_office: NonEmptyStr

    @field_validator("last_checked")
    @classmethod
    def _not_in_future(cls, value: date, info: ValidationInfo) -> date:
        context = cast("dict[str, object]", info.context or {})
        today = context.get("today")
        if isinstance(today, date) and value > today:
            raise PydanticCustomError("date_in_future", "last_checked lies in the future")
        return value


class Procedure(BaseModel):
    """A procedure with ordered steps. ``revision`` is set by the repository on read."""

    model_config = _FROZEN

    schema_version: Literal[1]
    slug: KebabStr
    title: NonEmptyStr
    steps: Annotated[tuple[Step, ...], Field(min_length=1)]
    revision: Annotated[int, Field(ge=1)] | None = None

    @field_validator("steps")
    @classmethod
    def _unique_keys(cls, steps: tuple[Step, ...]) -> tuple[Step, ...]:
        seen: set[str] = set()
        for step in steps:
            if step.key in seen:
                raise PydanticCustomError(
                    "duplicate_step_key", "duplicate step key", {"step_key": step.key}
                )
            seen.add(step.key)
        return steps


class ProcedureSummary(BaseModel):
    """Slug and title for listings."""

    model_config = _FROZEN

    slug: str
    title: str


class ImportResult(BaseModel):
    """Outcome of one import: the current revision and whether a new one was written."""

    model_config = _FROZEN

    slug: str
    revision: int
    changed: bool
