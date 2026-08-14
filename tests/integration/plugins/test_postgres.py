"""Integration tests for the PostgreSQL store (issue #9, ADR-0014).

Marked ``integration`` because they need a live PostgreSQL instance. They are
excluded from the plain-``uv`` unit run (``pytest -m "not integration"``) and
run against the live stack via the docker ``test`` profile. Locally they are
skipped if ``POSTGRES_URL`` (or its defaults) is unreachable.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest

from config.settings import get_settings
from plugins.relational_db.postgres import PostgreSQLStore

pytestmark = [
    pytest.mark.integration,
    pytest.mark.usefixtures("_postgres_available"),
]


@pytest.fixture
def plugin(tmp_path):
    """Fresh store whose schema is brought up by migrations on initialize()."""
    from sqlalchemy import create_engine, text

    p = PostgreSQLStore()
    p.initialize()
    engine = create_engine(get_settings().postgres_url, future=True)
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE legal_document"))
    engine.dispose()
    yield p
    p.close()


@pytest.fixture
def _postgres_available():
    """Skip the whole module if PostgreSQL is unreachable."""
    if not _can_connect(get_settings().postgres_url):
        pytest.skip("PostgreSQL unavailable", allow_module_level=True)


def _can_connect(url: str) -> bool:
    """Best-effort probe; never raises (tests skip instead)."""
    from sqlalchemy import create_engine, text

    try:
        engine = create_engine(url, future=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


def test_store_initializes(tmp_path):
    p = PostgreSQLStore()
    p.initialize()
    assert p._initialized is True
    p.close()


def test_save_and_get_roundtrip(plugin, _make_document: Callable):
    doc = _make_document(title="Konstytucja RP", content="Krajowe źródło prawa.")
    doc_id = plugin.save_document(doc)

    fetched = plugin.get_document(doc_id)
    assert fetched is not None
    assert fetched["id"] == doc_id
    assert fetched["title"] == "Konstytucja RP"
    assert fetched["content"] == "Krajowe źródło prawa."
    assert fetched["source"] == doc["source"]
    assert fetched["source_url"] == doc["source_url"]
    assert fetched["metadata"] == doc["metadata"]
    assert fetched["is_processed"] is False
    assert fetched["tenant_id"] == "tenant-7"


def test_get_missing_returns_none(plugin):
    assert plugin.get_document("00000000-0000-0000-0000-000000000000") is None


def test_save_upserts_on_conflict(plugin, _make_document: Callable):
    doc = _make_document(title="Ustawa o VAT", content="Wersja pierwsza")
    doc_id = plugin.save_document(doc)

    doc["content"] = "Wersja druga"
    doc["is_processed"] = True
    plugin.save_document(doc)  # same id -> update

    fetched = plugin.get_document(doc_id)
    assert fetched["content"] == "Wersja druga"
    assert fetched["is_processed"] is True


@pytest.fixture
def _make_document() -> Callable:
    """Factory for a minimal document dict (sans id; plugin generates one)."""

    def _factory(**overrides):
        base = {
            "title": "Untitled",
            "content": "Body",
            "source": "test",
            "source_url": "https://example.invalid/",
            "metadata": {"pages": 1, "language": "pl"},
            "is_processed": False,
            "tenant_id": "tenant-7",
        }
        return {**base, **overrides}

    return _factory


def test_search_ilike_matches_title_and_content(plugin, _make_document: Callable):
    plugin.save_document(_make_document(title="Kodeks cywilny", content="artykuły"))
    plugin.save_document(_make_document(title="Inny akt", content="Kodeks karny"))
    plugin.save_document(_make_document(title="Janusz", content="Nie dotyczy"))

    hits = plugin.search_documents("kodeks", limit=10)
    titles = sorted(h["title"] for h in hits)
    assert titles == ["Inny akt", "Kodeks cywilny"]


def test_search_limit_truncates(plugin, _make_document: Callable):
    for i in range(5):
        plugin.save_document(_make_document(title=f"Temat {i}", content="shared body"))
    hits = plugin.search_documents("shared", limit=3)
    assert len(hits) == 3


def test_get_recent_changes_orders_desc(plugin, _make_document: Callable):
    plugin.save_document(_make_document(title="Old", last_updated="2024-01-01T00:00:00+00:00"))
    plugin.save_document(_make_document(title="New", last_updated="2025-06-06T12:00:00+00:00"))

    changes = plugin.get_recent_changes()
    titles = [c["title"] for c in changes]
    assert titles.index("New") < titles.index("Old")


def test_delete_removes_document(plugin, _make_document: Callable):
    doc_id = plugin.save_document(_make_document())
    assert plugin.get_document(doc_id) is not None

    plugin.delete_document(doc_id)
    assert plugin.get_document(doc_id) is None


def test_delete_missing_is_noop(plugin):
    plugin.delete_document("00000000-0000-0000-0000-000000000000")  # must not raise


def test_update_merge_fields(plugin, _make_document: Callable):
    doc_id = plugin.save_document(_make_document(title="Pierwotny", is_processed=False))
    plugin.update_document(doc_id, {"title": "Zaktualizowany", "is_processed": True})

    fetched = plugin.get_document(doc_id)
    assert fetched["title"] == "Zaktualizowany"
    assert fetched["is_processed"] is True
    # field not in update dict stays unchanged
    assert fetched["source"] == "test"


def test_update_missing_raises_keyerror(plugin):
    with pytest.raises(KeyError):
        plugin.update_document("00000000-0000-0000-0000-000000000000", {"title": "x"})


def test_store_reinitializes_idempotently(plugin):
    """initialize() runs migrations again without error (already at head)."""
    plugin.initialize()
    assert plugin._initialized is True


def test_store_visible_via_platform_env(_make_document: Callable):
    """Sanity: POSTGRES_URL (or its parts) drives the connection string."""
    url = get_settings().postgres_url
    assert url.startswith("postgresql")
