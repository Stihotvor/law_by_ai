"""Tests for src/config/settings.py (issue #7)."""

import os

import pytest

from config.settings import ROOT_DIR, Settings, get_settings, load_env, positive_float

# Environment variables the settings module may read.
_ENV_KEYS = (
    "APP_NAME",
    "APP_PORT",
    "CELERY_BROKER_URL",
    "CELERY_RESULT_BACKEND_URL",
    "POSTGRES_DB",
    "POSTGRES_HOST",
    "POSTGRES_PASSWORD",
    "POSTGRES_PORT",
    "POSTGRES_URL",
    "POSTGRES_OWNER_URL",
    "POSTGRES_USER",
    "LAWBYAI_APP_PASSWORD",
    "LAWBYAI_OWNER_PASSWORD",
    "REDIS_DB",
    "REDIS_HOST",
    "REDIS_PASSWORD",
    "REDIS_PORT",
    "REDIS_URL",
    "LLM_MODEL",
    "LLM_MODEL_DOCUMENT_FETCHER",
    "LLM_MODEL_DOCUMENT_PROCESSOR",
    "LLM_MODEL_LEGAL_RESEARCH",
    "LLM_MODEL_CHANGE_TRACKER",
    "LLM_MODEL_KNOWLEDGE_GRAPH",
    "LLM_MODEL_ANALYSIS",
    "LLM_MODEL_BUREAUCRACY_ASSISTANT",
    "LLM_API_KEY",
    "LLM_API_KEY_DOCUMENT_PROCESSOR",
    "LLM_BASE_URL",
    "LLM_BASE_URL_BUREAUCRACY_ASSISTANT",
    "LLM_TIMEOUT",
    "QDRANT_URL",
    "QDRANT_API_KEY",
    "QDRANT_COLLECTION",
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "OTEL_SERVICE_NAME",
    "MIN_CONFIDENCE",
    "RERANK_MODEL_NAME",
    "RERANK_MODEL_PATH",
)


DEFAULT_DB_CRED = "lawbyai"


def _clear_env(monkeypatch) -> None:
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_defaults_when_no_environment(monkeypatch):
    _clear_env(monkeypatch)
    settings = Settings()

    assert settings.postgres_user == "lawbyai"
    assert settings.postgres_password == DEFAULT_DB_CRED
    assert settings.postgres_db == "lawbyai"
    assert settings.postgres_host == "localhost"
    assert settings.postgres_port == "5432"
    assert settings.postgres_url == "postgresql+psycopg://lawbyai_app:@localhost:5432/lawbyai"
    assert (
        settings.postgres_owner_url == "postgresql+psycopg://lawbyai_owner:@localhost:5432/lawbyai"
    )
    assert settings.redis_user == ""
    assert settings.redis_password == ""
    assert settings.redis_host == "localhost"
    assert settings.redis_port == "6379"
    assert settings.redis_db == "0"
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.celery_broker_url == settings.redis_url
    assert settings.celery_result_backend_url == settings.redis_url
    assert settings.app_port == 8501
    assert settings.app_name == "law-by-ai"


