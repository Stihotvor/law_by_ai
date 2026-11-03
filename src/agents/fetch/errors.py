"""Errors raised by the fetch package."""


class FetchError(Exception):
    """Base class for fetch errors."""


class DocumentRejectedError(FetchError):
    """Re-fetch blocked by the rejection checker."""


class SourceConfigError(FetchError):
    """Source declares an unknown strategy_name."""


class UnknownSourceError(FetchError):
    """No source is registered under the requested name."""


class FetchTransportError(FetchError):
    """Network, HTTP or storage failure."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class RedirectNotAllowedError(FetchTransportError):
    """A redirect leaves the source host or downgrades from https."""


class DocumentNotFoundError(FetchError):
    """The source has no such document (HTTP 404, S3 NoSuchKey)."""


class ResponseTooLargeError(FetchError):
    """Response body is larger than FETCH_MAX_BYTES."""


class PayloadError(FetchError):
    """Payload does not match the mapper or the contracts."""


class InvalidReferenceError(FetchError):
    """external_id or cursor is unsafe or outside the source scope."""


class InvalidTenantError(FetchError):
    """tenant_id is empty, not a string, too long or has control characters."""
