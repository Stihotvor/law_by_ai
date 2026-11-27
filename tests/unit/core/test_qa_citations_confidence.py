"""QA cases for citations-confidence, one test per case id."""

import ast
import dataclasses
import math
import sys
import time
from pathlib import Path

import pytest

import core.citations as citations_module
import core.notices as notices_module
from core.citations import (
    RERANK_WEIGHT,
    RETRIEVAL_WEIGHT,
    Answer,
    NoReliableAnswer,
    ScoredHit,
    decide,
)
from core.notices import NOT_LEGAL_ADVICE_NOTICE

U1 = "https://eli.gov.pl/akt/1"
U2 = "https://eli.gov.pl/akt/2"


def h(url: str = U1, r: object = 0.8, rr: object = None, quote: str = "q", **kw: object) -> ScoredHit:
    return ScoredHit(url, quote, r, rr, **kw)  # type: ignore[arg-type]


def ans(result: object) -> Answer:
    assert isinstance(result, Answer)
    return result


def ref(result: object) -> NoReliableAnswer:
    assert isinstance(result, NoReliableAnswer)
    return result


def test_qa_001_valid_citations_give_answer() -> None:
    a = ans(decide([h(U1, 0.8), h(U2, 0.6)], 0.5))
    assert [c.confidence for c in a.citations] == [0.8, 0.6]
    assert all(c.source_url.startswith("https://") for c in a.citations)
    assert a.confidence == 0.8


def test_qa_002_below_threshold_refusal() -> None:
    r = ref(decide([h(U1, 0.3)], 0.5))
    assert [c.source_url for c in r.closest_sources] == [U1]
    assert not hasattr(r, "confidence")


def test_qa_003_no_citation_refusal() -> None:
    assert ref(decide([h("", 0.9)], 0.5)).closest_sources == ()


def test_qa_004_setting_changes_outcome() -> None:
    hits = [h(U1, 0.4)]
    assert ans(decide(hits, 0.3)).confidence == 0.4
    ref(decide(hits, 0.5))


def test_qa_005_shared_notice_text() -> None:
    a = decide([h(r=0.9)], 0.5)
    r = decide([h(r=0.1)], 0.5)
    assert a.notice == r.notice == NOT_LEGAL_ADVICE_NOTICE
    assert "not legal advice" in NOT_LEGAL_ADVICE_NOTICE.lower()


def test_qa_007_empty_hit_list() -> None:
    assert ref(decide([], 0.5)).closest_sources == ()


def test_qa_008_equal_to_threshold() -> None:
    assert ans(decide([h(r=0.5)], 0.5)).confidence == 0.5


def test_qa_009_just_below_threshold() -> None:
    ref(decide([h(r=0.49)], 0.5))


def test_qa_010_point4_threshold_point3() -> None:
    assert ans(decide([h(r=0.4)], 0.3)).confidence == 0.4


def test_qa_011_point4_threshold_point5() -> None:
    ref(decide([h(r=0.4)], 0.5))


def test_qa_012_retrieval_above_one() -> None:
    with pytest.raises(ValueError, match="retrieval_score"):
        decide([h(r=1.2)], 0.5)


def test_qa_013_negative_retrieval() -> None:
    with pytest.raises(ValueError, match="retrieval_score"):
        decide([h(r=-0.1)], 0.5)


def test_qa_014_rerank_above_one() -> None:
    with pytest.raises(ValueError, match="rerank_score"):
        decide([h(r=0.7, rr=1.5)], 0.5)


def test_qa_015_nan_score() -> None:
    with pytest.raises(ValueError, match="retrieval_score"):
        decide([h(r=math.nan)], 0.5)


def test_qa_016_infinite_score() -> None:
    with pytest.raises(ValueError, match="rerank_score"):
        decide([h(r=0.7, rr=math.inf)], 0.5)


def test_qa_017_bool_score() -> None:
    with pytest.raises(ValueError, match="retrieval_score"):
        decide([h(r=True)], 0.5)


def test_qa_018_text_score() -> None:
    with pytest.raises(ValueError, match="retrieval_score"):
        decide([h(r="0.9")], 0.5)


def test_qa_019_threshold_above_one() -> None:
    with pytest.raises(ValueError, match="min_confidence"):
        decide([h(r=0.9)], 1.1)


