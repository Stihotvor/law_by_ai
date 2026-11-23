"""Errors raised by the LLM client."""


class LLMError(Exception):
    """An LLM call failed; ``status_code`` holds the HTTP status if known."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class LLMTimeoutError(LLMError):
    """An LLM call timed out."""


class LLMConfigError(Exception):
    """The LLM config for an agent is missing or invalid."""
