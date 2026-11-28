"""Citation scoring and the answer-or-refusal decision (ADR-0008, ADR-0015).

Tests named ``test_qa_NNN_...`` map to the case ids in
docs/design/citations-confidence/qa/results.md. QA-006 and QA-048 live in
tests/unit/test_adr_0008_status.py; QA-045 is the lint, type and coverage run.
"""

import ast
import dataclasses
import math
import sys
from pathlib import Path
from types import ModuleType
from typing import cast
from urllib.parse import urlsplit

import pytest

import core.citations as citations_module
import core.notices as notices_module
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

U1 = "https://eli.gov.pl/akt/1"
U2 = "https://eli.gov.pl/akt/2"
BASE = "https://eli.gov.pl/"
THRESHOLD = 0.5
HIGH = 0.9
LOW = 0.2
CLOSEST_LIMIT = 3
MAX_URL_LENGTH = 1024
ERROR_REPR_LIMIT = 40
LARGE_HIT_COUNT = 10_000
REPEAT_CALLS = 100
FORBIDDEN_MODULES = frozenset(
    {
        "sqlalchemy",
        "httpx",
        "requests",
        "redis",
        "celery",
        "openai",
        "psycopg",
        "urllib3",
        "aiohttp",
        "anthropic",
    }
)
HUGE_INT = 10**400
# Beyond Python's int-to-str digit limit (4300): repr() would raise.
GIANT_INT = 10**5000
BAD_SCORES: list[object] = [
    True,
    False,
    math.nan,
    math.inf,
    -math.inf,
    -0.01,
    1.01,
    2,
    -1,
    pytest.param(HUGE_INT, id="huge_int"),
    pytest.param(-HUGE_INT, id="neg_huge_int"),
    pytest.param(GIANT_INT, id="giant_int"),
    pytest.param(-GIANT_INT, id="neg_giant_int"),
]


def _hit(
    url: str = U1,
    retrieval: float = 0.8,
    rerank: float | None = None,
    quote: str = "q",
    **optional: str,
) -> ScoredHit:
    return ScoredHit(url, quote, retrieval, rerank, **optional)


def _as_score(value: object) -> float:
    """Pass a non-float through the typed API to test runtime validation."""
    return cast("float", value)


def _answer(result: Answer | NoReliableAnswer) -> Answer:
    assert isinstance(result, Answer)
    return result


def _refusal(result: Answer | NoReliableAnswer) -> NoReliableAnswer:
    assert isinstance(result, NoReliableAnswer)
    return result


def _shown(result: Answer | NoReliableAnswer) -> tuple[Citation, ...]:
    if isinstance(result, Answer):
        return result.citations
    return result.closest_sources


def _imported_modules(module: ModuleType) -> set[str]:
    path = Path(cast("str", module.__file__))
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_qa_001_valid_citations_give_answer() -> None:
    answer = _answer(decide([_hit(U1, 0.8), _hit(U2, 0.6)], THRESHOLD))
    assert [c.confidence for c in answer.citations] == [0.8, 0.6]
    assert all(c.source_url.startswith("https://") for c in answer.citations)
    assert answer.confidence == 0.8


def test_qa_002_below_threshold_refusal() -> None:
    refusal = _refusal(decide([_hit(U1, 0.3)], THRESHOLD))
    assert [c.source_url for c in refusal.closest_sources] == [U1]
    assert not hasattr(refusal, "confidence")


def test_qa_003_no_citation_refusal() -> None:
    assert _refusal(decide([_hit("", HIGH)], THRESHOLD)).closest_sources == ()


def test_qa_004_setting_changes_outcome() -> None:
    hits = [_hit(U1, 0.4)]
    assert _answer(decide(hits, 0.3)).confidence == 0.4
    _refusal(decide(hits, THRESHOLD))


def test_qa_005_shared_notice_text() -> None:
    answer = decide([_hit(retrieval=HIGH)], THRESHOLD)
    refusal = decide([_hit(retrieval=0.1)], THRESHOLD)
    assert answer.notice == refusal.notice == NOT_LEGAL_ADVICE_NOTICE
    assert "not legal advice" in NOT_LEGAL_ADVICE_NOTICE.lower()


