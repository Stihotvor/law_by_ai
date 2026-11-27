"""ProcedureService with an in-memory fake repository (T2). No database."""

from datetime import date

import pytest

from core.procedures import (
    ImportResult,
    Procedure,
    ProcedureRepository,
    ProcedureService,
    ProcedureStoreError,
    ProcedureSummary,
    ProcedureValidationError,
)
from core.security import ADMIN, USER, PrincipalRequiredError, RequestPrincipal, principal_context

TODAY = date(2026, 11, 27)

STEP = """\
  - key: get-form
    text: Get the form.
    source_url: {url}
    last_checked: 2026-11-01
    verify_with_office: Ask the office if the form is current.
"""


def _yaml(slug: str = "pesel", url: str = "https://example.gov.pl/form") -> str:
    return f"schema_version: 1\nslug: {slug}\ntitle: Title of {slug}\nsteps:\n" + STEP.format(
        url=url
    )


class FakeRepository:
    """In-memory port double that records every call."""

    def __init__(self, *, changed: bool = True, error: Exception | None = None) -> None:
        self.changed = changed
        self.error = error
        self.saved: list[tuple[Procedure, str]] = []
        self.get_calls: list[str] = []
        self.items: dict[str, Procedure] = {}

    def save(self, procedure: Procedure, actor: str) -> ImportResult:
        if self.error is not None:
            raise self.error
        self.saved.append((procedure, actor))
        self.items[procedure.slug] = procedure
        return ImportResult(slug=procedure.slug, revision=len(self.saved), changed=self.changed)

    def get(self, slug: str) -> Procedure | None:
        self.get_calls.append(slug)
        return self.items.get(slug)

    def list(self) -> list[ProcedureSummary]:
        return [ProcedureSummary(slug=p.slug, title=p.title) for p in self.items.values()]


def _service(repo: FakeRepository) -> ProcedureService:
    return ProcedureService(repo, today=lambda: TODAY)


def _admin(email: str = "a@x.org") -> RequestPrincipal:
    return RequestPrincipal(email=email, role=ADMIN)


def test_fake_follows_the_port() -> None:
    repo: ProcedureRepository = FakeRepository()
    assert isinstance(repo, FakeRepository)


def test_non_admin_import_is_refused_before_save() -> None:
    repo = FakeRepository()
    user = RequestPrincipal(email="u@x.org", role=USER)
    with principal_context(user), pytest.raises(PrincipalRequiredError):
        _service(repo).import_procedure(_yaml())
    assert repo.saved == []


def test_no_principal_import_is_refused_before_save() -> None:
    repo = FakeRepository()
    with principal_context(None), pytest.raises(PrincipalRequiredError):
        _service(repo).import_procedure(_yaml())
    assert repo.saved == []


def test_admin_import_saves_once_with_actor() -> None:
    repo = FakeRepository()
    with principal_context(_admin(" a@x.org ")):
        result = _service(repo).import_procedure(_yaml())
    assert len(repo.saved) == 1
    procedure, actor = repo.saved[0]
    assert actor == "a@x.org"
    assert procedure.slug == "pesel"
    assert result == ImportResult(slug="pesel", revision=1, changed=True)


def test_identical_content_returns_unchanged() -> None:
    repo = FakeRepository(changed=False)
    with principal_context(_admin()):
        result = _service(repo).import_procedure(_yaml())
    assert result.changed is False


def test_bad_input_writes_nothing() -> None:
    repo = FakeRepository()
    with principal_context(_admin()), pytest.raises(ProcedureValidationError) as info:
        _service(repo).import_procedure(_yaml(url='""'))
    assert info.value.step_key == "get-form"
    assert info.value.source == "upload"
    assert repo.saved == []


def test_import_error_names_the_given_source() -> None:
    repo = FakeRepository()
    with principal_context(_admin()), pytest.raises(ProcedureValidationError) as info:
        _service(repo).import_procedure(_yaml(url='""'), source="pesel.yaml")
    assert info.value.source == "pesel.yaml"
    assert "pesel.yaml" in str(info.value)
    assert repo.saved == []


def test_future_date_uses_injected_clock() -> None:
    repo = FakeRepository()
    service = ProcedureService(repo, today=lambda: date(2026, 10, 1))
    with principal_context(_admin()), pytest.raises(ProcedureValidationError):
        service.import_procedure(_yaml())
    assert repo.saved == []


def test_default_clock_accepts_past_date() -> None:
    repo = FakeRepository()
    with principal_context(_admin()):
        result = ProcedureService(repo).import_procedure(_yaml())
    assert result.slug == "pesel"


def test_unknown_or_malformed_slug_returns_none() -> None:
    repo = FakeRepository()
    service = _service(repo)
    assert service.get_procedure("nope") is None
    assert service.get_procedure("Bad Slug!") is None
    assert repo.get_calls == ["nope"]


def test_known_slug_returns_procedure() -> None:
    repo = FakeRepository()
    service = _service(repo)
    with principal_context(_admin()):
        service.import_procedure(_yaml())
    found = service.get_procedure("pesel")
    assert found is not None
    assert found.slug == "pesel"


def test_list_is_sorted_by_slug() -> None:
    repo = FakeRepository()
    service = _service(repo)
    with principal_context(_admin()):
        service.import_procedure(_yaml("tax-id"))
        service.import_procedure(_yaml("pesel"))
    assert [s.slug for s in service.list_procedures()] == ["pesel", "tax-id"]


def test_list_is_empty_without_procedures() -> None:
    assert _service(FakeRepository()).list_procedures() == []


def test_store_error_propagates_with_cause() -> None:
    lower = OSError("connection lost")
    try:
        raise ProcedureStoreError("procedure store failed") from lower
    except ProcedureStoreError as exc:
        error = exc
    repo = FakeRepository(error=error)
    with principal_context(_admin()), pytest.raises(ProcedureStoreError) as info:
        _service(repo).import_procedure(_yaml())
    assert info.value.__cause__ is lower
