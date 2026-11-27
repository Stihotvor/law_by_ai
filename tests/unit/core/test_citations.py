"""Citation scoring and the answer-or-refusal decision (ADR-0008, ADR-0015)."""

import ast
import math
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest

import core.citations as citations_module
from core.citations import (
    RERANK_WEIGHT,
    RETRIEVAL_WEIGHT,
    Answer,
    Citation,
    NoReliableAnswer,
    ScoredHit,
    decide,
)
from core.notices import NOT_LEGAL_ADVICE_NOTICE

FORBIDDEN_MODULES = {"sqlalchemy", "httpx", "requests", "redis", "celery", "openai"}


def _hit(
    url: str = "https://zakon.rada.gov.ua/laws/show/1",
    retrieval: float = 0.8,
    rerank: float | None = None,
    quote: str = "quote",
) -> ScoredHit:
    return ScoredHit(
        source_url=url,
        quote=quote,
        retrieval_score=retrieval,
        rerank_score=rerank,
    )


def _answer(result: Answer | NoReliableAnswer) -> Answer:
    assert isinstance(result, Answer)
    return result


def _refusal(result: Answer | NoReliableAnswer) -> NoReliableAnswer:
    assert isinstance(result, NoReliableAnswer)
    return result


HIT_SETS: list[list[ScoredHit]] = [
    [_hit(retrieval=0.9)],
    [_hit(retrieval=0.6, rerank=0.7), _hit("http://example.org/a", 0.5)],
    [_hit(retrieval=1.0, rerank=1.0), _hit(retrieval=0.0, rerank=1.0)],
    [_hit("https://example.org/x?y=1#z", 0.55, 0.9), _hit(retrieval=0.95)],
    [_hit(retrieval=0.7, rerank=0.0), _hit(retrieval=0.6), _hit("ftp://x.org", 0.9)],
]


@pytest.mark.parametrize("hits", HIT_SETS)
def test_valid_citations_have_url_and_confidence_in_range(
    hits: list[ScoredHit],
) -> None:
    answer = _answer(decide(hits, 0.5))
    assert answer.citations
    for citation in answer.citations:
        parts = urlsplit(citation.source_url)
        assert parts.scheme in {"http", "https"}
        assert parts.netloc
        assert 0.0 <= citation.confidence <= 1.0


def test_threshold_boundaries() -> None:
    assert isinstance(decide([_hit(retrieval=0.5)], 0.5), Answer)
    assert isinstance(decide([_hit(retrieval=0.49)], 0.5), NoReliableAnswer)
    assert isinstance(decide([_hit(retrieval=0.4)], 0.3), Answer)


def test_setting_changes_outcome() -> None:
    hits = [_hit(retrieval=0.4)]
    assert isinstance(decide(hits, 0.3), Answer)
    assert isinstance(decide(hits, 0.5), NoReliableAnswer)


def test_min_confidence_bounds_are_accepted() -> None:
    assert isinstance(decide([_hit(retrieval=0.0)], 0.0), Answer)
    assert isinstance(decide([_hit(retrieval=1.0)], 1.0), Answer)


@pytest.mark.parametrize(
    "hits",
    [
        [],
        [_hit(""), _hit("ftp://example.org/a"), _hit("https://u:p@example.org")],
    ],
)
def test_no_citation_gives_empty_closest_sources(hits: list[ScoredHit]) -> None:
    refusal = _refusal(decide(hits, 0.5))
    assert refusal.closest_sources == ()


@pytest.mark.parametrize("threshold", [0.0, 1.0])
def test_url_filter_drops_bad_urls(threshold: float) -> None:
    bad = [
        _hit("", 1.0, quote="empty"),
        _hit("ftp://example.org/a", 1.0, quote="ftp"),
        _hit("mailto:a@example.org", 1.0, quote="mailto"),
        _hit("https:///no-host", 1.0, quote="nohost"),
        _hit("https://user:pw@example.org/a", 1.0, quote="creds"),
        _hit("https://user@example.org/a", 1.0, quote="user"),
        _hit("https://[broken/a", 1.0, quote="unparsable"),
    ]
    good = _hit("https://example.org/ok", 0.9, quote="good")
    result = decide([*bad, good], threshold)
    match result:
        case Answer(citations=found):
            pass
        case NoReliableAnswer(closest_sources=found):
            pass
    assert [c.quote for c in found] == ["good"]


