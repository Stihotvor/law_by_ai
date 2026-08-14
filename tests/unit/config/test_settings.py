"""Tests for src/config/settings.py (issue #7)."""

import os

from config.settings import ROOT_DIR, Settings, get_settings, load_env

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
    "POSTGRES_USER",
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
)


def _clear_env(monkeypatch) -> None:
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_defaults_when_no_environment(monkeypatch):
    _clear_env(monkeypatch)
    settings = Settings()

    assert settings.postgres_user == "lawbyai"
    assert settings.postgres_password == "lawbyai"
    assert settings.postgres_db == "lawbyai"
    assert settings.postgres_host == "localhost"
    assert settings.postgres_port == "5432"
    assert settings.postgres_url == "postgresql+psycopg://lawbyai:lawbyai@localhost:5432/lawbyai"
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
    monkeypatch.setenv("POSTGRES_USER", "admin")
    monkeypatch.setenv("POSTGRES_PASSWORD", "p@ss:word")  # needs URL quoting
    monkeypatch.setenv("POSTGRES_DB", "legal")
    monkeypatch.setenv("POSTGRES_HOST", "db.internal")
    monkeypatch.setenv("POSTGRES_PORT", "5433")

    settings = Settings()

    assert (
        settings.postgres_url == "postgresql+psycopg://admin:p%40ss%3Aword@db.internal:5433/legal"
    )


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
