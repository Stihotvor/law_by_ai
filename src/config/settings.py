"""Environment-based application configuration (issue #7).

Loads ``.env`` from the repository root (if present) and exposes typed
settings derived from environment variables with sensible defaults.

Environment variable scheme — consistent *component prefix* + *subject*,
with connection strings ending in ``_URL``:

=====================  =====================================  ================================
Variable               Purpose                                Default
=====================  =====================================  ================================
``POSTGRES_URL``       Full SQLAlchemy URL                    assembled from ``POSTGRES_*``
``POSTGRES_USER``      PostgreSQL user                        ``lawbyai``
``POSTGRES_PASSWORD``  PostgreSQL password                    ``lawbyai``
``POSTGRES_DB``        PostgreSQL database name               ``lawbyai``
``POSTGRES_HOST``      PostgreSQL host                        ``localhost``
``POSTGRES_PORT``      PostgreSQL port                        ``5432``
``REDIS_URL``          Full Redis URL                         assembled from ``REDIS_*``
``REDIS_USER``         Redis user                             *(empty)*
``REDIS_PASSWORD``     Redis password                         *(empty)*
``REDIS_HOST``         Redis host                             ``localhost``
``REDIS_PORT``         Redis port                             ``6379``
``REDIS_DB``           Redis database number                  ``0``
``CELERY_BROKER_URL``  Celery broker URL                      ``REDIS_URL``
``CELERY_RESULT_BACKEND_URL``  Celery result backend URL      ``REDIS_URL``
``APP_PORT``           Streamlit port                         ``8501``
``APP_NAME``           Application name                       ``law-by-ai``
``LLM_BASE_URL``          OpenAI-compatible LLM/SLM base URL      ``http://localhost:11434/v1``
``LLM_API_KEY``           LLM API key (empty for local)           ``(empty)``
``LLM_MODEL``             default model (all agents unless overridden)  ``(empty)``
``LLM_MODEL_<AGENT>``     per-agent model override (``LLM_MODEL_LEGAL_RESEARCH``)  ``(LLM_MODEL)``
``EMBEDDING_BASE_URL``    embedding provider base URL             ``http://localhost:11434/v1``
``EMBEDDING_API_KEY``     embedding API key (empty for local)     ``(empty)``
``EMBEDDING_MODEL``       embedding model name                    ``nomic-embed-text``
``RERANK_BASE_URL``       reranking provider base URL             ``https://api.cohere.com/v1``
``RERANK_API_KEY``        reranking API key                       ``(empty)``
``RERANK_MODEL``          reranking model name                    ``rerank-v3.5``
``OCR_ENABLED``           send documents to the OCR provider      ``false``
``MISTRAL_API_KEY``       Mistral API key (OCR)                   ``(empty)``
``MISTRAL_BASE_URL``      Mistral API base URL                    ``https://api.mistral.ai/v1``
``MISTRAL_OCR_MODEL``     Mistral OCR model name                  ``mistral-ocr-latest``
``OCR_TIMEOUT``           total seconds per OCR request           ``120.0``
``OCR_MAX_BYTES``         max OCR input size in bytes             ``20971520``
``FETCH_HTTP_TIMEOUT``    total seconds per fetch HTTP request    ``10.0``
``FETCH_TOTAL_TIMEOUT``   total seconds to read one body          ``60.0``
``FETCH_MAX_BYTES``       max fetched body size in bytes          ``52428800``
``MINIO_ENDPOINT``        MinIO ``host:port`` (no scheme)         ``localhost:9000``
``MINIO_ACCESS_KEY``      MinIO access key                        *(empty)*
``MINIO_SECRET_KEY``      MinIO secret key                        *(empty)*
``MINIO_BUCKET``          MinIO bucket for legal documents        ``legal-documents``
``MINIO_SECURE``          use TLS for MinIO                       ``true``
``TAVILY_API_KEY``        Tavily API key                          *(empty)*
``TAVILY_TIMEOUT``        seconds per Tavily request              ``60.0``
``TAVILY_MAX_PAGES``      pages per Tavily map call               ``20``
``SEJM_MIN_INTERVAL``     seconds between Sejm requests           ``0.5``
=====================  =====================================  ================================

Usage::

    from config.settings import get_settings

    settings = get_settings()
    print(settings.postgres_url)
    print(settings.celery_broker_url)
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv

# Repository root: <repo>/src/config/settings.py -> <repo>/
ROOT_DIR = Path(__file__).resolve().parents[2]


def load_env(env_file: str | Path | None = None, *, override: bool = False) -> None:
    """Load a ``.env`` file into the environment if it exists.

    Defaults to ``<repo root>/.env``. Existing environment variables take
    precedence unless ``override=True``.
    """
    load_dotenv(dotenv_path=env_file or ROOT_DIR / ".env", override=override)


def _positive[N: (int, float)](name: str, default: str, kind: type[N]) -> N:
    """Read env ``name`` as a positive, finite number or raise ``ValueError``."""
    raw = os.getenv(name, default)
    try:
        value = kind(raw)
    except ValueError:
        raise ValueError(f"{name} must be a number, got {raw!r}") from None
    if not 0 < value < float("inf"):
        raise ValueError(f"{name} must be positive and finite, got {raw!r}")
    return value


class Settings:
    """Typed access to environment-based configuration.

    Values are read lazily from ``os.environ`` on each access, so a single
    :class:`Settings` instance always reflects the current environment.
    """

    def __init__(self) -> None:
        load_env()

    # --- PostgreSQL ----------------------------------------------------------
    @property
    def postgres_user(self) -> str:
        return os.getenv("POSTGRES_USER", "lawbyai")

    @property
    def postgres_password(self) -> str:
        return os.getenv("POSTGRES_PASSWORD", "lawbyai")

    @property
    def postgres_db(self) -> str:
        return os.getenv("POSTGRES_DB", "lawbyai")

    @property
    def postgres_host(self) -> str:
        return os.getenv("POSTGRES_HOST", "localhost")

    @property
    def postgres_port(self) -> str:
        return os.getenv("POSTGRES_PORT", "5432")

    @property
    def postgres_url(self) -> str:
        """Full SQLAlchemy URL.

        ``POSTGRES_URL`` wins when set; otherwise the URL is assembled from
        ``POSTGRES_*`` with URL-quoted credentials.
        """
        if url := os.getenv("POSTGRES_URL"):
            return url
        user = quote(self.postgres_user, safe="")
        password = quote(self.postgres_password, safe="")
        return f"postgresql+psycopg://{user}:{password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

    # --- Redis / Celery ------------------------------------------------------
    @property
    def redis_user(self) -> str:
        return os.getenv("REDIS_USER", "")

    @property
    def redis_password(self) -> str:
        return os.getenv("REDIS_PASSWORD", "")

    @property
    def redis_host(self) -> str:
        return os.getenv("REDIS_HOST", "localhost")

    @property
    def redis_port(self) -> str:
        return os.getenv("REDIS_PORT", "6379")

    @property
    def redis_db(self) -> str:
        return os.getenv("REDIS_DB", "0")

    @property
    def redis_url(self) -> str:
        """Full Redis URL.

        ``REDIS_URL`` wins when set; otherwise the URL is assembled from
        ``REDIS_*`` with URL-quoted credentials.
        """
        if url := os.getenv("REDIS_URL"):
            return url
        user = quote(self.redis_user, safe="")
        password = quote(self.redis_password, safe="")
        auth = f"{user}:{password}@" if user or password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    @property
    def celery_broker_url(self) -> str:
        """Celery broker; falls back to ``REDIS_URL``."""
        return os.getenv("CELERY_BROKER_URL", self.redis_url)

    @property
    def celery_result_backend_url(self) -> str:
        """Celery result backend; falls back to ``REDIS_URL``."""
        return os.getenv("CELERY_RESULT_BACKEND_URL", self.redis_url)

    # --- Application ----------------------------------------------------------
    @property
    def app_name(self) -> str:
        return os.getenv("APP_NAME", "law-by-ai")

    @property
    def app_port(self) -> int:
        """Streamlit port (used by the docker-compose ``app`` service)."""
        return int(os.getenv("APP_PORT", "8501"))

    # --- LLM / embeddings / reranking (ADR-0014) ---------------------------
    @property
    def llm_base_url(self) -> str:
        """Base URL of the OpenAI-compatible LLM/SLM endpoint."""
        return os.getenv("LLM_BASE_URL", "http://localhost:11434/v1")

    @property
    def llm_api_key(self) -> str:
        """API key for the LLM endpoint (empty for local SLMs)."""
        return os.getenv("LLM_API_KEY", "")

    @property
    def llm_model(self) -> str:
        """Default LLM/SLM model name; per-agent ``LLM_MODEL_<AGENT>``
        variables override this for individual agents."""
        return os.getenv("LLM_MODEL", "")

    @property
    def llm_model_document_fetcher(self) -> str:
        """Model for the DocumentFetcher agent (falls back to ``LLM_MODEL``)."""
        return os.getenv("LLM_MODEL_DOCUMENT_FETCHER", self.llm_model)

    @property
    def llm_model_document_processor(self) -> str:
        """Model for the DocumentProcessor agent (falls back to ``LLM_MODEL``)."""
        return os.getenv("LLM_MODEL_DOCUMENT_PROCESSOR", self.llm_model)

    @property
    def llm_model_legal_research(self) -> str:
        """Model for the LegalResearch agent (falls back to ``LLM_MODEL``)."""
        return os.getenv("LLM_MODEL_LEGAL_RESEARCH", self.llm_model)

    @property
    def llm_model_change_tracker(self) -> str:
        """Model for the ChangeTracker agent (falls back to ``LLM_MODEL``)."""
        return os.getenv("LLM_MODEL_CHANGE_TRACKER", self.llm_model)

    @property
    def llm_model_knowledge_graph(self) -> str:
        """Model for the KnowledgeGraph agent (falls back to ``LLM_MODEL``)."""
        return os.getenv("LLM_MODEL_KNOWLEDGE_GRAPH", self.llm_model)

    @property
    def llm_model_analysis(self) -> str:
        """Model for the Analysis agent (falls back to ``LLM_MODEL``)."""
        return os.getenv("LLM_MODEL_ANALYSIS", self.llm_model)

    @property
    def llm_model_bureaucracy_assistant(self) -> str:
        """Model for the BureaucracyAssistant agent (falls back to ``LLM_MODEL``)."""
        return os.getenv("LLM_MODEL_BUREAUCRACY_ASSISTANT", self.llm_model)

    @property
    def embedding_base_url(self) -> str:
        """Base URL of the embedding provider (may differ from the LLM)."""
        return os.getenv("EMBEDDING_BASE_URL", "http://localhost:11434/v1")

    @property
    def embedding_api_key(self) -> str:
        """API key for the embedding provider (empty for local endpoints)."""
        return os.getenv("EMBEDDING_API_KEY", "")

    @property
    def embedding_model(self) -> str:
        """Embedding model name (eval-selected, ADR-0009)."""
        return os.getenv("EMBEDDING_MODEL", "nomic-embed-text")

    @property
    def rerank_base_url(self) -> str:
        """Base URL of the reranking provider (Cohere by default)."""
        return os.getenv("RERANK_BASE_URL", "https://api.cohere.com/v1")

    @property
    def rerank_api_key(self) -> str:
        """API key for the reranking provider."""
        return os.getenv("RERANK_API_KEY", "")

    @property
    def rerank_model(self) -> str:
        """Reranking model name (Cohere by default)."""
        return os.getenv("RERANK_MODEL", "rerank-v3.5")

    # --- OCR ---------------------------------------------------------------
    @property
    def ocr_enabled(self) -> bool:
        """Whether document content may be sent to the OCR provider."""
        return os.getenv("OCR_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}

    @property
    def mistral_api_key(self) -> str:
        """API key for the Mistral OCR provider."""
        return os.getenv("MISTRAL_API_KEY", "")

    @property
    def mistral_base_url(self) -> str:
        """Base URL of the Mistral API."""
        return os.getenv("MISTRAL_BASE_URL", "https://api.mistral.ai/v1")

    @property
    def mistral_ocr_model(self) -> str:
        """Mistral OCR model name."""
        return os.getenv("MISTRAL_OCR_MODEL", "mistral-ocr-latest")

    @property
    def ocr_timeout(self) -> float:
        """Total timeout in seconds for one OCR request."""
        return _positive("OCR_TIMEOUT", "120.0", float)

    @property
    def ocr_max_bytes(self) -> int:
        """Maximum size in bytes of one OCR input before base64."""
        return _positive("OCR_MAX_BYTES", "20971520", int)

    # --- Document fetch ------------------------------------------------------
    @property
    def fetch_http_timeout(self) -> float:
        """Total timeout in seconds for one fetch HTTP request."""
        return _positive("FETCH_HTTP_TIMEOUT", "10.0", float)

    @property
    def fetch_total_timeout(self) -> float:
        """Wall-clock seconds allowed for reading one response body."""
        return _positive("FETCH_TOTAL_TIMEOUT", "60.0", float)

    @property
    def fetch_max_bytes(self) -> int:
        """Maximum size in bytes of one fetched document body."""
        return _positive("FETCH_MAX_BYTES", "52428800", int)

    @property
    def minio_endpoint(self) -> str:
        """MinIO endpoint as ``host:port`` without a scheme."""
        return os.getenv("MINIO_ENDPOINT", "localhost:9000")

    @property
    def minio_access_key(self) -> str:
        """MinIO access key (no default secret)."""
        return os.getenv("MINIO_ACCESS_KEY", "")

    @property
    def minio_secret_key(self) -> str:
        """MinIO secret key (no default secret)."""
        return os.getenv("MINIO_SECRET_KEY", "")

    @property
    def minio_bucket(self) -> str:
        """MinIO bucket that holds legal documents."""
        return os.getenv("MINIO_BUCKET", "legal-documents")

    @property
    def minio_secure(self) -> bool:
        """Whether to use TLS when talking to MinIO."""
        return os.getenv("MINIO_SECURE", "true").strip().lower() in {"1", "true", "yes", "on"}

    # --- Tavily and source politeness ---------------------------------------
    @property
    def tavily_api_key(self) -> str:
        """Tavily API key (secret, env only, empty when unset)."""
        return os.getenv("TAVILY_API_KEY", "")

    @property
    def tavily_timeout(self) -> float:
        """Seconds allowed for one Tavily request."""
        return _positive("TAVILY_TIMEOUT", "60.0", float)

    @property
    def tavily_max_pages(self) -> int:
        """Maximum pages one Tavily map call may return."""
        return _positive("TAVILY_MAX_PAGES", "20", int)

    @property
    def sejm_min_interval(self) -> float:
        """Minimum seconds between two outbound Sejm requests."""
        return _positive("SEJM_MIN_INTERVAL", "0.5", float)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide :class:`Settings` instance."""
    return Settings()


__all__ = [
    "ROOT_DIR",
    "Settings",
    "get_settings",
    "load_env",
]
