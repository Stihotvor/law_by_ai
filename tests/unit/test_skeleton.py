"""Smoke tests for the repo skeleton and Docker setup (issue #6)."""

import re
import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]

PACKAGES = (
    "core",
    "core/plugins",
    "core/security",
    "core/observability",
    "plugins",
    "agents",
    "agents/fetch",
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
    assert "python:3.13" in text
    assert "-slim" in text
    assert "@sha256:" in text
    assert "appuser" in text
    assert "USER appuser" in text


def test_dockerfile_pins_images_uid_and_uv():
    text = (ROOT / "docker" / "Dockerfile").read_text()
    for line in text.splitlines():
        if line.startswith("FROM ") and not line.startswith(("FROM base", "FROM builder")):
            assert "@sha256:" in line
    assert "COPY --from=ghcr.io" not in text
    assert ":latest" not in text
    assert "--uid 10001" in text
    assert "PYTHONDONTWRITEBYTECODE=1" in text


def test_dockerignore_keeps_local_secret_files_out_of_context():
    lines = (ROOT / ".dockerignore").read_text().splitlines()
    for entry in (".env", "docker/.env", ".claude"):
        assert entry in lines
    assert not any(line.strip() in ("*.env*", ".env*", "*.example") for line in lines)


def test_dockerfile_has_runtime_and_test_targets():
    text = (ROOT / "docker" / "Dockerfile").read_text()
    assert "AS runtime" in text
    assert "AS test" in text
    # dev extras are only installed in the test target, never in runtime
    assert "--extra dev" in text
    runtime_section = text.split("AS runtime")[1].split("AS test")[0]
    assert "--extra dev" not in runtime_section


def test_compose_prod_services_use_lean_runtime_target():
    text = (ROOT / "docker" / "docker-compose.yml").read_text()
    for service in ("app:", "celery-worker:", "postgres:", "redis:"):
        assert service in text
    assert "healthcheck:" in text
    assert "service_healthy" in text
    # app and celery-worker build the lean `runtime` target (no dev extras)
    assert text.count("target: runtime") == 2
    assert text.count("target: test") == 1


def test_compose_test_service_is_profiled_and_lean():
    text = (ROOT / "docker" / "docker-compose.yml").read_text()
    assert "test:" in text
    assert 'profiles: ["test"]' in text
    assert "target: test" in text
    # dev extras come from the build target, never from compose
    assert "--extra dev" not in text
    assert text.count("healthcheck:") >= 4


def test_dockerignore_present():
    assert (ROOT / ".dockerignore").exists()


def test_env_example_and_runtime_stubs_present():
    assert (ROOT / "src" / "config" / ".env.example").exists()
    assert (ROOT / "src" / "ui" / "app.py").exists()
    assert (ROOT / "src" / "tasks" / "celery_app.py").exists()


def test_readme_in_each_skeleton_dir():
    for rel in ("src", *(f"src/{p}" for p in PACKAGES), "src/evals", "scripts", "docker", "tests"):
        assert (ROOT / rel / "README.md").exists(), f"missing {rel}/README.md"


def test_precommit_revs_match_pinned_dev_tools():
    dev = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["optional-dependencies"][
        "dev"
    ]
    pins = {d.split("==")[0].split("[")[0]: d.split("==")[1] for d in dev}
    config = yaml.safe_load((ROOT / ".pre-commit-config.yaml").read_text())
    revs = {r["repo"].rsplit("/", 1)[-1]: r["rev"].removeprefix("v") for r in config["repos"]}
    assert revs["ruff-pre-commit"] == pins["ruff"]
    assert revs["pyright-python"] == pins["pyright"]
    assert revs["bandit"] == pins["bandit"]


def _workflows() -> dict[str, dict]:
    paths = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
    return {p.name: yaml.safe_load(p.read_text()) for p in paths}


def test_every_workflow_job_has_timeout():
    for name, wf in _workflows().items():
        for job, spec in wf["jobs"].items():
            assert "timeout-minutes" in spec, f"{name}:{job} lacks timeout-minutes"


def _uses(node: object) -> list[str]:
    if isinstance(node, dict):
        found = [v for k, v in node.items() if k == "uses" and isinstance(v, str)]
        return found + [u for v in node.values() for u in _uses(v)]
    if isinstance(node, list):
        return [u for v in node for u in _uses(v)]
    return []


def test_every_action_is_pinned_to_a_full_sha():
    for name, wf in _workflows().items():
        for ref in _uses(wf):
            if ref.startswith("./"):
                continue
            assert re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", ref), f"{name}: {ref}"
