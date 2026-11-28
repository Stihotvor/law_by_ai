"""Parse one procedure YAML text into a checked ``Procedure``. Pure: no I/O, no clock."""

import re
from datetime import date
from typing import Any, cast

import yaml
from pydantic import ValidationError
from pydantic_core import ErrorDetails

from .errors import ProcedureValidationError, safe_text
from .models import KEBAB_PATTERN, Procedure

DEFAULT_SOURCE = "upload"
MAX_YAML_BYTES = 256 * 1024

_REPOSITORY_FIELDS = ("revision",)
_MERGE_TAG = "tag:yaml.org,2002:merge"


def _compose(text: str) -> yaml.Node | None:
    """Compose *text* into a node tree with ``SafeLoader`` (typed form of ``yaml.compose``)."""
    return yaml.SafeLoader(text).get_single_node()


def _duplicate_key(root: yaml.Node | None) -> str | None:
    """Return the first scalar key found twice in one mapping of the node tree, or ``None``.

    Walks the composed nodes with a stack (no recursion). Merge keys (``<<``) are
    skipped; non-scalar keys are left to ``safe_load``.
    """
    stack: list[yaml.Node] = [root] if root is not None else []
    while stack:
        node = stack.pop()
        if isinstance(node, yaml.SequenceNode):
            stack.extend(cast("list[yaml.Node]", node.value))
        elif isinstance(node, yaml.MappingNode):
            pairs = cast("list[tuple[yaml.Node, yaml.Node]]", node.value)
            found = _duplicate_in(pairs)
            if found is not None:
                return found
            stack.extend(child for pair in pairs for child in pair)
    return None


def _duplicate_in(pairs: list[tuple[yaml.Node, yaml.Node]]) -> str | None:
    """Return the first scalar key of one mapping that appears twice, or ``None``."""
    seen: set[tuple[str, str]] = set()
    for key_node, _ in pairs:
        if not isinstance(key_node, yaml.ScalarNode) or key_node.tag == _MERGE_TAG:
            continue
        key = (key_node.tag, cast("str", key_node.value))
        if key in seen:
            return key[1]
        seen.add(key)
    return None


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
    if len(text.encode("utf-8")) > MAX_YAML_BYTES:
        raise ProcedureValidationError(source, None, f"too large: over {MAX_YAML_BYTES} bytes")
    try:
        duplicate = _duplicate_key(_compose(text))
        data = None if duplicate is not None else yaml.safe_load(text)
    except (yaml.YAMLError, RecursionError):
        raise ProcedureValidationError(source, None, "malformed YAML") from None
    if duplicate is not None:
        raise ProcedureValidationError(source, None, f"duplicate key {safe_text(duplicate)}")
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
    """Field path (repr, truncated) and error type only; never the input value."""
    loc = error["loc"]
    field = ".".join(str(part) for part in loc if not isinstance(part, int)) or "procedure"
    return f"{safe_text(field)}: {error['type']}"
