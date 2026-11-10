"""Smoke: a queued ``fetch_document`` reaches ``legal_document`` through broker and worker.

Runs only with ``SMOKE_WORKER=1`` against the worker from docker/docker-compose.smoke.yml,
which serves the Sejm ELI API from tests/smoke/fixtures. See CONTRIBUTING.md.
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, create_engine, text

from agents.fetch.document_fetcher import DocumentFetcherAgent
from config.settings import get_settings
from tasks.celery_app import FETCH_DOCUMENT, app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(os.getenv("SMOKE_WORKER") != "1", reason="needs the smoke worker"),
]

SOURCE = "sejm_eli"
EXTERNAL_ID = "DU/2024/1"
TIMEOUT_S = 30.0
STEP_S = 0.5


def _expected_url() -> str:
    """Return the source_url the task saves: the canonical ref URL."""
    with DocumentFetcherAgent() as agent:
        return agent.make_ref(SOURCE, EXTERNAL_ID).url


def _row_saved(engine: Engine, source_url: str, since: datetime) -> bool:
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT 1 FROM legal_document WHERE source_url = :u AND last_updated >= :t LIMIT 1"
            ),
            {"u": source_url, "t": since},
        ).first()
    return row is not None


def test_queued_fetch_saves_a_legal_document_row() -> None:
    source_url = _expected_url()
    engine = create_engine(get_settings().postgres_url, future=True)
    t0 = datetime.now(UTC)
    result = app.send_task(FETCH_DOCUMENT, args=[SOURCE, EXTERNAL_ID])
    deadline = time.monotonic() + TIMEOUT_S
    try:
        while time.monotonic() < deadline:
            if _row_saved(engine, source_url, t0):
                return
            time.sleep(STEP_S)
    finally:
        engine.dispose()
    pytest.fail(f"no legal_document row for {source_url} in {TIMEOUT_S} s; task {result.state}")