def test_qa_007_empty_hit_list() -> None:
    assert _refusal(decide([], THRESHOLD)).closest_sources == ()


def test_qa_008_equal_to_threshold() -> None:
    assert _answer(decide([_hit(retrieval=THRESHOLD)], THRESHOLD)).confidence == THRESHOLD


def test_qa_009_just_below_threshold() -> None:
    _refusal(decide([_hit(retrieval=0.49)], THRESHOLD))


def test_qa_010_point4_threshold_point3() -> None:
    assert _answer(decide([_hit(retrieval=0.4)], 0.3)).confidence == 0.4


def test_qa_011_point4_threshold_point5() -> None:
    _refusal(decide([_hit(retrieval=0.4)], THRESHOLD))


def test_qa_012_retrieval_above_one() -> None:
    with pytest.raises(ValueError, match="retrieval_score"):
        decide([_hit(retrieval=1.2)], THRESHOLD)


def test_qa_013_negative_retrieval() -> None:
    with pytest.raises(ValueError, match="retrieval_score"):
        decide([_hit(retrieval=-0.1)], THRESHOLD)


def test_qa_014_rerank_above_one() -> None:
    with pytest.raises(ValueError, match="rerank_score"):
        decide([_hit(retrieval=0.7, rerank=1.5)], THRESHOLD)


def test_qa_015_nan_score() -> None:
    with pytest.raises(ValueError, match="retrieval_score"):
        decide([_hit(retrieval=math.nan)], THRESHOLD)


def test_qa_016_infinite_score() -> None:
    with pytest.raises(ValueError, match="rerank_score"):
        decide([_hit(retrieval=0.7, rerank=math.inf)], THRESHOLD)


def test_qa_017_bool_score() -> None:
    with pytest.raises(ValueError, match="retrieval_score"):
        decide([_hit(retrieval=_as_score(True))], THRESHOLD)


def test_qa_018_text_score() -> None:
    with pytest.raises(ValueError, match="retrieval_score"):
        decide([_hit(retrieval=_as_score("0.9"))], THRESHOLD)


def test_qa_019_threshold_above_one() -> None:
    with pytest.raises(ValueError, match="min_confidence"):
        decide([_hit(retrieval=HIGH)], 1.1)


def test_qa_020_negative_threshold() -> None:
    with pytest.raises(ValueError, match="min_confidence"):
        decide([_hit(retrieval=HIGH)], -0.2)


def test_qa_021_threshold_range_limits() -> None:
    hits = [_hit(retrieval=0.0)]
    assert _answer(decide(hits, 0.0)).confidence == 0.0
    _refusal(decide(hits, 1.0))
    assert _answer(decide([_hit(retrieval=1.0)], 1.0)).confidence == 1.0


def test_qa_022_empty_url_dropped() -> None:
    answer = _answer(decide([_hit("", HIGH), _hit(U2, 0.6)], THRESHOLD))
    assert [c.source_url for c in answer.citations] == [U2]


def test_qa_023_non_http_url_dropped() -> None:
    urls = ["ftp://files.gov.pl/a", "javascript:alert(1)", "file:///etc/passwd"]
    hits = [_hit(url, HIGH) for url in urls]
    assert _refusal(decide(hits, THRESHOLD)).closest_sources == ()


def test_qa_024_url_with_credentials_dropped() -> None:
    refusal = _refusal(decide([_hit("https://admin:secret@eli.gov.pl/akt/1", HIGH)], THRESHOLD))
    assert "secret" not in repr(refusal)


def test_qa_025_plain_http_kept() -> None:
    url = "http://eli.gov.pl/akt/1"
    answer = _answer(decide([_hit(url, 0.8)], THRESHOLD))
    assert [c.source_url for c in answer.citations] == [url]


def test_qa_026_no_rerank_uses_retrieval() -> None:
    assert _answer(decide([_hit(retrieval=0.72)], THRESHOLD)).citations[0].confidence == 0.72


def test_qa_027_both_scores_weighted() -> None:
    citation = _answer(decide([_hit(retrieval=0.5, rerank=HIGH)], THRESHOLD)).citations[0]
    assert citation.confidence == pytest.approx(RETRIEVAL_WEIGHT * 0.5 + RERANK_WEIGHT * HIGH)
    assert citation.confidence == pytest.approx(0.74)


