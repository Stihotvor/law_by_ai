"""Parser and model hardening: size limit, recursion, duplicate keys, safe reasons, URLs."""

from datetime import date
from typing import get_args

import pytest

from core.procedures import (
    SCHEMA_VERSION,
    Procedure,
    ProcedureValidationError,
    parse_procedure_yaml,
)
from core.procedures.models import KEBAB_PATTERN
from core.procedures.parse import MAX_YAML_BYTES
from data.models import _KEBAB  # pyright: ignore[reportPrivateUsage]

TODAY = date(2026, 11, 27)

HEADER = "schema_version: 1\nslug: pesel\ntitle: PESEL number\n"


def _step(url: str = "https://example.gov.pl/form", key: str = "get-form") -> str:
    return (
        f"  - key: {key}\n"
        "    text: Get the form.\n"
        f"    source_url: {url}\n"
        "    last_checked: 2026-11-01\n"
        "    verify_with_office: Ask the office.\n"
    )


def _yaml(step: str | None = None, header: str = HEADER) -> str:
    return header + "steps:\n" + (step if step is not None else _step())


def _raises(text: str, source: str = "pesel.yaml") -> ProcedureValidationError:
    with pytest.raises(ProcedureValidationError) as info:
        parse_procedure_yaml(text, TODAY, source=source)
    return info.value


# --- size limit ---------------------------------------------------------------------


def test_limit_is_256_kib() -> None:
    assert MAX_YAML_BYTES == 256 * 1024


def test_text_over_the_limit_is_rejected_before_parsing() -> None:
    text = _yaml() + "#" * MAX_YAML_BYTES
    error = _raises(text)
    assert "too large" in error.reason


def test_limit_counts_utf8_bytes_not_characters() -> None:
    padding = "#" + "ż" * (MAX_YAML_BYTES // 2)
    text = _yaml() + padding + "\n"
    assert len(text) < MAX_YAML_BYTES
    assert "too large" in _raises(text).reason


def test_text_at_the_limit_is_parsed() -> None:
    base = _yaml()
    text = base + "#" * (MAX_YAML_BYTES - len(base.encode("utf-8")) - 1) + "\n"
    assert len(text.encode("utf-8")) == MAX_YAML_BYTES
    assert parse_procedure_yaml(text, TODAY).slug == "pesel"


# --- recursion ----------------------------------------------------------------------


def test_deep_nesting_is_rejected() -> None:
    depth = 50_000
    text = "title: " + "[" * depth + "]" * depth + "\n"
    error = _raises(text)
    assert error.step_key is None


# --- duplicate keys -----------------------------------------------------------------


def test_duplicate_top_level_key_is_rejected() -> None:
    text = _yaml(header=HEADER + "title: Other title\n")
    error = _raises(text)
    assert "duplicate key" in error.reason
    assert "'title'" in error.reason


def test_duplicate_step_field_is_rejected() -> None:
    step = _step() + "    text: Again.\n"
    assert "duplicate key" in _raises(_yaml(step)).reason


def test_duplicate_key_name_is_truncated() -> None:
    name = "k" * 500
    text = f"{name}: 1\n{name}: 2\n"
    reason = _raises(text).reason
    assert "k" * 81 not in reason
    assert "k" * 80 in reason


def test_safe_semantics_are_kept() -> None:
    with pytest.raises(ProcedureValidationError):
        parse_procedure_yaml("!!python/object/apply:os.system ['true']\n", TODAY)


def test_merge_keys_still_work() -> None:
    text = (
        "base: &base\n  schema_version: 1\n"
        "<<: *base\n"
        "slug: pesel\ntitle: PESEL number\nsteps:\n" + _step()
    )
    error = _raises(text)
    assert "base" in error.reason
    assert "duplicate key" not in error.reason


def test_unhashable_key_is_rejected_as_malformed() -> None:
    assert _raises("? [a, b]\n: 1\n").reason == "malformed YAML"


# --- safe reasons -------------------------------------------------------------------


def test_unknown_key_name_is_repr_and_truncated() -> None:
    name = "x" * 300 + "\x1b[31m"
    text = _yaml(header=HEADER + f'"{name}": 1\n'.replace("\x1b", "\\e"))
    reason = _raises(text).reason
    assert "\x1b" not in reason
    assert "x" * 81 not in reason
    assert reason.startswith("'")


def test_source_is_truncated_and_repr_in_message() -> None:
    source = "s" * 200 + "\n\x1b"
    error = _raises("", source=source)
    assert error.source == "s" * 80
    assert "\n" not in str(error)
    assert "s" * 81 not in str(error)
    assert repr("s" * 80) in str(error)


# --- source_url ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        '"https://example.gov.pl\\\\@evil.example/x"',
        '"https://example.gov.pl/a b"',
        '"https://example.gov.pl/a\\tb"',
        '"https://example.gov.pl/a\\x7fb"',
        '"https://example.gov.pl/\\x01"',
        '"https://exämple.gov.pl/x"',
        '"https://example.gov.pl/' + "a" * 2030 + '"',
    ],
    ids=["backslash", "space", "tab", "del", "control", "non-ascii", "too-long"],
)
def test_bad_url_characters_are_rejected(url: str) -> None:
    error = _raises(_yaml(_step(url=url)))
    assert error.step_key == "get-form"


def test_url_at_2048_chars_is_accepted() -> None:
    prefix = "https://example.gov.pl/"
    url = prefix + "a" * (2048 - len(prefix))
    procedure = parse_procedure_yaml(_yaml(_step(url=url)), TODAY)
    assert procedure.steps[0].source_url == url


# --- pinned constants ---------------------------------------------------------------


def test_schema_version_literal_matches_constant() -> None:
    annotation = Procedure.model_fields["schema_version"].annotation
    assert get_args(annotation) == (SCHEMA_VERSION,)
    assert SCHEMA_VERSION == 1


def test_kebab_pattern_matches_the_database_check() -> None:
    assert f"'{KEBAB_PATTERN}'" == _KEBAB
