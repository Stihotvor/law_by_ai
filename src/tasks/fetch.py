"""Celery task: fetch one document, parse it and save it to the store (issue #11).

This module wires the fetcher to the store; ``agents.fetch`` never imports the store.
"""

from __future__ import annotations

import functools
import logging
from typing import Any

from agents.fetch.contracts import DocumentRef, FetchedDocument
from agents.fetch.document_fetcher import DocumentFetcherAgent, RejectionChecker
from agents.fetch.errors import DocumentRejectedError
from data.models import DocumentStatus
from plugins.relational_db.postgres import PostgreSQLStore
from tasks.celery_app import app

_log = logging.getLogger(__name__)


@functools.cache
def _make_store() -> PostgreSQLStore:
    """Return this worker process's store, built on first call."""
    # One store per worker process: the store runs Alembic migrations on first use,
    # so a new store per task would migrate on every task run.
    # Call only inside a task: never at import time or in the parent (pre-fork) process.
    return PostgreSQLStore()


def _make_agent(rejection: RejectionChecker) -> DocumentFetcherAgent:
    """Build a fetcher agent that checks *rejection* before each fetch."""
    return DocumentFetcherAgent(rejection=rejection)


def _close_quietly(agent: DocumentFetcherAgent) -> None:
    """Close *agent*; log a close error as a warning instead of raising it."""
    try:
        agent.close()
    except Exception:
        _log.warning("fetch agent close failed", exc_info=True)


def _to_document(ref: DocumentRef, fetched: FetchedDocument, text: str) -> dict[str, Any]:
    """Build the dict that ``PostgreSQLStore.save_document`` stores."""
    return {
        "title": fetched.meta.title,
        "content": text,
        "source": ref.source,
        "source_url": ref.url,
        "last_updated": fetched.fetched_at,
        "metadata": fetched.meta.extra,
        "is_processed": False,
        "status": DocumentStatus.NEEDS_REVIEW.value,
    }


@app.task(name="fetch_document")
def fetch_document(source: str, url: str, tenant_id: str | None = None) -> dict[str, str]:
    """Fetch *url* from *source* and save it; skip it if an admin rejected it."""
    store = _make_store()
    ref = DocumentRef(source=source, external_id=url, url=url)
    agent = _make_agent(store)
    try:
        try:
            fetched = agent.fetch_document(source, ref, tenant_id=tenant_id)
        except DocumentRejectedError:
            return {"status": "skipped", "source_url": url}
        text = agent.parse(fetched.content, url, fetched.content_type)
    finally:
        _close_quietly(agent)
    document_id = store.save_document(_to_document(ref, fetched, text), tenant_id)
    return {"status": "saved", "document_id": document_id, "source_url": url}
