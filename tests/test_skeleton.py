"""Smoke tests for the repo skeleton and Docker setup (issue #6)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

PACKAGES = (
    "core",
    "core/plugins",
    "core/security",
    "core/observability",
    "plugins",
    "agents",
    "tasks",
    "ui",
    "ui/pages",
    "ui/components",
    "config",
    "data",
    "storage",
)


def test_src_layout_packages_have_init():
    for pkg in PACKAGES:
        assert (ROOT / "src" / pkg / "__init__.py").exists(), f"missing src/{pkg}/__init__.py"


def test_pyproject_uses_src_layout():
    text = (ROOT / "pyproject.toml").read_text()
    assert 'where = ["src"]' in text


def test_dockerfile_uses_python311_slim_and_nonroot():
    text = (ROOT / "docker" / "Dockerfile").read_text()
    assert "python:3.11-slim" in text
    assert "appuser" in text
    assert "USER appuser" in text


def test_compose_has_all_services_with_healthchecks():
    text = (ROOT / "docker" / "docker-compose.yml").read_text()
    for service in ("app:", "celery-worker:", "postgres:", "redis:"):
        assert service in text
    assert text.count("healthcheck:") >= 4
    assert "service_healthy" in text


def test_dockerignore_present():
    assert (ROOT / ".dockerignore").exists()


def test_env_example_and_runtime_stubs_present():
    assert (ROOT / "src" / "config" / ".env.example").exists()
    assert (ROOT / "src" / "ui" / "app.py").exists()
    assert (ROOT / "src" / "tasks" / "celery_app.py").exists()


def test_readme_in_each_skeleton_dir():
    for rel in ("src", *(f"src/{p}" for p in PACKAGES), "src/evals", "scripts", "docker", "tests"):
        assert (ROOT / rel / "README.md").exists(), f"missing {rel}/README.md"