def test_qa_028_weights_sum_to_one() -> None:
    assert RETRIEVAL_WEIGHT == 0.4
    assert RERANK_WEIGHT == 0.6
    assert RETRIEVAL_WEIGHT + RERANK_WEIGHT == 1.0
    citation = _answer(decide([_hit(retrieval=1.0, rerank=1.0)], THRESHOLD)).citations[0]
    assert citation.confidence == 1.0


def test_qa_029_rerank_lowers_high_retrieval() -> None:
    refusal = _refusal(decide([_hit(U1, HIGH, 0.1)], THRESHOLD))
    assert refusal.closest_sources[0].confidence == pytest.approx(0.42)
    assert refusal.closest_sources[0].source_url == U1


def test_qa_030_sorted_by_confidence() -> None:
    hits = [_hit(BASE + "a", 0.6), _hit(BASE + "b", HIGH), _hit(BASE + "c", 0.7)]
    answer = _answer(decide(hits, THRESHOLD))
    assert [c.source_url[-1] for c in answer.citations] == ["b", "c", "a"]
    assert answer.confidence == HIGH


def test_qa_031_tie_keeps_input_order() -> None:
    hits = [_hit(BASE + x, 0.8) for x in "abc"]
    answer = _answer(decide(hits, THRESHOLD))
    assert [c.source_url[-1] for c in answer.citations] == ["a", "b", "c"]


def test_qa_032_answer_drops_below_threshold() -> None:
    answer = _answer(decide([_hit(BASE + "a", HIGH), _hit(BASE + "b", LOW)], THRESHOLD))
    assert [c.source_url for c in answer.citations] == [BASE + "a"]


def test_qa_033_closest_sources_limited_to_three() -> None:
    scores = [0.1, 0.4, 0.3, 0.2, 0.5]
    hits = [_hit(f"{BASE}{i}", s) for i, s in enumerate(scores)]
    refusal = _refusal(decide(hits, HIGH))
    assert len(refusal.closest_sources) == CLOSEST_LIMIT
    assert [c.confidence for c in refusal.closest_sources] == [0.5, 0.4, 0.3]


def test_qa_034_closest_sources_tie_order() -> None:
    hits = [_hit(BASE + x, 0.3) for x in "abcd"]
    refusal = _refusal(decide(hits, HIGH))
    assert [c.source_url[-1] for c in refusal.closest_sources] == ["a", "b", "c"]


def test_qa_035_refusal_has_no_answer_fields() -> None:
    refusal = _refusal(decide([], THRESHOLD))
    assert not hasattr(refusal, "citations")
    assert not hasattr(refusal, "confidence")
    assert {f.name for f in dataclasses.fields(refusal)} == {"closest_sources", "notice"}


def test_qa_036_invalid_hit_after_dropped_hit_checked() -> None:
    with pytest.raises(ValueError, match="retrieval_score"):
        decide([_hit("", 1.7), _hit(BASE + "a", HIGH)], THRESHOLD)


def test_qa_037_invalid_hit_last_checked() -> None:
    with pytest.raises(ValueError, match="retrieval_score"):
        decide([_hit(BASE + "a", HIGH), _hit(BASE + "b", math.nan)], THRESHOLD)


def test_qa_038_repeated_call_same_result() -> None:
    hits = [_hit(BASE + "a", 0.6, 0.8), _hit(BASE + "b", 0.7)]
    first = decide(hits, THRESHOLD)
    assert all(decide(hits, THRESHOLD) == first for _ in range(REPEAT_CALLS))


def test_qa_039_input_list_not_changed() -> None:
    scores = [0.5, HIGH, 0.7]
    hits = [_hit(f"{BASE}{s}", s) for s in scores]
    decide(hits, THRESHOLD)
    assert [x.retrieval_score for x in hits] == scores


