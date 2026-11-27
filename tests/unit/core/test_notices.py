"""The shared "not legal advice" notice (ADR-0015)."""

from core.notices import NOT_LEGAL_ADVICE_NOTICE


def test_notice_is_non_empty_string() -> None:
    assert isinstance(NOT_LEGAL_ADVICE_NOTICE, str)
    assert NOT_LEGAL_ADVICE_NOTICE.strip()


def test_notice_says_not_legal_advice() -> None:
    assert "not legal advice" in NOT_LEGAL_ADVICE_NOTICE.lower()
