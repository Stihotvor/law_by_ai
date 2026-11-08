"""Tests for the shared ORM models in ``data.models`` (issue #16)."""

from data.models import Base, LegalDocument
from plugins.relational_db import postgres


def test_legal_document_importable_from_data_models() -> None:
    assert LegalDocument.__name__ == "LegalDocument"


def test_postgres_reexports_same_legal_document() -> None:
    assert postgres.LegalDocument is LegalDocument


def test_legal_document_tablename() -> None:
    assert LegalDocument.__tablename__ == "legal_document"


def test_postgres_models_share_one_metadata() -> None:
    assert postgres.Base is Base
    assert {"legal_document", "users", "tenants"} <= set(Base.metadata.tables)
