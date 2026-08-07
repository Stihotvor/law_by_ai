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


def test_dockerfile_uses_python313_slim_and_nonroot():
    text = (ROOT / "docker" / "Dockerfile").read_text()
    assert "python:3.13-slim" in text
    assert "appuser" in text
    assert "USER appuser" in text


def test_dockerfile_has_runtime_and_test_targets():
    text = (ROOT / "docker" / "Dockerfile").read_text()
    assert "AS runtime" in text
    assert "AS test" in text
    # dev extras are only installed in the test target, never in runtime
    assert "--extra dev" in text
    runtime_section = text.split("AS runtime")[1].split("AS test")[0]
    assert "--extra dev" not in runtime_section


def test_compose_prod_targets_are_lean():
    text = (ROOT / "docker" / "docker-compose.yml").read_text()
    for service in ("app:", "celery-worker:", "postgres:", "redis:"):
        assert service in text
    assert "target: runtime" in text
    assert text.count("healthcheck:") >= 4
    assert "service_healthy" in text
    # production compose must not reference the test target
    assert "target: test" not in text


def test_compose_test_override_present():
    text = (ROOT / "docker" / "docker-compose.test.yml").read_text()
    assert "test:" in text
    assert "target: test" in text
    assert "--extra dev" not in text  # deps come from the build target, not compose


def test_dockerignore_present():
    assert (ROOT / ".dockerignore").exists()


def test_env_example_and_runtime_stubs_present():
    assert (ROOT / "src" / "config" / ".env.example").exists()
    assert (ROOT / "src" / "ui" / "app.py").exists()
    assert (ROOT / "src" / "tasks" / "celery_app.py").exists()


def test_readme_in_each_skeleton_dir():
    for rel in ("src", *(f"src/{p}" for p in PACKAGES), "src/evals", "scripts", "docker", "tests"):
        assert (ROOT / rel / "README.md").exists(), f"missing {rel}/README.md"
