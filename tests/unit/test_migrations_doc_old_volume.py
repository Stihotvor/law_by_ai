"""Static checks for the old-volume SQL block in docs/migrations.md (rls-201 T5).

The live run of the block is in tests/integration/test_old_volume_upgrade.py.
"""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOC = ROOT / "docs" / "migrations.md"
SCRIPT = ROOT / "docker" / "initdb" / "00-roles.sh"
HEADING = "## Upgrade an old volume"
OWNER_CHANGES = (
    "ALTER TABLE tenants OWNER TO lawbyai_owner;",
    "ALTER TABLE users OWNER TO lawbyai_owner;",
    "ALTER TABLE legal_document OWNER TO lawbyai_owner;",
    "ALTER TABLE rejected_document OWNER TO lawbyai_owner;",
    "ALTER TABLE alembic_version OWNER TO lawbyai_owner;",
    "ALTER SEQUENCE rejected_document_id_seq OWNER TO lawbyai_owner;",
    "ALTER FUNCTION users_bump_session_version() OWNER TO lawbyai_owner;",
)


def old_volume_sql() -> str:
    """Return the first sql code block after the old-volume heading."""
    text = DOC.read_text()
    assert HEADING in text, "the old-volume section is missing"
    section = text.split(HEADING, 1)[1]
    match = re.search(r"```sql\n(.*?)```", section, re.DOTALL)
    assert match, "no sql block in the old-volume section"
    return match.group(1)


def _flat(sql: str) -> str:
    """Return the SQL without comment lines and with whitespace collapsed."""
    lines = [line for line in sql.splitlines() if not line.lstrip().startswith("--")]
    return " ".join(" ".join(lines).split())


def _role_statements(sql: str) -> list[str]:
    """Return the CREATE ROLE and GRANT statements in order."""
    return re.findall(r"(?:CREATE ROLE|GRANT) [^;]*;", _flat(sql))


def _script_sql() -> str:
    """Return the SQL heredoc of the init script."""
    return SCRIPT.read_text().split("<<'SQL'", 1)[1]


def test_block_lists_every_owner_change() -> None:
    """Scenario: The block lists every owner change."""
    flat = _flat(old_volume_sql())
    for stmt in OWNER_CHANGES:
        assert stmt in flat, stmt


def test_sequence_change_follows_its_table() -> None:
    """The sequence belongs to its table, so its table must change owner first."""
    flat = _flat(old_volume_sql())
    table = flat.index("ALTER TABLE rejected_document OWNER")
    assert table < flat.index("ALTER SEQUENCE rejected_document_id_seq OWNER")


def test_block_matches_the_init_script() -> None:
    """Scenario: The block matches the init script."""
    doc = _role_statements(old_volume_sql())
    script = _role_statements(_script_sql())
    assert len(script) == 6
    assert doc == script
    assert "GRANT CREATE, USAGE ON SCHEMA public TO lawbyai_auth;" in doc


def test_block_reads_passwords_from_env() -> None:
    """The block has no password text. psql reads the passwords from env."""
    sql = old_volume_sql()
    assert not re.search(r"PASSWORD\s+'", sql, re.IGNORECASE)
    assert "\\getenv owner_password LAWBYAI_OWNER_PASSWORD" in sql
    assert "\\getenv app_password LAWBYAI_APP_PASSWORD" in sql


def test_block_runs_in_one_transaction() -> None:
    """The block changes all or nothing."""
    flat = _flat(old_volume_sql())
    assert flat.count("BEGIN;") == 1
    assert flat.rstrip().endswith("COMMIT;")


def test_section_explains_the_order_and_reassign_owned() -> None:
    """The section names the superuser, the owner URL and why REASSIGN OWNED fails."""
    section = DOC.read_text().split(HEADING, 1)[1]
    assert "REASSIGN OWNED" in section
    assert "psql -v ON_ERROR_STOP=1" in section
    assert "bootstrap superuser" in section
    assert "uv run alembic upgrade head" in section
    assert "lawbyai_owner" in section
