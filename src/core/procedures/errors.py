"""Domain errors of the procedure knowledge base.

Messages hold no procedure content: only the source name, the step key and a
short reason built from field names and error types. Input-controlled names
(the source, key names) are truncated to ``MAX_NAME_CHARS`` and shown by ``repr``.
"""

MAX_NAME_CHARS = 80


def safe_text(value: str) -> str:
    """Return *value* truncated to ``MAX_NAME_CHARS`` and quoted by ``repr``."""
    return repr(value[:MAX_NAME_CHARS])


class ProcedureValidationError(Exception):
    """Raised when procedure data fails validation. Nothing is written."""

    def __init__(self, source: str, step_key: str | None, reason: str) -> None:
        self.source = source[:MAX_NAME_CHARS]
        self.step_key = step_key
        self.reason = reason
        where = f"step {step_key}" if step_key is not None else "procedure"
        super().__init__(f"invalid procedure in {safe_text(source)}, {where}: {reason}")


class ProcedureStoreError(Exception):
    """Raised when the procedure store fails. The cause is chained."""