def test_qa_040_optional_fields_kept() -> None:
    fields = {
        "law": "Kodeks rodzinny i opiekunczy",
        "article": "135",
        "paragraph": "1",
        "document_id": "doc-1",
    }
    quote = "Zakres obowiazku alimentacyjnego..."
    hit = ScoredHit(U1, quote, 0.8, None, **fields)
    citation = _answer(decide([hit], THRESHOLD)).citations[0]
    assert citation == Citation(source_url=U1, quote=quote, confidence=0.8, **fields)


def test_qa_041_missing_optional_fields() -> None:
    citation = _answer(decide([_hit(U1, 0.8)], THRESHOLD)).citations[0]
    assert (citation.law, citation.article, citation.paragraph, citation.document_id) == (
        None,
        None,
        None,
        None,
    )


def test_qa_042_citation_values_cannot_change() -> None:
    citation = _answer(decide([_hit(retrieval=0.8)], THRESHOLD)).citations[0]
    field_name = "confidence"
    with pytest.raises(dataclasses.FrozenInstanceError, match=field_name):
        setattr(citation, field_name, 0.99)
    assert citation.confidence == 0.8


@pytest.mark.parametrize("module", [citations_module, notices_module])
def test_qa_043_no_io_packages_imported(module: ModuleType) -> None:
    imported = _imported_modules(module)
    assert not {name.split(".")[0] for name in imported} & FORBIDDEN_MODULES
    for name in imported - {"core.notices"}:
        assert name.split(".")[0] in sys.stdlib_module_names, name


def test_qa_044_threshold_not_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MIN_CONFIDENCE", "LBA_MIN_CONFIDENCE", "CITATION_MIN_CONFIDENCE"):
        monkeypatch.setenv(name, "0.1")
    _refusal(decide([_hit(retrieval=0.3)], THRESHOLD))


def test_qa_046_large_hit_list() -> None:
    hits = [_hit(f"{BASE}{i}", i / LARGE_HIT_COUNT) for i in range(LARGE_HIT_COUNT)]
    answer = _answer(decide(hits, THRESHOLD))
    confidences = [c.confidence for c in answer.citations]
    assert len(confidences) == LARGE_HIT_COUNT // 2
    assert confidences == sorted(confidences, reverse=True)


HIT_SETS: list[list[ScoredHit]] = [
    [_hit(U1, HIGH), _hit(U2, 0.95)],
    [_hit(U1, 0.1), _hit(U2, LOW)],
    [_hit("", HIGH), _hit("ftp://x/a", HIGH), _hit("https://u:p@x.org/a", HIGH), _hit(U1, 0.8)],
    [_hit(U1, 0.5, HIGH), _hit(U2, HIGH, 0.1)],
    [_hit("https://example.org/x?y=1#z", 0.55, HIGH), _hit(retrieval=0.95)],
]


@pytest.mark.parametrize("hits", HIT_SETS)
def test_qa_047_hit_sets_pass_validity(hits: list[ScoredHit]) -> None:
    for citation in _shown(decide(hits, THRESHOLD)):
        parts = urlsplit(citation.source_url)
        assert parts.scheme in {"http", "https"}
        assert parts.hostname
        assert 0.0 <= citation.confidence <= 1.0


def test_qa_049_notice_on_refusal_with_source() -> None:
    refusal = _refusal(decide([_hit(U1, LOW)], THRESHOLD))
    assert refusal.notice == NOT_LEGAL_ADVICE_NOTICE
    assert refusal.closest_sources[0].source_url == U1
    assert not hasattr(refusal, "confidence")


