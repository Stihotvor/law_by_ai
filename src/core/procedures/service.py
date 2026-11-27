"""Procedure service: the one entry point for seed, upload page and assistant.

Uses only the ``ProcedureRepository`` port. The admin check runs before any
store call; the actor comes from the request principal, never from an argument.
"""

import re
from collections.abc import Callable
from datetime import date

from core.security import require_admin_principal

from .models import KEBAB_PATTERN, ImportResult, Procedure, ProcedureSummary
from .parse import DEFAULT_SOURCE, parse_procedure_yaml
from .ports import ProcedureRepository

_SLUG = re.compile(KEBAB_PATTERN)


class ProcedureService:
    """Admin import and read access to curated procedures."""

    def __init__(
        self, repository: ProcedureRepository, *, today: Callable[[], date] = date.today
    ) -> None:
        self._repository = repository
        self._today = today

    def import_procedure(self, text: str, *, source: str = DEFAULT_SOURCE) -> ImportResult:
        """Parse *text* and store it as the current admin.

        *source* names the input (for example a file name) in validation errors.

        Raises:
            PrincipalRequiredError: no admin principal (nothing is parsed or stored).
            ProcedureValidationError: the YAML is invalid (nothing is stored).
            ProcedureStoreError: the store failed (cause chained by the repository).
        """
        actor = require_admin_principal().email
        procedure = parse_procedure_yaml(text, self._today(), source=source)
        return self._repository.save(procedure, actor)

    def get_procedure(self, slug: str) -> Procedure | None:
        """Return the procedure, or ``None`` if not found or *slug* is malformed."""
        if not _SLUG.fullmatch(slug):
            return None
        return self._repository.get(slug)

    def list_procedures(self) -> list[ProcedureSummary]:
        """Return all procedure summaries sorted by slug."""
        return sorted(self._repository.list(), key=lambda summary: summary.slug)
