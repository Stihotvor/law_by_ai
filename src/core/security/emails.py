"""Email normalisation shared by login, throttle and the user store."""

from __future__ import annotations

__all__ = ["normalise_email"]


def normalise_email(raw: str) -> str:
    """Return *raw* stripped and lower-cased: the one email form for lookups and keys."""
    return raw.strip().lower()
