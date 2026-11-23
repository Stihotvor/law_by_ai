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


def test_compose_keeps_only_two_rerank_keys() -> None:
    """Scenario: The compose file keeps only two RERANK keys."""
    lines = [line.strip() for line in COMPOSE.read_text().splitlines() if "RERANK_" in line]
    assert lines == ["RERANK_MODEL_NAME:", "RERANK_MODEL_PATH:"]
