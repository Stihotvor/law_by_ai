"""Seed files and the seed logic of scripts/seed_db.py (procedure-kb T5).

No network and no database: the service runs on an in-memory repository.
"""

import importlib.util
from datetime import date
from pathlib import Path
from types import ModuleType

import pytest

from core.procedures import (
    ImportResult,
    Procedure,
    ProcedureService,
    ProcedureSummary,
    parse_procedure_yaml,
)
from core.security import PrincipalRequiredError

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data" / "procedures"
SCRIPT = ROOT / "scripts" / "seed_db.py"
DOC = ROOT / "docs" / "migrations.md"
SEED_HEADING = "## Seed the procedures"
TODAY = date(2026, 11, 27)

STEP = """\
  - key: get-form
    text: Get the form.
    source_url: "{url}"
    last_checked: 2026-11-01
    verify_with_office: Ask the office if the form is current.
"""


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("seed_db", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _yaml(slug: str, url: str = "https://example.gov.pl/form") -> str:
    head = f"schema_version: 1\nslug: {slug}\ntitle: Title of {slug}\nsteps:\n"
    return head + STEP.format(url=url)


class FakeRepository:
    """In-memory port double that records every save."""

    def __init__(self) -> None:
        self.saved: list[tuple[Procedure, str]] = []

    def save(self, procedure: Procedure, actor: str) -> ImportResult:
        self.saved.append((procedure, actor))
        return ImportResult(slug=procedure.slug, revision=1, changed=True)

    def get(self, slug: str) -> Procedure | None:
        return None

    def list(self) -> list[ProcedureSummary]:
        return []


def _service(repo: FakeRepository) -> ProcedureService:
    return ProcedureService(repo, today=lambda: TODAY)


# --- the seed files -----------------------------------------------------------------


def test_exactly_three_seed_files() -> None:
    """Scenario: exactly three seed files."""
    files = sorted(DATA_DIR.glob("*.yaml"))
    assert len(files) == 3
    slugs = {parse_procedure_yaml(f.read_text(encoding="utf-8"), TODAY).slug for f in files}
    assert slugs == {"pesel", "residence-card", "tax-id"}


@pytest.mark.parametrize("name", ["pesel.yaml", "residence-card.yaml", "tax-id.yaml"])
def test_seed_content_is_complete(name: str) -> None:
    """Scenario: seed content is complete."""
    path = DATA_DIR / name
    procedure = parse_procedure_yaml(path.read_text(encoding="utf-8"), TODAY, source=name)
    assert procedure.slug == path.stem
    assert len(procedure.steps) >= 3
    for step in procedure.steps:
        assert step.source_url.startswith("https://")
        assert step.verify_with_office.strip()


# --- seed() -------------------------------------------------------------------------


def test_seed_imports_every_file_as_system_seed() -> None:
    repo = FakeRepository()
    results = _load().seed(DATA_DIR, _service(repo))
    assert [r.slug for r in results] == ["pesel", "residence-card", "tax-id"]
    assert {actor for _, actor in repo.saved} == {"system:seed"}


def test_seed_restores_the_principal() -> None:
    _load().seed(DATA_DIR, _service(FakeRepository()))
    with pytest.raises(PrincipalRequiredError):
        _service(FakeRepository()).import_procedure(_yaml("pesel"))


def test_bad_seed_file_writes_nothing(tmp_path: Path) -> None:
    """Scenario: bad seed file."""
    (tmp_path / "a-good.yaml").write_text(_yaml("a-good"), encoding="utf-8")
    (tmp_path / "b-bad.yaml").write_text(_yaml("b-bad", url=""), encoding="utf-8")
    repo = FakeRepository()
    module = _load()
    with pytest.raises(module.SeedError) as info:
        module.seed(tmp_path, _service(repo))
    assert "b-bad.yaml" in str(info.value)
    assert "a-good.yaml" not in str(info.value)
    assert repo.saved == []


def test_every_bad_file_is_named(tmp_path: Path) -> None:
    (tmp_path / "one.yaml").write_text("slug: [", encoding="utf-8")
    (tmp_path / "two.yaml").write_text(_yaml("two", url="http://x.pl"), encoding="utf-8")
    module = _load()
    with pytest.raises(module.SeedError) as info:
        module.seed(tmp_path, _service(FakeRepository()))
    assert "one.yaml" in str(info.value)
    assert "two.yaml" in str(info.value)


def test_duplicate_slug_stops_before_any_write(tmp_path: Path) -> None:
    """Scenario: duplicate slug."""
    (tmp_path / "first.yaml").write_text(_yaml("pesel"), encoding="utf-8")
    (tmp_path / "second.yaml").write_text(_yaml("pesel"), encoding="utf-8")
    repo = FakeRepository()
    module = _load()
    with pytest.raises(module.SeedError) as info:
        module.seed(tmp_path, _service(repo))
    assert "first.yaml" in str(info.value)
    assert "second.yaml" in str(info.value)
    assert repo.saved == []


def test_empty_directory_is_an_error(tmp_path: Path) -> None:
    module = _load()
    with pytest.raises(module.SeedError):
        module.seed(tmp_path, _service(FakeRepository()))


# --- main() -------------------------------------------------------------------------


def test_main_prints_one_line_per_file(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    module = _load()
    monkeypatch.setattr(module, "build_service", lambda: _service(FakeRepository()))
    assert module.main([str(DATA_DIR)]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines == [
        "pesel revision=1 changed=True",
        "residence-card revision=1 changed=True",
        "tax-id revision=1 changed=True",
    ]


def test_main_exits_non_zero_naming_the_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "broken.yaml").write_text(_yaml("broken", url=""), encoding="utf-8")
    repo = FakeRepository()
    module = _load()
    monkeypatch.setattr(module, "build_service", lambda: _service(repo))
    assert module.main([str(tmp_path)]) != 0
    captured = capsys.readouterr()
    assert "broken.yaml" in captured.err
    assert captured.out == ""
    assert repo.saved == []


# --- run order doc ------------------------------------------------------------------


def test_run_order_doc_migrate_before_seed() -> None:
    """Scenario: run order doc."""
    text = DOC.read_text(encoding="utf-8")
    assert SEED_HEADING in text
    section = text.split(SEED_HEADING, 1)[1].split("\n## ", 1)[0]
    assert "migrate" in section
    assert "seed" in section
    assert section.index("migrate") < section.index("seed")
    assert section.index("alembic upgrade head") < section.index("scripts/seed_db.py")
