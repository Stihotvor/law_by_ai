"""Celery task ``fetch_document`` through the real Sejm ELI source and PostgreSQL store.

Wiring under test: task -> fetcher -> ``SejmEliSource`` -> ``RestApiStrategy`` ->
parser -> ``PostgreSQLStore``. Only HTTP is fake (``httpx.MockTransport``).

Marked ``integration``: needs a live PostgreSQL. Skipped if it is unreachable.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
from sqlalchemy import create_engine, text

import agents.fetch.sources.sejm_eli  # noqa: F401  (registers the source and mapper)
from agents.fetch.strategies.rest_api import RestApiStrategy
from config.settings import get_settings
from plugins.relational_db.postgres import PostgreSQLStore
from tasks import fetch
from tasks.celery_app import FETCH_DOCUMENT, app

pytestmark = pytest.mark.integration

_SOURCE = "sejm_eli"
_ELI = "DU/2024/1"
_API = "https://api.sejm.gov.pl/eli"
_META_URL = f"{_API}/acts/{_ELI}"
_TEXT_URL = f"{_API}/acts/{_ELI}/text.html"
_TITLE = "Ustawa testowa"
_MARKER = "Art. 1. Znacznik-testowy-sejm-7f3c."
_META = {
    "ELI": _ELI,
    "title": _TITLE,
    "type": "Ustawa",
    "textHTML": True,
    "textPDF": False,
    "promulgation": "2024-01-02",
}
_HTML = f"<html><body><h1>{_TITLE}</h1><p>{_MARKER}</p></body></html>"
_TENANT = f"tenant-{uuid.uuid4().hex}"


def _make_handler(requests: list[httpx.Request]) -> Callable[[httpx.Request], httpx.Response]:
    """Return a handler that logs each request and serves the Sejm act."""

    def handler(request: httpx.Request) -> httpx.Response:
        """Serve the meta and text of DU/2024/1; answer 404 to anything else."""
        requests.append(request)
        url = str(request.url)
        if request.method == "GET" and url == _META_URL:
            return httpx.Response(
                200,
                content=json.dumps(_META).encode(),
                headers={"content-type": "application/json"},
            )
        if request.method == "GET" and url == _TEXT_URL:
            return httpx.Response(
                200,
                content=_HTML.encode("utf-8"),
                headers={"content-type": "text/html; charset=utf-8"},
            )
        return httpx.Response(404)

    return handler


class _NoThrottle:
    """Throttle that never waits."""

    def wait(self) -> None:
        """Do not wait."""
        pass


def _can_connect(url: str) -> bool:
    """Return True when the database at the URL answers a query."""
    try:
        engine = create_engine(url, future=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


def _rows(source_url: str) -> list[dict[str, Any]]:
    """Return the test tenant's ``legal_document`` rows with *source_url*."""
    engine = create_engine(get_settings().postgres_url, future=True)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, source_url, source, title, content, status, tenant_id, metadata "
                "FROM legal_document WHERE source_url = :u AND tenant_id = :t"
            ),
            {"u": source_url, "t": _TENANT},
        ).all()
    engine.dispose()
    return [dict(r._mapping) for r in rows]


def _cleanup(db_url: str) -> None:
    """Delete the test tenant's rows for the Sejm URLs."""
    engine = create_engine(db_url, future=True)
    with engine.begin() as conn:
        for url in (_TEXT_URL, _META_URL):
            conn.execute(
                text("DELETE FROM legal_document WHERE source_url = :u AND tenant_id = :t"),
                {"u": url, "t": _TENANT},
            )
    engine.dispose()


@pytest.fixture(autouse=True)
def requests(monkeypatch: pytest.MonkeyPatch) -> list[httpx.Request]:
    """Route the real ``RestApiStrategy`` client through a mock transport; return its log."""
    log: list[httpx.Request] = []
    handler = _make_handler(log)
    original = RestApiStrategy._new_client

    def new_client(self: RestApiStrategy) -> httpx.Client:
        """Build the real client with the mock transport."""
        self._transport = httpx.MockTransport(handler)
        return original(self)

    monkeypatch.setattr(RestApiStrategy, "_new_client", new_client)
    monkeypatch.setattr(
        "agents.fetch.strategies._hosts._getaddrinfo",
        lambda *a, **kw: [(2, 1, 6, "", ("8.8.8.8", 0))],
    )
    monkeypatch.setattr("agents.fetch.sources.sejm_eli._THROTTLE", _NoThrottle())
    return log


@pytest.fixture(autouse=True)
def eager() -> Iterator[None]:
    """Run Celery tasks in process and raise their errors."""
    old = (app.conf.task_always_eager, app.conf.task_eager_propagates)
    app.conf.task_always_eager = True
    app.conf.task_eager_propagates = True
    yield
    app.conf.task_always_eager, app.conf.task_eager_propagates = old


@pytest.fixture
def clean_db() -> Iterator[None]:
    """Remove the test tenant's rows for the Sejm URLs before and after the test."""
    url = get_settings().postgres_url
    if not _can_connect(url):
        pytest.skip("PostgreSQL unavailable")
    _cleanup(url)
    yield
    _cleanup(url)


@pytest.fixture
def store(clean_db: None, monkeypatch: pytest.MonkeyPatch) -> Iterator[PostgreSQLStore]:
    """Real store that the task gets from ``_make_store``."""
    s = PostgreSQLStore()
    s.initialize()
    original = fetch._make_store
    original.cache_clear()
    monkeypatch.setattr(fetch, "_make_store", lambda: s)
    try:
        yield s
    finally:
        try:
            s.close()
        finally:
            original.cache_clear()


def _run(external_id: str) -> Any:
    """Run the task for *external_id* as the test tenant; return its result."""
    return app.tasks[FETCH_DOCUMENT].delay(_SOURCE, external_id, tenant_id=_TENANT).get()


def test_task_fetches_and_saves_sejm_act(
    store: PostgreSQLStore, requests: list[httpx.Request]
) -> None:
    """A valid id is fetched over mocked HTTP and saved with the make_ref URL."""
    expected_url = RestApiStrategy(_API).make_ref(_SOURCE, _ELI).url
    assert expected_url == "https://api.sejm.gov.pl/eli/acts/DU/2024/1/text.html"

    result = _run(_ELI)

    assert result["status"] == "saved"
    assert result["source_url"] == expected_url
    rows = _rows(expected_url)
    assert len(rows) == 1
    row = rows[0]
    assert row["id"] == result["document_id"]
    assert row["source"] == _SOURCE
    assert row["title"] == _TITLE
    assert _MARKER in row["content"]
    assert row["status"] == "needs_review"
    assert row["tenant_id"] == _TENANT
    assert row["metadata"]["eli"] == _ELI
    assert [str(r.url) for r in requests] == [_META_URL, _TEXT_URL]


def test_task_rejects_url_as_id_without_http(
    store: PostgreSQLStore, requests: list[httpx.Request]
) -> None:
    """A URL as the id gives status invalid and sends no request."""
    result = _run(_META_URL)

    assert result == {"status": "invalid", "external_id": _META_URL}
    assert requests == []
    assert _rows(_TEXT_URL) == []
    assert _rows(_META_URL) == []
