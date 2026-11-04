"""Tests for the mutation score gate script."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "mutation_score.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("mutation_score", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(root: Path, codes: dict[str, int | None]) -> None:
    (root / "pkg").mkdir(parents=True, exist_ok=True)
    (root / "pkg" / "m.py.meta").write_text(json.dumps({"exit_code_by_key": codes}))


def test_counts_survivors_and_unchecked_as_not_killed(tmp_path: Path) -> None:
    _write(tmp_path, {"a": 1, "b": 0, "c": None, "d": 3})
    assert _load().count(tmp_path) == (2, 4)


@pytest.mark.parametrize("code", [1, 3, 36, 24, -24, 152, 255, -11, -9, 37])
def test_detected_codes_count_as_killed(tmp_path: Path, code: int) -> None:
    _write(tmp_path, {"a": code})
    assert _load().count(tmp_path) == (1, 1)


@pytest.mark.parametrize("code", [0, 2, 5, 33, 34, 35, 99, None])
def test_other_codes_stay_in_total_only(tmp_path: Path, code: int | None) -> None:
    _write(tmp_path, {"a": code})
    assert _load().count(tmp_path) == (0, 1)


def test_percent_of_empty_total_is_zero() -> None:
    assert _load().percent(0, 0) == 0.0
    assert _load().percent(1, 4) == 25.0


def test_passes_at_the_threshold_and_fails_below(tmp_path: Path) -> None:
    module = _load()
    minimum = module.MIN_KILLED_PERCENT
    _write(tmp_path, {str(i): (1 if i < minimum else 0) for i in range(100)})
    assert module.main(["x", str(tmp_path)]) == 0
    _write(tmp_path, {str(i): (1 if i < minimum - 1 else 0) for i in range(100)})
    assert module.main(["x", str(tmp_path)]) == 1


def test_fails_when_no_mutants_exist(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert _load().main(["x", str(tmp_path)]) == 1
    assert "no mutants found" in capsys.readouterr().out
