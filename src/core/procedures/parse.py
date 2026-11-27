"""Parse one procedure YAML text into a checked ``Procedure``. Pure: no I/O, no clock."""

import re
from datetime import date
from typing import Any, cast

import yaml
from pydantic import ValidationError
from pydantic_core import ErrorDetails

from .errors import ProcedureValidationError
from .models import KEBAB_PATTERN, Procedure

DEFAULT_SOURCE = "upload"

_REPOSITORY_FIELDS = ("revision",)


def parse_procedure_yaml(text: str, today: date, *, source: str = DEFAULT_SOURCE) -> Procedure:
    """Return the checked procedure or raise ``ProcedureValidationError`` naming source and step."""
    data = _load_mapping(text, source)
    for name in _REPOSITORY_FIELDS:
        if name in data:
            raise ProcedureValidationError(source, None, f"{name}: set by the repository")
    try:
        return Procedure.model_validate(data, context={"today": today})
    except ValidationError as exc:
        first = exc.errors()[0]
        step_key = _step_key(first, data)
        raise ProcedureValidationError(source, step_key, _reason(first)) from None


def _load_mapping(text: str, source: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        raise ProcedureValidationError(source, None, "malformed YAML") from None
    if not isinstance(data, dict):
        raise ProcedureValidationError(source, None, "top level must be a mapping")
    return cast("dict[str, Any]", data)


def _step_key(error: ErrorDetails, data: dict[str, Any]) -> str | None:
    """Name the failing step by its key, or by index when the key is unusable."""
    ctx = error.get("ctx") or {}
    if "step_key" in ctx:
        return str(ctx["step_key"])
    loc = error["loc"]
    if len(loc) < 2 or loc[0] != "steps" or not isinstance(loc[1], int):
        return None
    index = loc[1]
    step = data["steps"][index]
    key = cast("dict[str, Any]", step).get("key") if isinstance(step, dict) else None
    if isinstance(key, str) and re.fullmatch(KEBAB_PATTERN, key):
        return key
    return f"steps[{index}]"


def _reason(error: ErrorDetails) -> str:
    """Field path and error type only; never the input value."""
    loc = error["loc"]
    field = ".".join(str(part) for part in loc if not isinstance(part, int)) or "procedure"
    return f"{field}: {error['type']}"