def test_qa_020_negative_threshold() -> None:
    with pytest.raises(ValueError, match="min_confidence"):
        decide([h(r=0.9)], -0.2)


def test_qa_021_threshold_range_limits() -> None:
    hits = [h(r=0.0)]
    assert ans(decide(hits, 0.0)).confidence == 0.0
    ref(decide(hits, 1.0))


def test_qa_022_empty_url_dropped() -> None:
    a = ans(decide([h("", 0.9), h(U2, 0.6)], 0.5))
    assert [c.source_url for c in a.citations] == [U2]


def test_qa_023_non_http_url_dropped() -> None:
    hits = [h("ftp://files.gov.pl/a", 0.9), h("javascript:alert(1)", 0.9), h("file:///etc/passwd", 0.9)]
    assert ref(decide(hits, 0.5)).closest_sources == ()


def test_qa_024_url_with_credentials_dropped() -> None:
    r = ref(decide([h("https://admin:secret@eli.gov.pl/akt/1", 0.9)], 0.5))
    assert "secret" not in repr(r)


def test_qa_025_plain_http_kept() -> None:
    a = ans(decide([h("http://eli.gov.pl/akt/1", 0.8)], 0.5))
    assert [c.source_url for c in a.citations] == ["http://eli.gov.pl/akt/1"]


def test_qa_026_no_rerank_uses_retrieval() -> None:
    assert ans(decide([h(r=0.72)], 0.5)).citations[0].confidence == 0.72


def test_qa_027_both_scores_weighted() -> None:
    c = ans(decide([h(r=0.5, rr=0.9)], 0.5)).citations[0]
    assert c.confidence == pytest.approx(0.74)


def test_qa_028_weights_sum_to_one() -> None:
    assert RETRIEVAL_WEIGHT + RERANK_WEIGHT == 1.0
    assert ans(decide([h(r=1.0, rr=1.0)], 0.5)).citations[0].confidence == 1.0


def test_qa_029_rerank_lowers_high_retrieval() -> None:
    r = ref(decide([h(U1, 0.9, 0.1)], 0.5))
    assert r.closest_sources[0].confidence == pytest.approx(0.42)
    assert r.closest_sources[0].source_url == U1


def test_qa_030_sorted_by_confidence() -> None:
    hits = [h("https://eli.gov.pl/a", 0.6), h("https://eli.gov.pl/b", 0.9), h("https://eli.gov.pl/c", 0.7)]
    a = ans(decide(hits, 0.5))
    assert [c.source_url[-1] for c in a.citations] == ["b", "c", "a"]
    assert a.confidence == 0.9


def test_qa_031_tie_keeps_input_order() -> None:
    hits = [h(f"https://eli.gov.pl/{x}", 0.8) for x in "abc"]
    assert [c.source_url[-1] for c in ans(decide(hits, 0.5)).citations] == ["a", "b", "c"]


def test_qa_032_answer_drops_below_threshold() -> None:
    a = ans(decide([h("https://eli.gov.pl/a", 0.9), h("https://eli.gov.pl/b", 0.2)], 0.5))
    assert [c.source_url for c in a.citations] == ["https://eli.gov.pl/a"]


def test_qa_033_closest_sources_limited_to_three() -> None:
    hits = [h(f"https://eli.gov.pl/{i}", s) for i, s in enumerate([0.1, 0.4, 0.3, 0.2, 0.5])]
    r = ref(decide(hits, 0.9))
    assert [c.confidence for c in r.closest_sources] == [0.5, 0.4, 0.3]


def test_qa_034_closest_sources_tie_order() -> None:
    hits = [h(f"https://eli.gov.pl/{x}", 0.3) for x in "abcd"]
    r = ref(decide(hits, 0.9))
    assert [c.source_url[-1] for c in r.closest_sources] == ["a", "b", "c"]


def test_qa_035_refusal_has_no_answer_fields() -> None:
    r = ref(decide([], 0.5))
    with pytest.raises(AttributeError):
        _ = r.citations  # type: ignore[attr-defined]
    with pytest.raises(AttributeError):
        _ = r.confidence  # type: ignore[attr-defined]
    assert {f.name for f in dataclasses.fields(r)} == {"closest_sources", "notice"}