def test_confidence_equals_retrieval_without_rerank() -> None:
    answer = _answer(decide([_hit(retrieval=0.73)], 0.0))
    assert answer.citations[0].confidence == 0.73


def test_confidence_blends_both_scores() -> None:
    answer = _answer(decide([_hit(retrieval=0.5, rerank=0.9)], 0.0))
    assert answer.citations[0].confidence == pytest.approx(0.4 * 0.5 + 0.6 * 0.9)


def test_weights_sum_to_one() -> None:
    assert RETRIEVAL_WEIGHT == 0.4
    assert RERANK_WEIGHT == 0.6
    assert RETRIEVAL_WEIGHT + RERANK_WEIGHT == 1.0


def test_citation_keeps_hit_fields() -> None:
    hit = ScoredHit(
        source_url="https://example.org/law",
        quote="text",
        retrieval_score=0.9,
        rerank_score=None,
        law="Civil Code",
        article="5",
        paragraph="2",
        document_id="doc-1",
    )
    citation = _answer(decide([hit], 0.5)).citations[0]
    assert citation == Citation(
        source_url="https://example.org/law",
        quote="text",
        confidence=0.9,
        law="Civil Code",
        article="5",
        paragraph="2",
        document_id="doc-1",
    )


BAD_SCORES: list[object] = [True, False, math.nan, math.inf, -math.inf, -0.01, 1.01]


@pytest.mark.parametrize("value", BAD_SCORES)
def test_bad_retrieval_score_raises(value: object) -> None:
    hit = _hit(retrieval=value)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="retrieval_score"):
        decide([hit], 0.5)


@pytest.mark.parametrize("value", BAD_SCORES)
def test_bad_rerank_score_raises(value: object) -> None:
    hit = _hit(rerank=value)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="rerank_score"):
        decide([hit], 0.5)


@pytest.mark.parametrize("value", BAD_SCORES)
def test_bad_min_confidence_raises(value: object) -> None:
    with pytest.raises(ValueError, match="min_confidence"):
        decide([_hit()], value)  # type: ignore[arg-type]


def test_non_number_score_raises() -> None:
    hit = _hit(retrieval="0.5")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="retrieval_score"):
        decide([hit], 0.5)


def test_bad_score_on_dropped_hit_still_raises() -> None:
    hit = _hit("ftp://example.org", retrieval=2.0)
    with pytest.raises(ValueError, match="retrieval_score"):
        decide([hit], 0.5)


def test_citations_sorted_descending_and_stable() -> None:
    hits = [
        _hit(retrieval=0.6, quote="a"),
        _hit(retrieval=0.9, quote="b"),
        _hit(retrieval=0.6, quote="c"),
        _hit(retrieval=0.9, quote="d"),
        _hit(retrieval=0.2, quote="low"),
    ]
    answer = _answer(decide(hits, 0.5))
    assert [c.quote for c in answer.citations] == ["b", "d", "a", "c"]
    assert answer.confidence == 0.9


def test_closest_sources_at_most_three_sorted() -> None:
    hits = [
        _hit(retrieval=0.1, quote="a"),
        _hit(retrieval=0.3, quote="b"),
        _hit(retrieval=0.2, quote="c"),
        _hit(retrieval=0.3, quote="d"),
        _hit(retrieval=0.25, quote="e"),
    ]
    refusal = _refusal(decide(hits, 0.5))
    assert [c.quote for c in refusal.closest_sources] == ["b", "d", "e"]


def test_refusal_has_no_citations_or_confidence() -> None:
    refusal = _refusal(decide([], 0.5))
    assert not hasattr(refusal, "citations")
    assert not hasattr(refusal, "confidence")


@pytest.mark.parametrize("hits", [[], [_hit(retrieval=0.1)], [_hit(retrieval=0.9)]])
def test_notice_is_shared(hits: list[ScoredHit]) -> None:
    assert decide(hits, 0.5).notice == NOT_LEGAL_ADVICE_NOTICE


def _imported_modules(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_module_imports_only_stdlib_and_notices() -> None:
    source = Path(citations_module.__file__).read_text(encoding="utf-8")
    imported = _imported_modules(ast.parse(source))
    assert "core.notices" in imported
    for name in imported - {"core.notices"}:
        assert name.split(".")[0] in sys.stdlib_module_names, name
    assert not {n.split(".")[0] for n in imported} & FORBIDDEN_MODULES
