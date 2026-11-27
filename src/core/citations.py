"""Citation scoring and the "answer or no reliable answer" decision.

Input contract: ``retrieval_score`` and ``rerank_score`` are already in
[0, 1]. The search adapter normalizes raw scores (cosine, logits). A bool,
NaN, infinity, non-number or out-of-range value (including a huge int)
raises ``ValueError`` naming the field; nothing is clipped. Integers 0 and 1
are valid. ``min_confidence`` must be in [0, 1] too.

Scoring rule (deterministic; weights provisional until an evaluation runs):

- no rerank score: ``confidence = retrieval_score``
- both scores: ``confidence = RETRIEVAL_WEIGHT * retrieval_score
  + RERANK_WEIGHT * rerank_score``

Decision: every hit is validated first. Hits whose URL is empty, not
http(s), holds credentials, a bad port (not a number or above 65535), any
Unicode whitespace or control/format character (categories C* and Z*) or a
backslash, or is longer than ``MAX_URL_LENGTH`` (the ``source_url`` column)
are dropped. Other non-ASCII text (e.g. Polish letters) is kept.
Valid hits are sorted by confidence, highest first (ties keep input order). Hits with
``confidence >= min_confidence`` form an ``Answer``. If none qualify, the
result is ``NoReliableAnswer`` with the top 3 valid hits as closest sources.
Both results carry ``NOT_LEGAL_ADVICE_NOTICE``. No I/O, no environment read.

This layer does not make a URL safe to fetch; the renderer must escape the
``quote`` and ``law`` fields.
"""

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from urllib.parse import urlsplit

from core.notices import NOT_LEGAL_ADVICE_NOTICE

RETRIEVAL_WEIGHT: float = 0.4
RERANK_WEIGHT: float = 0.6
CLOSEST_SOURCES_LIMIT: int = 3
ALLOWED_SCHEMES: frozenset[str] = frozenset({"http", "https"})
MAX_URL_LENGTH: int = 1024
ERROR_REPR_LIMIT: int = 40
# Ints wider than this are described, not printed (repr may raise past 4300 digits).
ERROR_REPR_MAX_BITS: int = 128


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


def _shown(value: object) -> str:
    """Short text for an error message; never turns a huge int into digits."""
    if isinstance(value, int) and value.bit_length() > ERROR_REPR_MAX_BITS:
        return f"int with {value.bit_length()} bits"
    return repr(value)[:ERROR_REPR_LIMIT]


def _check_unit(value: object, field: str) -> float:
    shown = _shown(value)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{field} must be a number in [0, 1], got {shown}")
    # Exact comparison: false for NaN, rejects infinities and huge ints alike.
    if not 0 <= value <= 1:
        raise ValueError(f"{field} must be in [0, 1], got {shown}")
    return float(value)


def _confidence(hit: ScoredHit) -> float:
    retrieval = _check_unit(hit.retrieval_score, "retrieval_score")
    if hit.rerank_score is None:
        return retrieval
    rerank = _check_unit(hit.rerank_score, "rerank_score")
    return RETRIEVAL_WEIGHT * retrieval + RERANK_WEIGHT * rerank


def _has_bad_char(url: str) -> bool:
    # Categories C* (control, format, ...) and Z* (all Unicode whitespace).
    return any(ch == "\\" or unicodedata.category(ch)[0] in "CZ" for ch in url)


def _valid_url(url: str) -> bool:
    if len(url) > MAX_URL_LENGTH or _has_bad_char(url):
        return False
    try:
        parts = urlsplit(url)
        host = parts.hostname
        _ = parts.port
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
