"""Seed the curated procedures from ``data/procedures/*.yaml``.

Run after the migrations (``uv run alembic upgrade head``). The seed parses
every file first, with the file name as ``source``. If any file is invalid, or
two files share a slug, it writes nothing and exits non-zero. Then it imports
each file through ``ProcedureService`` as the admin principal ``system:seed``,
connected as ``lawbyai_app`` (``POSTGRES_URL``). The check and the import use
one ``today``. A rerun is safe: identical content writes nothing.

Usage: uv run python scripts/seed_db.py [directory]
"""

import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from sqlalchemy import Engine, create_engine

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


_READ_ERRORS = (OSError, UnicodeDecodeError)


def _read(path: Path) -> str:
    """Return the UTF-8 text of *path*; raise ``SeedError`` naming the file if unreadable."""
    try:
        return path.read_text(encoding="utf-8")
    except _READ_ERRORS as exc:
        raise SeedError(f"cannot read {path.name}: {type(exc).__name__}") from exc


def _check(files: Sequence[Path], today: date) -> None:
    """Parse every file; raise ``SeedError`` naming each bad file and each duplicate slug."""
    problems: list[str] = []
    owners: dict[str, str] = {}
    for path in files:
        try:
            slug = parse_procedure_yaml(_read(path), today, source=path.name).slug
        except (SeedError, ProcedureValidationError) as exc:
            problems.append(str(exc))
            continue
        first = owners.setdefault(slug, path.name)
        if first != path.name:
            problems.append(f"duplicate slug {slug} in {first} and {path.name}")
    if problems:
        raise SeedError("seed stopped, nothing written: " + "; ".join(problems))


def _import(path: Path, service: ProcedureService) -> ImportResult:
    """Import one file; raise ``SeedError`` naming the file on any failure."""
    text = _read(path)
    try:
        return service.import_procedure(text, source=path.name)
    except (ProcedureValidationError, ProcedureStoreError) as exc:
        raise SeedError(f"seed failed in {path.name}: {exc}") from exc


def seed(directory: Path, service: ProcedureService, today: date) -> list[ImportResult]:
    """Check all YAML files in *directory*, then import each one as ``system:seed``.

    The check uses *today*; build *service* with the same ``today`` (see ``main``).

    Raises:
        SeedError: no file, a bad file or a duplicate slug (nothing written),
            or a store failure (names the file).
    """
    files = sorted(directory.glob("*.yaml"))
    if not files:
        raise SeedError(f"no *.yaml files in {directory}")
    _check(files, today)
    with principal_context(SEED_PRINCIPAL):
        return [_import(path, service) for path in files]


def build_engine() -> Engine:
    """Return the engine on the app connection (``lawbyai_app``, ``POSTGRES_URL``)."""
    return create_engine(get_settings().postgres_url)


def build_service(engine: Engine, today: date) -> ProcedureService:
    """Return the service on *engine* with a clock fixed at *today*."""
    return ProcedureService(PostgresProcedureRepository(engine), today=lambda: today)


def main(argv: Sequence[str]) -> int:
    directory = Path(argv[0]) if argv else DATA_DIR
    today = date.today()
    engine = build_engine()
    try:
        results = seed(directory, build_service(engine, today), today)
    except SeedError as exc:
        print(exc, file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    for result in results:
        print(f"{result.slug} revision={result.revision} changed={result.changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
