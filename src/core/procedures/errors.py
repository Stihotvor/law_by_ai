"""Domain errors of the procedure knowledge base.

Messages hold no procedure content: only the source name, the step key and a
short reason built from field names and error types.
"""


class ProcedureValidationError(Exception):
    """Raised when procedure data fails validation. Nothing is written."""

    def __init__(self, source: str, step_key: str | None, reason: str) -> None:
        self.source = source
        self.step_key = step_key
        self.reason = reason
        where = f"step {step_key}" if step_key is not None else "procedure"
        super().__init__(f"invalid procedure in {source}, {where}: {reason}")


class ProcedureStoreError(Exception):
    """Raised when the procedure store fails. The cause is chained."""
