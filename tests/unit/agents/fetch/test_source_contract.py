"""Every registered source and every test fake honours the source contract."""

from __future__ import annotations

from dataclasses import replace

import pytest
from contracts.fetch_source import SourceCase, check_legal_source, check_ref_builder
from fakes.fetch import (
    FAKE_BASE,
    FAKE_SOURCE,
    STATIC_REF,
    FakeSource,
    FakeStrategy,
    StaticFakeSource,
    StaticFakeStrategy,
)

from agents.fetch.contracts import DocumentRef
from agents.fetch.sources import SOURCES
from agents.fetch.sources.sejm_eli import SejmEliSource
from agents.fetch.strategies.rest_api import RestApiStrategy

_FAKE_ID = "0123456789abcdef" * 2 + ".txt"

SEJM_CASE = SourceCase(
    source_cls=SejmEliSource,
    strategy_cls=RestApiStrategy,
    valid_id="DU/2020/1",
    expected_url="https://api.sejm.gov.pl/eli/acts/DU/2020/1/text.html",
    too_long_id="DU/2020/" + "1" * 7,
)
FAKE_CASE = SourceCase(
    source_cls=FakeSource,
    strategy_cls=FakeStrategy,
    valid_id=_FAKE_ID,
    expected_url=f"{FAKE_BASE}/{_FAKE_ID}",
    too_long_id="0" + _FAKE_ID,
    fetch_ref=DocumentRef(source=FAKE_SOURCE, external_id=_FAKE_ID, url=f"{FAKE_BASE}/{_FAKE_ID}"),
)
# Its strategy is not a RefBuilder, so only the LegalSource contract applies.
FETCHER_FAKE_CASE = SourceCase(
    source_cls=StaticFakeSource,
    strategy_cls=StaticFakeStrategy,
    fetch_ref=STATIC_REF,
)

REGISTERED_CASES = {"sejm_eli": SEJM_CASE}
ALL_CASES = {**REGISTERED_CASES, "fake": FAKE_CASE, "fetcher_fake": FETCHER_FAKE_CASE}
SOURCE_CASES = [pytest.param(case, id=key) for key, case in ALL_CASES.items()]
REF_BUILDER_CASES = [
    pytest.param(case, id=key)
    for key, case in ALL_CASES.items()
    if hasattr(case.strategy_cls, "make_ref")
]


class PermissiveStrategy(FakeStrategy):
    """The postmortem bug: a ref builder that accepts any id."""

    def make_ref(self, source: str, external_id: str) -> DocumentRef:
        if source != FAKE_SOURCE:
            return super().make_ref(source, external_id)
        return DocumentRef(source=source, external_id=external_id, url=f"{FAKE_BASE}/{external_id}")


def test_every_registered_source_has_a_case() -> None:
    assert set(REGISTERED_CASES) == set(SOURCES.names())


def test_every_registered_source_runs_the_ref_builder_contract() -> None:
    assert set(REGISTERED_CASES) <= {p.id for p in REF_BUILDER_CASES}


@pytest.mark.parametrize("field", ["valid_id", "expected_url", "too_long_id"])
def test_ref_builder_contract_rejects_an_incomplete_case(field: str) -> None:
    incomplete = replace(FAKE_CASE, **{field: ""})

    with pytest.raises(ValueError, match=field):
        check_ref_builder(incomplete)


@pytest.mark.parametrize("case", REF_BUILDER_CASES)
def test_ref_builder_contract(case: SourceCase) -> None:
    check_ref_builder(case)


@pytest.mark.parametrize("case", SOURCE_CASES)
def test_legal_source_contract(case: SourceCase) -> None:
    check_legal_source(case)


def test_contract_fails_for_a_ref_builder_that_accepts_any_id() -> None:
    permissive = replace(FAKE_CASE, strategy_cls=PermissiveStrategy)

    # Only the invalid-id check can fail: unknown sources still raise.
    with pytest.raises(pytest.fail.Exception, match=r"DID NOT RAISE.*InvalidReferenceError"):
        check_ref_builder(permissive)
