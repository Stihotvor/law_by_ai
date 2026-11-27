"""Citation scoring and the "answer or no reliable answer" decision.

Input contract: ``retrieval_score`` and ``rerank_score`` are already in
[0, 1]. The search adapter normalizes raw scores (cosine, logits). A bool,
NaN, infinity, non-number or out-of-range value raises ``ValueError`` naming
the field; nothing is clipped. ``min_confidence`` must be in [0, 1] too.

Scoring rule (deterministic; weights provisional until an evaluation runs):

- no rerank score: ``confidence = retrieval_score``
- both scores: ``confidence = RETRIEVAL_WEIGHT * retrieval_score
  + RERANK_WEIGHT * rerank_score``

Decision: every hit is validated first. Hits whose URL is empty, not
http(s), or holds credentials are dropped. Valid hits are sorted by
confidence, highest first (ties keep input order). Hits with
``confidence >= min_confidence`` form an ``Answer``. If none qualify, the
result is ``NoReliableAnswer`` with the top 3 valid hits as closest sources.
Both results carry ``NOT_LEGAL_ADVICE_NOTICE``. No I/O, no environment read.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit

from core.notices import NOT_LEGAL_ADVICE_NOTICE

RETRIEVAL_WEIGHT: float = 0.4
RERANK_WEIGHT: float = 0.6
CLOSEST_SOURCES_LIMIT: int = 3
ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})


@dataclass(frozen=True)
class ScoredHit:
    """One search hit with scores already normalized to [0, 1]."""

    source_url: str
    quote: str
    retrieval_score: float
    rerank_score: float | None
    law: str | None = None
    article: str | None = None
    paragraph: str | None = None
    document_id: str | None = None


@dataclass(frozen=True)
class Citation:
    """A source shown to the user, with one confidence in [0, 1]."""

    source_url: str
    quote: str
    confidence: float
    law: str | None = None
    article: str | None = None
    paragraph: str | None = None
    document_id: str | None = None


@dataclass(frozen=True)
class Answer:
    """Citations at or above the threshold, best first."""

    citations: tuple[Citation, ...]
    confidence: float
    notice: str


@dataclass(frozen=True)
class NoReliableAnswer:
    """Refusal: no citation reached the threshold."""

    closest_sources: tuple[Citation, ...]
    notice: str


def _check_unit(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{field} must be a number in [0, 1], got {value!r}")
    if math.isnan(value) or math.isinf(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{field} must be in [0, 1], got {value!r}")
    return float(value)


def _confidence(hit: ScoredHit) -> float:
    retrieval = _check_unit(hit.retrieval_score, "retrieval_score")
    if hit.rerank_score is None:
        return retrieval
    rerank = _check_unit(hit.rerank_score, "rerank_score")
    return RETRIEVAL_WEIGHT * retrieval + RERANK_WEIGHT * rerank


def _valid_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:
        return False
    return parts.scheme in ALLOWED_SCHEMES and bool(host) and "@" not in parts.netloc


def _to_citation(hit: ScoredHit, confidence: float) -> Citation:
    return Citation(
        source_url=hit.source_url,
        quote=hit.quote,
        confidence=confidence,
        law=hit.law,
        article=hit.article,
        paragraph=hit.paragraph,
        document_id=hit.document_id,
    )


def decide(hits: Sequence[ScoredHit], min_confidence: float) -> Answer | NoReliableAnswer:
    """Score ``hits`` and return an ``Answer`` or a ``NoReliableAnswer``."""
    threshold = _check_unit(min_confidence, "min_confidence")
    scored = [_to_citation(hit, _confidence(hit)) for hit in hits]
    ranked = sorted(
        (c for c in scored if _valid_url(c.source_url)),
        key=lambda c: c.confidence,
        reverse=True,
    )
    accepted = tuple(c for c in ranked if c.confidence >= threshold)
    if accepted:
        return Answer(accepted, accepted[0].confidence, NOT_LEGAL_ADVICE_NOTICE)
    closest = tuple(ranked[:CLOSEST_SOURCES_LIMIT])
    return NoReliableAnswer(closest, NOT_LEGAL_ADVICE_NOTICE)
