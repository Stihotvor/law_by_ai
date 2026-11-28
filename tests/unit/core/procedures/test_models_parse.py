"""Procedure models, errors and the YAML parser (T1). Pure, no network."""

from datetime import date

import pytest
from pydantic import ValidationError

from core.procedures import (
    SCHEMA_VERSION,
    ImportResult,
    Procedure,
    ProcedureStoreError,
    ProcedureSummary,
    ProcedureValidationError,
    Step,
    parse_procedure_yaml,
)

TODAY = date(2026, 11, 27)

STEP_A = """\
  - key: get-form
    text: Get the form.
    source_url: https://example.gov.pl/form
    last_checked: 2026-11-01
    verify_with_office: Ask the office if the form is current.
"""
STEP_B = """\
  - key: fill-form
    text: Fill in the form.
    source_url: https://example.gov.pl/fill
    last_checked: 2026-10-01
    verify_with_office: Ask the office which fields are required.
"""
STEP_C = """\
  - key: submit-form
    text: Submit the form.
    source_url: https://example.gov.pl/submit
    last_checked: 2026-09-01
    verify_with_office: Ask the office for the opening hours.
"""
HEADER = """\
schema_version: 1
slug: pesel
title: PESEL number
"""


def _yaml(*steps: str, header: str = HEADER) -> str:
    return header + "steps:\n" + "".join(steps)


def _bad_step(**fields: str | None) -> str:
    base: dict[str, str | None] = {
        "key": "bad-step",
        "text": "Do it.",
        "source_url": "https://example.gov.pl/x",
        "last_checked": "2026-11-01",
        "verify_with_office": "Ask the office.",
    }
    base.update(fields)
    lines = [f"{k}: {v!r}" if v is not None else "" for k, v in base.items()]
    present = [line for line in lines if line]
    return "  - " + "\n    ".join(present) + "\n"


def _raises(text: str, source: str = "pesel.yaml") -> ProcedureValidationError:
    with pytest.raises(ProcedureValidationError) as info:
        parse_procedure_yaml(text, TODAY, source=source)
    return info.value


# Scenario: valid procedure parses


def test_valid_procedure_parses_in_position_order() -> None:
    procedure = parse_procedure_yaml(_yaml(STEP_A, STEP_B, STEP_C), TODAY)

    assert isinstance(procedure, Procedure)
    assert [s.key for s in procedure.steps] == ["get-form", "fill-form", "submit-form"]
    assert procedure.slug == "pesel"
    assert procedure.schema_version == SCHEMA_VERSION
    assert procedure.revision is None
    assert procedure.steps[0].last_checked == date(2026, 11, 1)


def test_last_checked_today_is_accepted() -> None:
    step = _bad_step(last_checked=TODAY.isoformat())
    procedure = parse_procedure_yaml(_yaml(step), TODAY)
    assert procedure.steps[0].last_checked == TODAY


def test_models_are_frozen() -> None:
    procedure = parse_procedure_yaml(_yaml(STEP_A), TODAY)
    with pytest.raises(ValidationError):
        procedure.title = "changed"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        procedure.steps[0].text = "changed"  # type: ignore[misc]


def test_revision_can_be_set_by_repository() -> None:
    procedure = parse_procedure_yaml(_yaml(STEP_A), TODAY)
    stored = procedure.model_copy(update={"revision": 3})
    assert stored.revision == 3


def test_summary_and_import_result() -> None:
    assert ProcedureSummary(slug="pesel", title="PESEL").slug == "pesel"
    result = ImportResult(slug="pesel", revision=1, changed=True)
    assert result.changed is True


# Scenario: incomplete step is rejected


@pytest.mark.parametrize(
    "fields",
    [
        {"source_url": ""},
        {"last_checked": None},
        {"verify_with_office": None},
        {"verify_with_office": "   "},
        {"text": ""},
    ],
)
def test_incomplete_step_names_the_step(fields: dict[str, str | None]) -> None:
    error = _raises(_yaml(STEP_A, _bad_step(**fields)))
    assert error.step_key == "bad-step"
    assert error.source == "pesel.yaml"


def test_step_with_invalid_key_is_named_by_index() -> None:
    error = _raises(_yaml(STEP_A, _bad_step(key="Bad Key")))
    assert error.step_key == "steps[1]"


def test_step_that_is_not_a_mapping_is_named_by_index() -> None:
    error = _raises(_yaml(STEP_A, "  - just text\n"))
    assert error.step_key == "steps[1]"


# Scenario: future or invalid date is rejected


@pytest.mark.parametrize("value", ["2026-11-28", "not-a-date"])
def test_future_or_invalid_date_is_rejected(value: str) -> None:
    error = _raises(_yaml(_bad_step(last_checked=value)))
    assert error.step_key == "bad-step"


