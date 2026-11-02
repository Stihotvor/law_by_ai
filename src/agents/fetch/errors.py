"""Errors raised by the fetch package."""


class FetchError(Exception):
    """Base class for fetch errors."""


class DocumentRejectedError(FetchError):
    """Re-fetch blocked by the rejection checker."""


class SourceConfigError(FetchError):
    """Source declares an unknown strategy_name."""