def test_qa_036_invalid_hit_after_dropped_hit_checked() -> None:
    with pytest.raises(ValueError, match="retrieval_score"):
        decide([h("", 1.7), h("https://eli.gov.pl/a", 0.9)], 0.5)


def test_qa_037_invalid_hit_last_checked() -> None:
    with pytest.raises(ValueError):
        decide([h("https://eli.gov.pl/a", 0.9), h("https://eli.gov.pl/b", math.nan)], 0.5)


def test_qa_038_repeated_call_same_result() -> None:
    hits = [h("https://eli.gov.pl/a", 0.6, 0.8), h("https://eli.gov.pl/b", 0.7)]
    first = decide(hits, 0.5)
    assert all(decide(hits, 0.5) == first for _ in range(100))


def test_qa_039_input_list_not_changed() -> None:
    hits = [h(f"https://eli.gov.pl/{s}", s) for s in (0.5, 0.9, 0.7)]
    decide(hits, 0.5)
    assert [x.retrieval_score for x in hits] == [0.5, 0.9, 0.7]


def test_qa_040_optional_fields_kept() -> None:
    hit = h(U1, 0.8, quote="Zakres obowiazku alimentacyjnego...", law="Kodeks rodzinny i opiekunczy", article="135", paragraph="1")
    c = ans(decide([hit], 0.5)).citations[0]
    assert (c.law, c.article, c.paragraph, c.quote, c.source_url) == (
        "Kodeks rodzinny i opiekunczy", "135", "1", "Zakres obowiazku alimentacyjnego...", U1,
    )


def test_qa_041_missing_optional_fields() -> None:
    c = ans(decide([h(U1, 0.8)], 0.5)).citations[0]
    assert (c.law, c.article, c.paragraph) == (None, None, None)


def test_qa_042_citation_values_cannot_change() -> None:
    c = ans(decide([h(r=0.8)], 0.5)).citations[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        c.confidence = 0.99  # type: ignore[misc]
    assert c.confidence == 0.8


def test_qa_043_no_io_packages_imported() -> None:
    forbidden = {"sqlalchemy", "httpx", "requests", "redis", "celery", "openai", "psycopg", "urllib3", "aiohttp", "anthropic"}
    for module in (citations_module, notices_module):
        tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
        tops = {n.split(".")[0] for n in names}
        assert not tops & forbidden
        assert all(n == "core.notices" or n.split(".")[0] in sys.stdlib_module_names for n in names)


def test_qa_044_threshold_not_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("MIN_CONFIDENCE", "LBA_MIN_CONFIDENCE", "CITATION_MIN_CONFIDENCE"):
        monkeypatch.setenv(name, "0.1")
    ref(decide([h(r=0.3)], 0.5))


def test_qa_046_large_hit_list() -> None:
    hits = [h(f"https://eli.gov.pl/{i}", (i % 10000) / 10000 + 0.00001 * 0) for i in range(10000)]
    start = time.perf_counter()
    a = ans(decide(hits, 0.5))
    assert time.perf_counter() - start < 1.0
    confs = [c.confidence for c in a.citations]
    assert confs == sorted(confs, reverse=True)


def test_qa_047_hit_sets_pass_validity() -> None:
    sets = [
        [h(U1, 0.9), h(U2, 0.95)],
        [h(U1, 0.1), h(U2, 0.2)],
        [h("", 0.9), h("ftp://x/a", 0.9), h("https://u:p@x.org/a", 0.9), h(U1, 0.8)],
        [h(U1, 0.5, 0.9), h(U2, 0.9, 0.1)],
    ]
    for hs in sets:
        r = decide(hs, 0.5)
        cits = r.citations if isinstance(r, Answer) else r.closest_sources
        for c in cits:
            assert c.source_url.startswith(("http://", "https://"))
            assert 0.0 <= c.confidence <= 1.0


def test_qa_049_notice_on_refusal_with_source() -> None:
    r = ref(decide([h(U1, 0.2)], 0.5))
    assert r.notice == NOT_LEGAL_ADVICE_NOTICE
    assert r.closest_sources[0].source_url == U1
    assert not hasattr(r, "confidence")