def test_future_check_uses_today_from_context() -> None:
    data = {
        "key": "a",
        "text": "t",
        "source_url": "https://example.gov.pl",
        "last_checked": "2026-12-01",
        "verify_with_office": "v",
    }
    with pytest.raises(ValidationError):
        Step.model_validate(data, context={"today": TODAY})
    # Without a clock (repository read of stored data) no future check runs.
    assert Step.model_validate(data).last_checked == date(2026, 12, 1)


# Scenario: bad URL is rejected


@pytest.mark.parametrize(
    "url",
    [
        "http://example.gov.pl/x",
        "https://user:pw@example.gov.pl/x",
        "https://user@example.gov.pl/x",
        "https:///no-host",
        "ftp://example.gov.pl/x",
    ],
)
def test_bad_url_is_rejected(url: str) -> None:
    error = _raises(_yaml(_bad_step(source_url=url)))
    assert error.step_key == "bad-step"


# Scenario: structure errors are rejected


@pytest.mark.parametrize(
    "text",
    [
        HEADER + "steps: []\n",
        _yaml(STEP_A, header=HEADER + "colour: red\n"),
        _yaml(STEP_A, header=HEADER + "revision: 2\n"),
        _yaml(STEP_A, STEP_A),
        "slug: [unclosed\n",
        "- a list\n",
        "",
        _yaml(STEP_A, header=HEADER.replace("schema_version: 1", "schema_version: 2")),
        _yaml(STEP_A, header=HEADER.replace("pesel", "Bad Slug")),
    ],
    ids=[
        "zero-steps",
        "unknown-key",
        "revision-in-yaml",
        "duplicate-keys",
        "malformed",
        "not-a-mapping",
        "empty",
        "other-schema-version",
        "bad-slug",
    ],
)
def test_structure_errors_set_source(text: str) -> None:
    error = _raises(text, source="upload:pesel.yaml")
    assert error.source == "upload:pesel.yaml"


def test_duplicate_keys_name_the_step() -> None:
    error = _raises(_yaml(STEP_A, STEP_B, STEP_A))
    assert error.step_key == "get-form"


def test_unknown_step_field_names_the_step() -> None:
    step = STEP_A + "    colour: red\n"
    error = _raises(_yaml(step))
    assert error.step_key == "get-form"


def test_default_source_is_upload() -> None:
    with pytest.raises(ProcedureValidationError) as info:
        parse_procedure_yaml("", TODAY)
    assert info.value.source == "upload"


def test_error_message_holds_no_content() -> None:
    secret = "https://secret-user:secret-pw@example.gov.pl/x"  # noqa: S105 - test data
    error = _raises(_yaml(_bad_step(source_url=secret, text="private words")))
    assert "secret" not in str(error)
    assert "private words" not in str(error)
    assert "pesel.yaml" in str(error)
    assert "bad-step" in str(error)


def test_store_error_is_an_exception() -> None:
    assert issubclass(ProcedureStoreError, Exception)
    assert not issubclass(ProcedureStoreError, ProcedureValidationError)


# QA gap tests


def test_qa_018_blank_title_is_rejected() -> None:
    _raises(_yaml(STEP_A, header=HEADER.replace("title: PESEL number", "title: '  '")))


def test_qa_071_missing_schema_version_is_rejected() -> None:
    _raises(_yaml(STEP_A, header=HEADER.replace("schema_version: 1\n", "")))


def test_qa_072_schema_version_99_is_rejected() -> None:
    _raises(_yaml(STEP_A, header=HEADER.replace("schema_version: 1", "schema_version: 99")))


def test_qa_028_key_order_and_comments_do_not_change_content() -> None:
    plain = parse_procedure_yaml(_yaml(STEP_A), TODAY)
    reordered = (
        "# a comment\n"
        "title: PESEL number\n"
        "steps:\n"
        "  # step comment\n"
        "  - verify_with_office: Ask the office if the form is current.\n"
        "    last_checked: 2026-11-01\n"
        "    source_url: https://example.gov.pl/form\n"
        "    text: Get the form.\n"
        "    key: get-form\n"
        "slug: pesel\n"
        "schema_version: 1\n"
    )
    assert parse_procedure_yaml(reordered, TODAY) == plain


def test_qa_068_stale_date_is_kept_unchanged() -> None:
    step = _bad_step(last_checked="2020-01-01")
    procedure = parse_procedure_yaml(_yaml(step), TODAY)
    assert procedure.steps[0].last_checked == date(2020, 1, 1)


def test_qa_088_two_hundred_steps_parse_in_order() -> None:
    steps = [_bad_step(key=f"step-{i}") for i in range(200)]
    procedure = parse_procedure_yaml(_yaml(*steps), TODAY)
    assert [s.key for s in procedure.steps] == [f"step-{i}" for i in range(200)]


# Scenario: schema is pinned


def test_step_schema_is_pinned() -> None:
    assert list(Step.model_fields) == [
        "key",
        "text",
        "source_url",
        "last_checked",
        "verify_with_office",
    ]
    assert SCHEMA_VERSION == 1
    assert Procedure.model_fields["schema_version"].annotation is not None
