"""Smoke tests verifying the dev environment and project scaffolding."""

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_pyproject_is_valid_toml():
    with (ROOT / "pyproject.toml").open("rb") as fh:
        data = tomllib.load(fh)
    assert data["project"]["name"] == "law-by-ai"
    assert "dev" in data["project"]["optional-dependencies"]
    assert "docs" in data["project"]["optional-dependencies"]


def test_ruff_lint_config_present():
    with (ROOT / "pyproject.toml").open("rb") as fh:
        data = tomllib.load(fh)
    assert "ruff" in data["tool"]
    assert data["tool"]["ruff"]["line-length"] == 100


def test_pytest_config_present():
    with (ROOT / "pyproject.toml").open("rb") as fh:
        data = tomllib.load(fh)
    pytest_opts = data["tool"]["pytest"]["ini_options"]
    assert any("integration" in m for m in pytest_opts["markers"])
    assert any("security" in m for m in pytest_opts["markers"])


def test_ci_workflow_has_lint_unit_and_integration_jobs():
    ci = ROOT / ".github" / "workflows" / "ci.yml"
    assert ci.exists()
    text = ci.read_text()
    assert "paths-ignore" in text
    assert "'docs/**'" in text
    for job in ("lint", "unit-test", "typecheck", "security", "integration-test"):
        assert f"  {job}:" in text


def test_docs_workflow_has_build_deploy_jobs():
    docs = ROOT / ".github" / "workflows" / "docs.yml"
    assert docs.exists()
    text = docs.read_text()
    assert "paths:" in text
    assert "'docs/**'" in text
    for job in ("build", "deploy"):
        assert f"  {job}:" in text
    assert "-f docs/mkdocs.yml" in text


def test_mkdocs_config_is_in_docs_dir():
    cfg = ROOT / "docs" / "mkdocs.yml"
    assert cfg.exists()
    text = cfg.read_text()
    assert "docs_dir: ." in text
    assert "site_dir: ../site" in text
