"""Celery task: fetch one document by its source id, parse it and save it to the store.

The fetcher builds the canonical document URL from the source and the id.
An id the source does not accept gives the ``invalid`` status.
A source that cannot build a ref from an id gives the ``unsupported`` status;
the task then fetches and saves nothing.

This module wires the fetcher to the store; ``agents.fetch`` never imports the store.
"""

from __future__ import annotations

import logging
from typing import Any

from celery.signals import worker_process_shutdown

from agents.fetch.contracts import DocumentRef, FetchedDocument
from agents.fetch.document_fetcher import DocumentFetcherAgent, RejectionChecker
from agents.fetch.errors import DocumentRejectedError, InvalidReferenceError
from data.models import DocumentStatus
from plugins.relational_db.postgres import PostgreSQLStore
from tasks.celery_app import FETCH_DOCUMENT, app

_log = logging.getLogger(__name__)


_store: PostgreSQLStore | None = None


def _make_store() -> PostgreSQLStore:
    """Return this worker process's store, built on first call."""
    # One store per worker process. Workers never migrate: the init service runs
    # `alembic upgrade head`, and the store only checks the schema head.
    # A failed build leaves _store as None, so the next task tries again.
    # Call only inside a task: never at import time or in the parent (pre-fork) process.
    global _store
    if _store is None:
        _store = PostgreSQLStore()
    return _store


@worker_process_shutdown.connect
def _close_store(**_: object) -> None:
    """Close this worker process's store at child exit; build nothing if there is none."""
    global _store
    if _store is None:
        return
    try:
        _store.close()
    except Exception:
        _log.warning("store close failed", exc_info=True)
    finally:
        _store = None


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


@app.task(name=FETCH_DOCUMENT)
def fetch_document(source: str, external_id: str, tenant_id: str | None = None) -> dict[str, str]:
    """Fetch *external_id* from *source* and save it; skip it if an admin rejected it."""
    store = _make_store()
    agent = _make_agent(store)
    try:
        try:
            ref = agent.make_ref(source, external_id)
        except InvalidReferenceError:
            return {"status": "invalid", "external_id": external_id}
        except NotImplementedError:
            return {"status": "unsupported", "external_id": external_id}
        try:
            fetched = agent.fetch_document(source, ref, tenant_id=tenant_id)
        except DocumentRejectedError:
            return {"status": "skipped", "source_url": ref.url}
        text = agent.parse(fetched.content, ref.url, fetched.content_type)
    finally:
        _close_quietly(agent)
    document_id = store.save_document(_to_document(ref, fetched, text), tenant_id)
    return {"status": "saved", "document_id": document_id, "source_url": ref.url}
