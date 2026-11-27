"""Port between the procedure service and the procedure store."""

from typing import Protocol

from .models import ImportResult, Procedure, ProcedureSummary


class ProcedureRepository(Protocol):
    """Procedure store. Each call opens and closes its own session."""

    def save(self, procedure: Procedure, actor: str) -> ImportResult:
        """Store *procedure* as a new revision by *actor*, or write nothing if identical.

        Identical means ``procedure.model_dump(mode="json", exclude={"revision"})``
        equals the latest revision content; the actor does not count. Then
        ``changed=False``.
        Raises ``ProcedureStoreError`` on a store failure, with the cause chained.
        """
        ...

    def get(self, slug: str) -> Procedure | None:
        """Return the current procedure with its ``revision``, or ``None`` if not found."""
        ...

    def list(self) -> list[ProcedureSummary]:
        """Return a summary of every stored procedure, sorted by slug."""
        ...
