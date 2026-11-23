"""Drift test for the full-settings keys (T2).

Each new key must appear in the ``config.settings`` docstring table, in
``docker/.env.example`` and in the ``x-app-env`` block of the compose file.
"""

import re
from typing import Any

import pytest
import yaml

import config.settings as settings_module
from config.settings import ROOT_DIR

ENV_EXAMPLE = ROOT_DIR / "docker" / ".env.example"
COMPOSE = ROOT_DIR / "docker" / "docker-compose.yml"

NEW_KEYS = [
    "QDRANT_URL",
    "QDRANT_API_KEY",
    "QDRANT_COLLECTION",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_SERVICE_NAME",
    "MIN_CONFIDENCE",
    "RERANK_MODEL_NAME",
    "RERANK_MODEL_PATH",
]


def _app_env() -> dict[str, Any]:
    """Return the parsed ``x-app-env`` block of the compose file."""
    return yaml.safe_load(COMPOSE.read_text())["x-app-env"]


@pytest.mark.parametrize("key", NEW_KEYS)
def test_new_key_appears_in_all_three_places(key: str) -> None:
    """Scenario Outline: A new key appears in all three places."""
    docstring = settings_module.__doc__ or ""
    assert f"``{key}``" in docstring
    env_text = ENV_EXAMPLE.read_text()
    assert re.search(rf"^(# )?{key}=", env_text, re.MULTILINE)
    assert key in _app_env()


def test_env_example_has_no_cohere_key() -> None:
    """Scenario: The env example has no Cohere key."""
    pattern = re.compile(r"cohere|rerank_base_url|rerank_api_key", re.IGNORECASE)
    assert not pattern.search(ENV_EXAMPLE.read_text())


def test_qa_037_config_source_has_no_cohere_text() -> None:
    pattern = re.compile(r"cohere|rerank_base_url|rerank_api_key", re.IGNORECASE)
    for path in (ROOT_DIR / "src" / "config").rglob("*"):
        if path.is_file() and path.suffix in {".py", ".txt", ".md", ".toml", ".yml", ".yaml"}:
            assert not pattern.search(path.read_text()), str(path)


def test_qa_039_env_example_has_no_old_rerank_model_key() -> None:
    assert not re.search(r"^\s*#?\s*RERANK_MODEL=", ENV_EXAMPLE.read_text(), re.MULTILINE)


def test_qa_041_env_example_defaults_match_settings() -> None:
    text = ENV_EXAMPLE.read_text()
    for line in (
        "QDRANT_URL=http://localhost:6333",
        "QDRANT_COLLECTION=legal_documents",
        "OTEL_SERVICE_NAME=law-by-ai",
        "MIN_CONFIDENCE=0.5",
    ):
        assert re.search(rf"^{re.escape(line)}$", text, re.MULTILINE), line
    for key in (
        "QDRANT_API_KEY",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "RERANK_MODEL_NAME",
        "RERANK_MODEL_PATH",
    ):
        assert re.search(rf"^{key}=$", text, re.MULTILINE), key


def test_qa_042_env_example_explains_empty_otel_endpoint() -> None:
    lines = ENV_EXAMPLE.read_text().splitlines()
    idx = next(i for i, line in enumerate(lines) if line.startswith("OTEL_EXPORTER_OTLP_ENDPOINT="))
    comment = " ".join(lines[max(0, idx - 3) : idx]).lower()
    assert "empty" in comment
    assert "export off" in comment


def test_qa_051_drift_check_catches_missing_key() -> None:
    lines = ENV_EXAMPLE.read_text().splitlines()
    text = "\n".join(line for line in lines if not line.startswith("MIN_CONFIDENCE="))

    assert not re.search(r"^(# )?MIN_CONFIDENCE=", text, re.MULTILINE)
    assert re.search(r"^(# )?QDRANT_URL=", text, re.MULTILINE)


def test_qa_052_docstring_lists_migration_lock_key() -> None:
    docstring = settings_module.__doc__ or ""
    row = next(
        (line for line in docstring.splitlines() if "``MIGRATION_LOCK_TIMEOUT_S``" in line), ""
    )
    assert "300" in row


def test_compose_keeps_only_two_rerank_keys() -> None:
    """Scenario: The compose file keeps only two RERANK keys."""
    lines = [line.strip() for line in COMPOSE.read_text().splitlines() if "RERANK_" in line]
    assert lines == ["RERANK_MODEL_NAME:", "RERANK_MODEL_PATH:"]