BAD_URLS: list[str] = [
    "mailto:a@example.org",
    "https:///no-host",
    "https://user@example.org/a",
    "https://[broken/a",
    "https://example.org/a b",
    "https://example.org/a\tb",
    "https://example.org/a\nb",
    "https://example.org/a\x00b",
    "https://example.org/a\x1fb",
    "https://example.org/a\x7fb",
    "https://example.org\\evil.org/a",
    "https://example.org/a\\b",
    " https://example.org/a",
    "https://example.org/a\u3000b",
    "https://example.org/a\u00a0b",
    "https://example.org/a\u2028b",
    "https://example.org/a\u2029b",
    "https://example.org/a\x85b",
    "https://example.org/a\x9fb",
    "https://example.org:bad/a",
    "https://example.org:65536/a",
    BASE + "a" * (MAX_URL_LENGTH - len(BASE) + 1),
    "http://localhost/a",
    "http://LocalHost./a",
    "http://app.localhost/a",
    "http://intranet/a",
    "http://printer.local/a",
    "http://metadata.google.internal/a",
    "http://127.0.0.1/a",
    "http://127.1.2.3:8080/a",
    "http://10.0.0.5/a",
    "http://172.16.0.1/a",
    "http://192.168.1.1/a",
    "http://169.254.169.254/latest/meta-data",
    "http://100.64.0.1/a",
    "http://0.0.0.0/a",
    "http://[::1]/a",
    "http://[::]/a",
    "http://[fe80::1]/a",
    "http://[fc00::1]/a",
    "http://[fd00:ec2::254]/a",
    "http://[::ffff:127.0.0.1]/a",
    "http://[::ffff:169.254.169.254]/a",
    "http://2130706433/a",
    "http://0x7f.0.0.1/a",
    "http://0177.0.0.1/a",
    "http://127.1/a",
    "http://127.0.0.%31/a",
    "http://%6c%6f%63%61%6c%68%6f%73%74/a",
    "http://home.arpa/a",
    "http://local/a",
    "http://internal/a",
    "http://\uff11\uff12\uff17.0.0.1/a",
    "http://127\u30020\u30020\u30021/a",
]


@pytest.mark.parametrize("url", BAD_URLS)
@pytest.mark.parametrize("threshold", [0.0, 1.0])
def test_url_filter_drops_bad_urls(url: str, threshold: float) -> None:
    result = decide([_hit(url, 1.0, quote="bad"), _hit(BASE + "ok", HIGH, quote="good")], threshold)
    assert [c.quote for c in _shown(result)] == ["good"]


GOOD_URLS: list[str] = [
    "https://example.org/zażółć",
    "https://example.org:8443/a",
    "https://example.org/a",
    "https://8.8.8.8/a",
    "https://[2606:4700:4700::1111]/a",
    "https://sub.eli.gov.pl./a",
    "https://notlocal.example.org/a",
    "https://myhome.arpa.example.org/a",
]


@pytest.mark.parametrize("url", GOOD_URLS)
def test_url_filter_keeps_good_urls(url: str) -> None:
    answer = _answer(decide([_hit(url, HIGH)], THRESHOLD))
    assert [c.source_url for c in answer.citations] == [url]


@pytest.mark.parametrize("value", [0, 1])
def test_integer_unit_bounds_valid(value: int) -> None:
    result = decide([_hit(retrieval=value, rerank=value)], value)
    assert _answer(result).confidence == float(value)


def test_url_at_length_limit_kept() -> None:
    url = BASE + "a" * (MAX_URL_LENGTH - len(BASE))
    assert len(url) == MAX_URL_LENGTH
    answer = _answer(decide([_hit(url, HIGH)], THRESHOLD))
    assert [c.source_url for c in answer.citations] == [url]


@pytest.mark.parametrize("value", BAD_SCORES)
def test_bad_retrieval_score_raises(value: object) -> None:
    hit = _hit(retrieval=_as_score(value))
    with pytest.raises(ValueError, match="retrieval_score"):
        decide([hit], THRESHOLD)


@pytest.mark.parametrize("value", BAD_SCORES)
def test_bad_rerank_score_raises(value: object) -> None:
    hit = _hit(rerank=_as_score(value))
    with pytest.raises(ValueError, match="rerank_score"):
        decide([hit], THRESHOLD)


@pytest.mark.parametrize("value", BAD_SCORES)
def test_bad_min_confidence_raises(value: object) -> None:
    with pytest.raises(ValueError, match="min_confidence"):
        decide([_hit()], _as_score(value))


def test_error_message_truncates_value_repr() -> None:
    value = "x" * (ERROR_REPR_LIMIT * 3)
    with pytest.raises(ValueError, match="retrieval_score") as info:
        decide([_hit(retrieval=_as_score(value))], THRESHOLD)
    message = str(info.value)
    assert message.endswith(repr(value)[:ERROR_REPR_LIMIT])
    assert "x" * ERROR_REPR_LIMIT not in message
