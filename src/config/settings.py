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
        return f"postgresql://{user}:{password}@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"

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
