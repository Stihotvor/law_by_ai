"""Drift tests for the full-settings keys and the Cohere rerank removal.

Each full-settings key must appear in the ``config.settings`` docstring table,
in ``docker/.env.example`` and in the ``x-app-env`` block of the compose file.
No Cohere rerank key or text may remain in the env example, compose file or
``src/config``.
"""

import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pytest
import yaml

import config.settings as settings_module
from config.settings import ROOT_DIR, Settings

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


def find_drift(
    docstring: str, env_text: str, app_env_keys: Iterable[str], keys: Iterable[str] = NEW_KEYS
) -> list[str]:
    """Return the keys missing from the docstring, the env example or ``x-app-env``."""
    compose_keys = set(app_env_keys)
    return [
        key
        for key in keys
        if f"``{key}``" not in docstring
        or not re.search(rf"^(# )?{key}=", env_text, re.MULTILINE)
        or key not in compose_keys
    ]


def _isolate_env(monkeypatch: pytest.MonkeyPatch, keys: Iterable[str]) -> None:
    """Clear ``keys`` and stop Settings() from loading a developer env file."""
    monkeypatch.setattr("config.settings.load_env", lambda: None)
    for key in keys:
        monkeypatch.delenv(key, raising=False)


def _docstring_default(key: str) -> str:
    """Return the default column of ``key``'s row in the settings docstring table."""
    docstring = settings_module.__doc__ or ""
    row = next(line for line in docstring.splitlines() if line.startswith(f"``{key}``"))
    return re.split(r"\s{2,}", row.strip())[-1].strip("`")


@pytest.mark.parametrize("key", NEW_KEYS)
def test_new_key_appears_in_all_three_places(key: str) -> None:
    """Each full-settings key is in the docstring, the env example and x-app-env."""
    missing = find_drift(settings_module.__doc__ or "", ENV_EXAMPLE.read_text(), _app_env(), [key])
    assert missing == []


def test_env_example_has_no_cohere_key() -> None:
    """The env example has no Cohere, RERANK_BASE_URL or RERANK_API_KEY text."""
    pattern = re.compile(r"cohere|rerank_base_url|rerank_api_key", re.IGNORECASE)
    assert not pattern.search(ENV_EXAMPLE.read_text())


def test_config_source_has_no_cohere_text() -> None:
    """QA-037. No text file under src/config mentions Cohere or its rerank keys."""
    pattern = re.compile(r"cohere|rerank_base_url|rerank_api_key", re.IGNORECASE)
    for path in (ROOT_DIR / "src" / "config").rglob("*"):
        if path.is_file() and path.suffix in {".py", ".txt", ".md", ".toml", ".yml", ".yaml"}:
            assert not pattern.search(path.read_text()), str(path)


def test_env_example_has_no_old_rerank_model_key() -> None:
    """QA-039. The env example has no RERANK_MODEL line, commented or not."""
    assert not re.search(r"^\s*#?\s*RERANK_MODEL=", ENV_EXAMPLE.read_text(), re.MULTILINE)


def test_env_example_defaults_match_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """QA-041. Each full-settings key in the env example has the Settings() default."""
    _isolate_env(monkeypatch, NEW_KEYS)
    settings = Settings()
    text = ENV_EXAMPLE.read_text()
    for key in NEW_KEYS:
        match = re.search(rf"^{key}=(.*)$", text, re.MULTILINE)
        assert match, key
        assert match.group(1) == str(getattr(settings, key.lower())), key


def test_env_example_explains_empty_otel_endpoint() -> None:
    """QA-042. The comment above the OTel endpoint says an empty value turns export off."""
    lines = ENV_EXAMPLE.read_text().splitlines()
    idx = next(i for i, line in enumerate(lines) if line.startswith("OTEL_EXPORTER_OTLP_ENDPOINT="))
    comment = " ".join(lines[max(0, idx - 3) : idx]).lower()
    assert "empty" in comment
    assert "export off" in comment


def test_drift_check_reports_missing_key(tmp_path: Path) -> None:
    """QA-051. The drift check reports MIN_CONFIDENCE when the env example lacks it."""
    lines = ENV_EXAMPLE.read_text().splitlines()
    copy = tmp_path / "env.example"
    copy.write_text("\n".join(line for line in lines if not line.startswith("MIN_CONFIDENCE=")))

    missing = find_drift(settings_module.__doc__ or "", copy.read_text(), _app_env())

    assert missing == ["MIN_CONFIDENCE"]


def test_docstring_migration_lock_default_matches_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """QA-052. The docstring default of MIGRATION_LOCK_TIMEOUT_S equals the Settings() default."""
    _isolate_env(monkeypatch, ["MIGRATION_LOCK_TIMEOUT_S"])

    documented = _docstring_default("MIGRATION_LOCK_TIMEOUT_S")

    assert float(documented) == Settings().migration_lock_timeout_s


def test_compose_keeps_only_two_rerank_keys() -> None:
    """The compose file has only the RERANK_MODEL_NAME and RERANK_MODEL_PATH keys."""
    lines = [line.strip() for line in COMPOSE.read_text().splitlines() if "RERANK_" in line]
    assert lines == ["RERANK_MODEL_NAME:", "RERANK_MODEL_PATH:"]
