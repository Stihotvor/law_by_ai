"""Tests for the shared ORM models in ``data.models`` (issue #16)."""

from data.models import Base, DocumentStatus, LegalDocument, RejectedDocument
from plugins.relational_db import postgres


def test_legal_document_importable_from_data_models() -> None:
    assert LegalDocument.__name__ == "LegalDocument"


def test_postgres_reexports_same_legal_document() -> None:
    assert postgres.LegalDocument is LegalDocument


def test_legal_document_tablename() -> None:
    assert LegalDocument.__tablename__ == "legal_document"


def test_legal_document_has_status_column() -> None:
    column = LegalDocument.__table__.c.status
    assert column.nullable is False
    assert column.default is not None
    assert column.default.arg == "needs_review"


def test_rejected_document_table_registered() -> None:
    assert RejectedDocument.__tablename__ == "rejected_document"
    assert "rejected_document" in Base.metadata.tables


def test_rejected_document_has_no_tenant_column() -> None:
    assert "tenant_id" not in RejectedDocument.__table__.c


def test_rejected_document_source_url_indexed() -> None:
    names = {ix.name for ix in Base.metadata.tables["rejected_document"].indexes}
    assert "ix_rejected_document_source_url" in names


def test_document_status_values() -> None:
    assert [s.value for s in DocumentStatus] == ["needs_review", "approved"]


def test_status_check_constraint_lists_enum_values() -> None:
    checks = {
        c.name: str(getattr(c, "sqltext", ""))
        for c in Base.metadata.tables["legal_document"].constraints
        if c.name == "ck_legal_document_status"
    }
    assert checks == {"ck_legal_document_status": "status IN ('needs_review', 'approved')"}


def test_postgres_models_share_one_metadata() -> None:
    assert postgres.Base is Base
    assert {"legal_document", "users", "tenants"} <= set(Base.metadata.tables)
