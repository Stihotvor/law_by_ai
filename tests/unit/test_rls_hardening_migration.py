"""Unit checks for the rls-201 revision (T3): role checks, NO FORCE window, policies.

The revision runs against a fake ``op`` and a fake connection that answers the
catalog queries, so the tests see every SQL statement in order. The live checks
(row counts as ``lawbyai_app``, WITH CHECK failures) are in the T8 integration tests.
"""

import importlib.util
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

VERSIONS = Path(__file__).resolve().parents[2] / "migrations" / "versions"
REVISION_FILE = next(VERSIONS.glob("*_harden_rls_tenant_only_policies.py"))
TENANT = "nullif(current_setting('app.current_tenant', true), '')"
ALL_ROLES = {"lawbyai_owner", "lawbyai_app", "lawbyai_auth"}
TABLES = ("tenants", "users", "legal_document", "rejected_document", "alembic_version")


def _load() -> ModuleType:
    """Import the revision file as a module."""
    spec = importlib.util.spec_from_file_location("rls_revision", REVISION_FILE)
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Result:
    """A query result with only ``all()``."""

    def __init__(self, rows: list[tuple[str, ...]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[str, ...]]:
        return self._rows


class _FakeOp:
    """Records ``op.execute`` statements and holds the fake catalog for its bind."""

    def __init__(
        self,
        roles: set[str],
        tables: dict[str, str] | None = None,
        functions: dict[str, str] | None = None,
    ) -> None:
        self.roles = roles
        self.tables = _good_tables() if tables is None else tables
        self.functions = _good_functions() if functions is None else functions
        self.statements: list[str] = []

    def execute(self, sql: Any) -> None:
        self.statements.append(" ".join(str(sql).split()))

    def get_bind(self) -> "_FakeBind":
        return _FakeBind(self)


class _FakeBind:
    """A connection that answers pg_roles, pg_class and pg_proc queries by their SQL text."""

    def __init__(self, op: _FakeOp) -> None:
        self._op = op

    def execute(self, sql: Any, params: dict[str, list[str]]) -> _Result:
        text = str(sql)
        names = params["names"]
        if "pg_roles" in text:
            return _Result([(n,) for n in names if n in self._op.roles])
        if "pg_proc" in text:
            return _Result(_rows(names, self._op.functions))
        if "pg_class" in text:
            return _Result(_rows(names, self._op.tables))
        raise AssertionError(f"unexpected query: {text}")


def _rows(names: list[str], owners: dict[str, str]) -> list[tuple[str, ...]]:
    """Return (name, owner) rows for the names present in ``owners``."""
    return [(n, owners[n]) for n in names if n in owners]


def _good_tables() -> dict[str, str]:
    """Return a table owner map where lawbyai_owner owns every checked table."""
    return dict.fromkeys(TABLES, "lawbyai_owner")


def _good_functions() -> dict[str, str]:
    """Return a function owner map where lawbyai_owner owns the trigger function."""
    return {"users_bump_session_version": "lawbyai_owner"}


def _run(fake: _FakeOp) -> _FakeOp:
    """Run upgrade() against the fake catalog of ``fake`` and return it."""
    module = _load()
    setattr(module, "op", fake)  # noqa: B010
    module.upgrade()
    return fake


def _policy(statements: list[str], name: str) -> str:
    """Return the single ALTER POLICY statement for ``name``."""
    found = [s for s in statements if s.startswith(f"ALTER POLICY {name} ")]
    assert len(found) == 1, found
    return found[0]


def _force(table: str, *, on: bool) -> str:
    """Return the expected FORCE or NO FORCE statement for ``table``."""
    mode = "FORCE" if on else "NO FORCE"
    return f"ALTER TABLE public.{table} {mode} ROW LEVEL SECURITY"


def test_revision_follows_77985ac8fa22() -> None:
    """The revision sits directly after the session_version revision."""
    module = _load()
    assert module.down_revision == "77985ac8fa22"
    assert REVISION_FILE.name.startswith(module.revision)


def test_missing_role_stops_the_migration() -> None:
    """Scenario: Missing role stops the migration, names it, and no policy has changed."""
    fake = _FakeOp(ALL_ROLES - {"lawbyai_auth"})
    with pytest.raises(RuntimeError, match="lawbyai_auth") as err:
        _run(fake)
    assert "lawbyai_app" not in str(err.value)
    assert not [s for s in fake.statements if s.startswith("ALTER")]


def test_wrong_owner_stops_the_migration() -> None:
    """Scenario: Wrong owner stops the migration."""
    fake = _FakeOp(ALL_ROLES, tables=_good_tables() | {"tenants": "postgres"})
    with pytest.raises(RuntimeError) as err:
        _run(fake)
    message = str(err.value)
    assert "table tenants is owned by postgres, not lawbyai_owner" in message
    assert not [s for s in fake.statements if s.startswith("ALTER")]


def test_wrong_function_owner_and_missing_table_are_named() -> None:
    """Step 1 names a wrong function owner (from pg_proc) and a missing table together."""
    tables = _good_tables()
    del tables["rejected_document"]
    fake = _FakeOp(ALL_ROLES, tables=tables, functions={"users_bump_session_version": "postgres"})
    with pytest.raises(RuntimeError) as err:
        _run(fake)
    message = str(err.value)
    assert "function users_bump_session_version is owned by postgres" in message
    assert "table rejected_document does not exist" in message


def test_missing_function_is_named() -> None:
    """Step 1 reads the function owner from pg_proc, not from the table query."""
    with pytest.raises(RuntimeError, match="function users_bump_session_version does not exist"):
        _run(_FakeOp(ALL_ROLES, functions={}))


def test_policies_are_tenant_only() -> None:
    """Scenarios: No tenant means zero rows; Tenant isolation on read and write.

    This checks the policy text only: USING and WITH CHECK both compare to
    nullif(setting, ''), which is NULL with no tenant. Row behaviour is in T8.
    """
    fake = _run(_FakeOp(ALL_ROLES))
    users = _policy(fake.statements, "users_isolation")
    tenants = _policy(fake.statements, "tenants_isolation")
    assert users == (
        f"ALTER POLICY users_isolation ON public.users USING (tenant_id = {TENANT}) "
        f"WITH CHECK (tenant_id = {TENANT})"
    )
    assert tenants == (
        f"ALTER POLICY tenants_isolation ON public.tenants USING (id = {TENANT}) "
        f"WITH CHECK (id = {TENANT})"
    )


def test_policies_change_inside_the_no_force_window() -> None:
    """NO FORCE (tenants, users) < every ALTER POLICY < FORCE (tenants, users)."""
    stmts = _run(_FakeOp(ALL_ROLES)).statements
    no_force = [stmts.index(_force(t, on=False)) for t in ("tenants", "users")]
    force = [stmts.index(_force(t, on=True)) for t in ("tenants", "users")]
    policies = [i for i, s in enumerate(stmts) if s.startswith("ALTER POLICY")]
    assert len(policies) == 2
    assert max(no_force) < min(policies)
    assert max(policies) < min(force)


def test_force_is_on_at_head_for_tenants_and_users_only() -> None:
    """Scenario: FORCE is on at head for tenants and users only."""
    stmts = _run(_FakeOp(ALL_ROLES)).statements
    force = [s for s in stmts if "FORCE ROW LEVEL SECURITY" in s]
    assert force == [
        _force("tenants", on=False),
        _force("users", on=False),
        _force("tenants", on=True),
        _force("users", on=True),
    ]
    assert stmts[-1] == _force("users", on=True)
    joined = "\n".join(stmts)
    assert "legal_document" not in joined
    assert "rejected_document" not in joined


def test_lock_timeout_is_set() -> None:
    """Scenario: Lock timeout is set (and it is the first statement of upgrade)."""
    assert "SET LOCAL lock_timeout = '5s'" in REVISION_FILE.read_text()
    fake = _run(_FakeOp(ALL_ROLES))
    assert fake.statements[0] == "SET LOCAL lock_timeout = '5s'"


def test_downgrade_restores_the_old_policies() -> None:
    """The downgrade puts back the 4439761c5e40 policy expressions."""
    module = _load()
    fake = _FakeOp(ALL_ROLES)
    setattr(module, "op", fake)  # noqa: B010
    module.downgrade()
    joined = "\n".join(fake.statements)
    pattern = r"ALTER POLICY tenants_isolation ON public\.tenants USING \(current_setting"
    assert re.search(pattern, joined)
    assert "OR tenant_id IS NULL" in joined
    assert TENANT not in joined