def test_environment_overrides(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("POSTGRES_URL", "postgresql://u:p@db:5432/x")
    monkeypatch.setenv("REDIS_URL", "redis://r:6379/1")
    monkeypatch.setenv("CELERY_BROKER_URL", "redis://b:6379/0")
    monkeypatch.setenv("CELERY_RESULT_BACKEND_URL", "redis://res:6379/0")
    monkeypatch.setenv("APP_PORT", "9000")
    monkeypatch.setenv("APP_NAME", "legal-assistant")

    settings = Settings()

    assert settings.postgres_url == "postgresql://u:p@db:5432/x"
    assert settings.redis_url == "redis://r:6379/1"
    assert settings.celery_broker_url == "redis://b:6379/0"
    assert settings.celery_result_backend_url == "redis://res:6379/0"
    assert settings.app_port == 9000
    assert settings.app_name == "legal-assistant"


def test_database_url_assembled_from_postgres_parts(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("POSTGRES_USER", "admin")  # bootstrap superuser: not in the app URL
    monkeypatch.setenv("POSTGRES_PASSWORD", "superuser-secret")
    monkeypatch.setenv("LAWBYAI_APP_PASSWORD", "p@ss:word")  # needs URL quoting
    monkeypatch.setenv("POSTGRES_DB", "legal")
    monkeypatch.setenv("POSTGRES_HOST", "db.internal")
    monkeypatch.setenv("POSTGRES_PORT", "5433")

    settings = Settings()

    assert (
        settings.postgres_url
        == "postgresql+psycopg://lawbyai_app:p%40ss%3Aword@db.internal:5433/legal"
    )


def test_settings_owner_url_comes_from_env(monkeypatch):
    """Scenario: Owner URL comes from env."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("LAWBYAI_OWNER_PASSWORD", "own/er@pw")  # needs URL quoting
    monkeypatch.setenv("LAWBYAI_APP_PASSWORD", "app-pw")
    monkeypatch.setenv("POSTGRES_USER", "superuser")
    monkeypatch.setenv("POSTGRES_PASSWORD", "superuser-secret")
    monkeypatch.setenv("POSTGRES_HOST", "db")

    settings = Settings()

    owner = settings.postgres_owner_url
    assert owner == "postgresql+psycopg://lawbyai_owner:own%2Fer%40pw@db:5432/lawbyai"
    assert owner != settings.postgres_url
    assert settings.postgres_url == "postgresql+psycopg://lawbyai_app:app-pw@db:5432/lawbyai"
    assert "superuser" not in owner + settings.postgres_url


def test_settings_url_overrides_win(monkeypatch):
    """Scenario: URL override wins."""
    _clear_env(monkeypatch)
    monkeypatch.setenv("LAWBYAI_OWNER_PASSWORD", "owner-pw")
    monkeypatch.setenv("LAWBYAI_APP_PASSWORD", "app-pw")
    monkeypatch.setenv("POSTGRES_OWNER_URL", "postgresql://o:p@db:5432/x")
    monkeypatch.setenv("POSTGRES_URL", "postgresql://a:p@db:5432/x")

    settings = Settings()

    assert settings.postgres_owner_url == "postgresql://o:p@db:5432/x"
    assert settings.postgres_url == "postgresql://a:p@db:5432/x"


def test_redis_url_assembled_from_parts(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("REDIS_USER", "admin")
    monkeypatch.setenv("REDIS_PASSWORD", "r@di:s")  # needs URL quoting
    monkeypatch.setenv("REDIS_HOST", "redis.internal")
    monkeypatch.setenv("REDIS_PORT", "6380")
    monkeypatch.setenv("REDIS_DB", "2")

    settings = Settings()

    assert settings.redis_url == "redis://admin:r%40di%3As@redis.internal:6380/2"


def test_redis_url_wins_over_parts(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("REDIS_URL", "redis://r:6379/1")
    monkeypatch.setenv("REDIS_HOST", "redis.internal")
    monkeypatch.setenv("REDIS_PORT", "6380")
    monkeypatch.setenv("REDIS_DB", "2")

    settings = Settings()

    assert settings.redis_url == "redis://r:6379/1"


def test_redis_url_no_creds_segment_when_empty(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("REDIS_HOST", "myhost")
    monkeypatch.setenv("REDIS_PORT", "6380")
    monkeypatch.setenv("REDIS_DB", "1")

    settings = Settings()

    assert settings.redis_url == "redis://myhost:6380/1"


def test_celery_urls_fall_back_to_redis(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")

    settings = Settings()

    assert settings.celery_broker_url == "redis://redis:6379/0"
    assert settings.celery_result_backend_url == "redis://redis:6379/0"


def test_llm_model_defaults_to_empty_and_agents_fall_back(monkeypatch):
    _clear_env(monkeypatch)
    settings = Settings()

    assert settings.llm_model == ""
    for name in (
        "document_fetcher",
        "document_processor",
        "legal_research",
        "change_tracker",
        "knowledge_graph",
        "analysis",
        "bureaucracy_assistant",
    ):
        assert getattr(settings, f"llm_model_{name}") == ""


def test_llm_model_default_applies_to_all_agents(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("LLM_MODEL", "qwen2.5:7b")

    settings = Settings()

    assert settings.llm_model == "qwen2.5:7b"
    assert settings.llm_model_legal_research == "qwen2.5:7b"
    assert settings.llm_model_document_fetcher == "qwen2.5:7b"


def test_llm_model_per_agent_override(monkeypatch):
    _clear_env(monkeypatch)
    monkeypatch.setenv("LLM_MODEL", "qwen2.5:7b")
    monkeypatch.setenv("LLM_MODEL_LEGAL_RESEARCH", "gpt-4o-mini")

    settings = Settings()

    assert settings.llm_model == "qwen2.5:7b"
    assert settings.llm_model_legal_research == "gpt-4o-mini"
    assert settings.llm_model_document_fetcher == "qwen2.5:7b"


def test_get_settings_is_a_singleton():
    assert get_settings() is get_settings()


def test_load_env_reads_file(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    env_file = tmp_path / ".env"
    env_file.write_text("APP_PORT=8123\nREDIS_URL=redis://x:6379/2\n")

    load_env(env_file)

    assert os.environ["APP_PORT"] == "8123"
    assert os.environ["REDIS_URL"] == "redis://x:6379/2"


def test_root_dir_points_at_repo_root():
    # Container WORKDIR is /app; local checkout is <repo>/law_by_ai.
    assert (ROOT_DIR / "pyproject.toml").exists()


_LOCK_VAR = "MIGRATION_LOCK_TIMEOUT_S"


def _isolate_lock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stop Settings() from loading the env file and clear the lock timeout variable."""
    monkeypatch.setattr("config.settings.load_env", lambda: None)
    monkeypatch.delenv(_LOCK_VAR, raising=False)


def test_migration_lock_timeout_defaults_to_300(monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate_lock_env(monkeypatch)

    assert Settings().migration_lock_timeout_s == 300.0


def test_migration_lock_timeout_reads_valid_value(monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate_lock_env(monkeypatch)
    monkeypatch.setenv(_LOCK_VAR, "12.5")

    assert Settings().migration_lock_timeout_s == 12.5


@pytest.mark.parametrize("value", ["0", "-5", "abc"])
def test_migration_lock_timeout_rejects_invalid_value(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    _isolate_lock_env(monkeypatch)
    monkeypatch.setenv(_LOCK_VAR, value)

    with pytest.raises(ValueError, match=_LOCK_VAR):
        _ = Settings().migration_lock_timeout_s


# --- Full settings: Qdrant, OTel, min_confidence, local rerank model ---------

_NEW_DEFAULTS: tuple[tuple[str, str, object], ...] = (
    ("QDRANT_URL", "qdrant_url", "http://localhost:6333"),
    ("QDRANT_API_KEY", "qdrant_api_key", ""),
    ("QDRANT_COLLECTION", "qdrant_collection", "legal_documents"),
    ("OTEL_EXPORTER_OTLP_ENDPOINT", "otel_exporter_otlp_endpoint", ""),
    ("OTEL_SERVICE_NAME", "otel_service_name", "law-by-ai"),
    ("MIN_CONFIDENCE", "min_confidence", 0.5),
    ("RERANK_MODEL_NAME", "rerank_model_name", ""),
    ("RERANK_MODEL_PATH", "rerank_model_path", ""),
)

_NEW_OVERRIDES: tuple[tuple[str, str, str, object], ...] = (
    ("QDRANT_URL", "qdrant_url", "qdrant:6333", "qdrant:6333"),
    ("QDRANT_API_KEY", "qdrant_api_key", "k1", "k1"),
    ("QDRANT_COLLECTION", "qdrant_collection", "c1", "c1"),
    (
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "otel_exporter_otlp_endpoint",
        "http://alloy:4317",
        "http://alloy:4317",
    ),
    ("OTEL_SERVICE_NAME", "otel_service_name", "svc", "svc"),
    ("MIN_CONFIDENCE", "min_confidence", "0.8", 0.8),
    ("RERANK_MODEL_NAME", "rerank_model_name", "bge-reranker", "bge-reranker"),
    ("RERANK_MODEL_PATH", "rerank_model_path", "/models/rerank", "/models/rerank"),
)

_NEW_PROPERTIES = tuple(prop for _, prop, _ in _NEW_DEFAULTS)
_MIN_CONF = "MIN_CONFIDENCE"


def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear the known keys and stop Settings() from loading a developer .env."""
    _clear_env(monkeypatch)
    monkeypatch.setattr("config.settings.load_env", lambda: None)


def test_env_keys_cover_new_keys() -> None:
    for key, _, _ in _NEW_DEFAULTS:
        assert key in _ENV_KEYS


def test_clear_env_removes_new_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, _, _ in _NEW_DEFAULTS:
        monkeypatch.setenv(key, "x")

    _clear_env(monkeypatch)

    for key, _, _ in _NEW_DEFAULTS:
        assert key not in os.environ


@pytest.mark.parametrize(("key", "prop", "default"), _NEW_DEFAULTS)
def test_new_key_uses_default_when_unset(
    monkeypatch: pytest.MonkeyPatch, key: str, prop: str, default: object
) -> None:
    _isolate_env(monkeypatch)

    assert key not in os.environ
    assert getattr(Settings(), prop) == default


@pytest.mark.parametrize(("key", "prop", "default"), _NEW_DEFAULTS)
def test_new_key_empty_value_uses_default(
    monkeypatch: pytest.MonkeyPatch, key: str, prop: str, default: object
) -> None:
    _isolate_env(monkeypatch)
    monkeypatch.setenv(key, "")

    assert getattr(Settings(), prop) == default


@pytest.mark.parametrize(("key", "prop", "value", "expected"), _NEW_OVERRIDES)
def test_new_key_takes_environment_value(
    monkeypatch: pytest.MonkeyPatch, key: str, prop: str, value: str, expected: object
) -> None:
    _isolate_env(monkeypatch)
    monkeypatch.setenv(key, value)

    assert getattr(Settings(), prop) == expected


@pytest.mark.parametrize("value", ["abc", "-0.1", "1.1", "nan", "inf", "   "])
def test_min_confidence_rejects_bad_value(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    _isolate_env(monkeypatch)
    monkeypatch.setenv(_MIN_CONF, value)

    with pytest.raises(ValueError, match=_MIN_CONF):
        _ = Settings().min_confidence


@pytest.mark.parametrize(("value", "expected"), [("0", 0.0), ("1", 1.0), (" 0.5 ", 0.5)])
def test_min_confidence_accepts_valid_value(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: float
) -> None:
    _isolate_env(monkeypatch)
    monkeypatch.setenv(_MIN_CONF, value)

    assert Settings().min_confidence == expected


def test_min_confidence_empty_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate_env(monkeypatch)
    monkeypatch.setenv(_MIN_CONF, "")

    assert Settings().min_confidence == 0.5


@pytest.mark.parametrize(
    "name", ["rerank_enabled", "rerank_base_url", "rerank_api_key", "rerank_model"]
)
def test_cohere_settings_are_gone(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    _isolate_env(monkeypatch)

    assert not hasattr(Settings, name)
    assert not hasattr(Settings(), name)


def test_old_rerank_keys_do_no_harm(monkeypatch: pytest.MonkeyPatch) -> None:
    """QA-036. Old Cohere rerank keys raise nothing and leave the new defaults."""
    _isolate_env(monkeypatch)
    monkeypatch.setenv("RERANK_BASE_URL", "https://api.cohere.com/v1")
    monkeypatch.setenv("RERANK_API_KEY", "old-key")
    monkeypatch.setenv("RERANK_MODEL", "rerank-v3.5")

    settings = Settings()

    for _, prop, default in _NEW_DEFAULTS:
        assert getattr(settings, prop) == default


def test_bad_min_confidence_never_falls_back(monkeypatch: pytest.MonkeyPatch) -> None:
    """QA-028. A bad MIN_CONFIDENCE raises on every read, never a fallback."""
    _isolate_env(monkeypatch)
    monkeypatch.setenv(_MIN_CONF, "2")
    settings = Settings()

    for _ in range(2):
        with pytest.raises(ValueError, match=_MIN_CONF):
            _ = settings.min_confidence


def test_value_change_read_on_next_access(monkeypatch: pytest.MonkeyPatch) -> None:
    """QA-029. A changed MIN_CONFIDENCE is read on the next access."""
    _isolate_env(monkeypatch)
    monkeypatch.setenv(_MIN_CONF, "0.3")
    settings = Settings()
    assert settings.min_confidence == 0.3

    monkeypatch.setenv(_MIN_CONF, "0.9")

    assert settings.min_confidence == 0.9


def test_empty_rerank_values_do_not_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """QA-031. Empty RERANK_MODEL_NAME and RERANK_MODEL_PATH read as empty."""
    _isolate_env(monkeypatch)
    monkeypatch.setenv("RERANK_MODEL_NAME", "")
    monkeypatch.setenv("RERANK_MODEL_PATH", "")
    settings = Settings()

    assert settings.rerank_model_name == ""
    assert settings.rerank_model_path == ""


def test_bad_min_confidence_error_has_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """QA-033. The MIN_CONFIDENCE error does not contain the Qdrant API key."""
    _isolate_env(monkeypatch)
    monkeypatch.setenv("QDRANT_API_KEY", "s3cret-key-123")
    monkeypatch.setenv(_MIN_CONF, "abc")

    with pytest.raises(ValueError, match=_MIN_CONF) as excinfo:
        _ = Settings().min_confidence

    assert "s3cret-key-123" not in str(excinfo.value)


def test_qdrant_api_key_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """QA-034. Any QDRANT_API_KEY value reads without error."""
    _isolate_env(monkeypatch)
    monkeypatch.setenv("QDRANT_API_KEY", "  odd value  ")

    _ = Settings().qdrant_api_key


def test_developer_env_cannot_change_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """QA-053. Values set before isolation do not leak into the defaults."""
    monkeypatch.setenv(_MIN_CONF, "0.9")
    monkeypatch.setenv("QDRANT_URL", "http://dev:1")
    _isolate_env(monkeypatch)

    settings = Settings()

    assert settings.min_confidence == 0.5
    assert settings.qdrant_url == "http://localhost:6333"


# --- LLM client: llm_setting and llm_timeout (T1) ----------------------------

_LLM_TIMEOUT = "LLM_TIMEOUT"


def test_llm_setting_prefers_agent_value(monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate_env(monkeypatch)
    monkeypatch.setenv("LLM_MODEL", "global-m")
    monkeypatch.setenv("LLM_MODEL_BUREAUCRACY_ASSISTANT", "agent-m")

    assert Settings().llm_setting("model", "bureaucracy_assistant") == "agent-m"


def test_llm_setting_falls_back_to_global(monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate_env(monkeypatch)
    monkeypatch.setenv("LLM_MODEL", "global-m")

    assert Settings().llm_setting("model", "document_processor") == "global-m"


def test_llm_setting_empty_when_both_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate_env(monkeypatch)

    assert Settings().llm_setting("api_key", "document_processor") == ""


def test_llm_setting_base_url_defaults_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate_env(monkeypatch)

    settings = Settings()
    assert settings.llm_setting("base_url", "bureaucracy_assistant") == "http://localhost:11434/v1"
    assert settings.llm_base_url == "http://localhost:11434/v1"


def test_llm_timeout_defaults_to_60(monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate_env(monkeypatch)

    assert Settings().llm_timeout == 60.0


def test_llm_timeout_accepts_padded_number(monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate_env(monkeypatch)
    monkeypatch.setenv(_LLM_TIMEOUT, " 0.2 ")

    assert Settings().llm_timeout == 0.2


@pytest.mark.parametrize("value", ["abc", "0", "-1", "nan", "inf"])
def test_llm_timeout_rejects_bad_value(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    _isolate_env(monkeypatch)
    monkeypatch.setenv(_LLM_TIMEOUT, value)

    with pytest.raises(ValueError, match=_LLM_TIMEOUT):
        _ = Settings().llm_timeout


def test_llm_model_property_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate_env(monkeypatch)
    monkeypatch.setenv("LLM_MODEL_BUREAUCRACY_ASSISTANT", "m1")

    assert Settings().llm_model_bureaucracy_assistant == "m1"


def test_llm_model_global_and_agent_properties_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate_env(monkeypatch)
    monkeypatch.setenv("LLM_MODEL", "g")
    monkeypatch.setenv("LLM_MODEL_ANALYSIS", "x1")

    settings = Settings()

    assert settings.llm_model_analysis == "x1"
    assert settings.llm_model == "g"


def test_bad_llm_timeout_raises_plain_value_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate_env(monkeypatch)
    monkeypatch.setenv(_LLM_TIMEOUT, "abc")

    with pytest.raises(ValueError, match=_LLM_TIMEOUT) as info:
        _ = Settings().llm_timeout

    assert type(info.value) is ValueError


def test_llm_timeout_error_does_not_echo_value(monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate_env(monkeypatch)
    monkeypatch.setenv(_LLM_TIMEOUT, "-7.5")

    with pytest.raises(ValueError, match=_LLM_TIMEOUT) as info:
        _ = Settings().llm_timeout

    assert "-7.5" not in str(info.value)


@pytest.mark.parametrize(
    ("field", "agent", "expected"),
    [
        ("timeout", None, "LLM_TIMEOUT"),
        ("base_url", "analysis", "LLM_BASE_URL_ANALYSIS"),
        ("MODEL", "Legal_Research", "LLM_MODEL_LEGAL_RESEARCH"),
    ],
)
def test_llm_var_name(field: str, agent: str | None, expected: str) -> None:
    assert Settings.llm_var_name(field, agent) == expected


def test_positive_float_empty_gives_default() -> None:
    assert positive_float("X_VAR", "", 3.5) == 3.5


def test_positive_float_strips_whitespace() -> None:
    assert positive_float("X_VAR", " 2.5 ", 3.5) == 2.5


@pytest.mark.parametrize("raw", ["abc", " ", "0", "-1", "nan", "inf", "-inf"])
def test_positive_float_rejects_bad_value(raw: str) -> None:
    with pytest.raises(ValueError, match="X_VAR") as info:
        positive_float("X_VAR", raw, 3.5)

    assert type(info.value) is ValueError
    assert info.value.__cause__ is None


def test_positive_float_message_hides_value() -> None:
    with pytest.raises(ValueError, match="X_VAR") as info:
        positive_float("X_VAR", "secret-ish", 3.5)

    assert "secret-ish" not in str(info.value)


def test_llm_agent_timeout_prefers_agent_value(monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate_env(monkeypatch)
    monkeypatch.setenv(_LLM_TIMEOUT, "abc")
    monkeypatch.setenv(f"{_LLM_TIMEOUT}_ANALYSIS", " 5 ")

    assert Settings().llm_agent_timeout("analysis") == 5.0


def test_llm_agent_timeout_falls_back_to_global(monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate_env(monkeypatch)
    monkeypatch.setenv(_LLM_TIMEOUT, "7")
    monkeypatch.setenv(f"{_LLM_TIMEOUT}_ANALYSIS", "")

    assert Settings().llm_agent_timeout("analysis") == 7.0


def test_llm_agent_timeout_rejects_bad_agent_value(monkeypatch: pytest.MonkeyPatch) -> None:
    _isolate_env(monkeypatch)
    monkeypatch.setenv(f"{_LLM_TIMEOUT}_ANALYSIS", "soon-xyz")

    with pytest.raises(ValueError, match=f"{_LLM_TIMEOUT}_ANALYSIS") as info:
        Settings().llm_agent_timeout("analysis")

    assert "soon-xyz" not in str(info.value)
