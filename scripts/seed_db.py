"""Seed the curated procedures from ``data/procedures/*.yaml`` (procedure-kb T5).

Run after the migrations (``uv run alembic upgrade head``). The seed parses
every file first, with the file name as ``source``. If any file is invalid, or
two files share a slug, it writes nothing and exits non-zero. Then it imports
each file through ``ProcedureService`` as the admin principal ``system:seed``,
connected as ``lawbyai_app`` (``POSTGRES_URL``). A rerun is safe: identical
content writes nothing.

Usage: uv run python scripts/seed_db.py [directory]
"""

import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from sqlalchemy import create_engine

from config.settings import get_settings
from core.procedures import (
    ImportResult,
    ProcedureService,
    ProcedureStoreError,
    ProcedureValidationError,
    parse_procedure_yaml,
)
from core.security import ADMIN, RequestPrincipal, principal_context
from plugins.relational_db.procedures import PostgresProcedureRepository

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "procedures"
SEED_PRINCIPAL = RequestPrincipal(email="system:seed", role=ADMIN)


class SeedError(Exception):
    """The seed stopped. The message names the file or files."""


def _check(files: Sequence[Path], today: date) -> None:
    """Parse every file; raise ``SeedError`` naming each bad file and each duplicate slug."""
    problems: list[str] = []
    owners: dict[str, str] = {}
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
            slug = parse_procedure_yaml(text, today, source=path.name).slug
        except ProcedureValidationError as exc:
            problems.append(str(exc))
            continue
        first = owners.setdefault(slug, path.name)
        if first != path.name:
            problems.append(f"duplicate slug {slug} in {first} and {path.name}")
    if problems:
        raise SeedError("seed stopped, nothing written: " + "; ".join(problems))


def _import(path: Path, service: ProcedureService) -> ImportResult:
    try:
        return service.import_procedure(path.read_text(encoding="utf-8"), source=path.name)
    except ProcedureStoreError as exc:
        raise SeedError(f"seed failed in {path.name}: {exc}") from exc


def seed(directory: Path, service: ProcedureService) -> list[ImportResult]:
    """Check all YAML files in *directory*, then import each one as ``system:seed``.

    Raises:
        SeedError: no file, a bad file or a duplicate slug (nothing written),
            or a store failure (names the file).
    """
    files = sorted(directory.glob("*.yaml"))
    if not files:
        raise SeedError(f"no *.yaml files in {directory}")
    _check(files, date.today())
    with principal_context(SEED_PRINCIPAL):
        return [_import(path, service) for path in files]


def build_service() -> ProcedureService:
    """Return the service on the app connection (``lawbyai_app``, ``POSTGRES_URL``)."""
    engine = create_engine(get_settings().postgres_url, future=True)
    return ProcedureService(PostgresProcedureRepository(engine))


def main(argv: Sequence[str]) -> int:
    directory = Path(argv[0]) if argv else DATA_DIR
    try:
        results = seed(directory, build_service())
    except SeedError as exc:
        print(exc, file=sys.stderr)
        return 1
    for result in results:
        print(f"{result.slug} revision={result.revision} changed={result.changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
