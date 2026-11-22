"""Unit checks for the last-admin revision: statements, order, owner check, downgrade.

The revision runs against a fake ``op`` that records ``op.execute`` statements. The
live checks (refused UPDATE and DELETE, grants, round trip) are in
``tests/integration/test_last_admin_trigger.py``.
"""

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

VERSIONS = Path(__file__).resolve().parents[2] / "migrations" / "versions"
REVISION_FILE = next(VERSIONS.glob("*_last_admin_trigger_and_admin_audit.py"))


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("last_admin_revision", REVISION_FILE)
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Result:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[Any, ...]]:
        return self._rows

    def scalar_one(self) -> Any:
        return self._rows[0][0]


class _FakeBind:
    def __init__(self, owners: dict[str, str], audit_rows: int) -> None:
        self._owners = owners
        self._audit_rows = audit_rows

    def execute(self, sql: Any, params: dict[str, Any] | None = None) -> _Result:
        text = str(sql)
        if "pg_class" in text:
            assert params is not None
            return _Result([(n, self._owners[n]) for n in params["names"] if n in self._owners])
        assert "count(*)" in text
        return _Result([(self._audit_rows,)])


class _FakeOp:
    """Records statements. ``create_table`` and ``drop_table`` are recorded as text too."""

    def __init__(self, owners: dict[str, str] | None = None, audit_rows: int = 0) -> None:
        owned = {"users": "lawbyai_owner", "tenants": "lawbyai_owner"}
        self.bind = _FakeBind(owned if owners is None else owners, audit_rows)
        self.statements: list[str] = []

    def execute(self, sql: Any) -> None:
        self.statements.append(" ".join(str(sql).split()))

    def get_bind(self) -> _FakeBind:
        return self.bind

    def create_table(self, name: str, *_args: Any, **_kwargs: Any) -> None:
        self.statements.append(f"CREATE TABLE {name}")

    def create_index(self, name: str, *_args: Any, **_kwargs: Any) -> None:
        self.statements.append(f"CREATE INDEX {name}")

    def drop_table(self, name: str) -> None:
        self.statements.append(f"DROP TABLE {name}")


def _run(fake: _FakeOp, step: str) -> list[str]:
    module = _load()
    vars(module)["op"] = fake
    getattr(module, step)()
    return fake.statements


def _index(statements: list[str], prefix: str) -> int:
    found = [i for i, s in enumerate(statements) if s.startswith(prefix)]
    assert len(found) == 1, (prefix, statements)
    return found[0]


def test_revision_follows_the_reject_audit_revision() -> None:
    module = _load()
    assert module.down_revision == "81dde4a27be7"


def test_upgrade_sets_lock_timeout_first() -> None:
    assert _run(_FakeOp(), "upgrade")[0] == "SET LOCAL lock_timeout = '5s'"


@pytest.mark.parametrize("owners", [{"users": "someone", "tenants": "lawbyai_owner"}, {}])
def test_wrong_or_missing_owner_stops_before_any_change(owners: dict[str, str]) -> None:
    fake = _FakeOp(owners)
    module = _load()
    vars(module)["op"] = fake
    with pytest.raises(RuntimeError, match="prerequisites not met"):
        module.upgrade()
    assert fake.statements == ["SET LOCAL lock_timeout = '5s'"]


def test_audit_table_is_forced_tenant_rls_with_select_insert_only() -> None:
    statements = _run(_FakeOp(), "upgrade")
    assert _index(statements, "CREATE TABLE admin_action_audit") < _index(
        statements, "ALTER TABLE public.admin_action_audit ENABLE ROW LEVEL SECURITY"
    )
    force = _index(statements, "ALTER TABLE public.admin_action_audit FORCE ROW LEVEL SECURITY")
    policy = statements[_index(statements, "CREATE POLICY admin_action_audit_isolation")]
    assert force < _index(statements, "CREATE POLICY")
    assert "USING (tenant_id = nullif(current_setting('app.current_tenant', true), ''))" in policy
    assert (
        "WITH CHECK (tenant_id = nullif(current_setting('app.current_tenant', true), ''))" in policy
    )
    grants = [s for s in statements if s.startswith("GRANT")]
    assert grants == ["GRANT SELECT, INSERT ON public.admin_action_audit TO lawbyai_app"]


def test_function_is_invoker_with_a_pinned_search_path() -> None:
    statements = _run(_FakeOp(), "upgrade")
    sql = statements[_index(statements, "CREATE FUNCTION")]
    assert "SECURITY DEFINER" not in sql
    assert "SET search_path = pg_catalog, pg_temp" in sql
    assert "FOR NO KEY UPDATE" in sql
    assert "ORDER BY u.id" in sql
    assert "ERRCODE = '23514'" in sql
    assert "CONSTRAINT = 'trg_users_last_admin'" in sql


def test_function_owner_bypass_needs_the_owner_role_and_the_setting() -> None:
    statements = _run(_FakeOp(), "upgrade")
    sql = statements[_index(statements, "CREATE FUNCTION")]
    assert "current_setting('app.skip_last_admin_check', true) = 'on'" in sql
    assert "current_user = 'lawbyai_owner'" in sql


def test_trigger_fires_on_update_of_the_three_columns_and_on_delete() -> None:
    statements = _run(_FakeOp(), "upgrade")
    sql = statements[_index(statements, "CREATE TRIGGER trg_users_last_admin")]
    assert "BEFORE UPDATE OF is_active, role, tenant_id OR DELETE ON public.users" in sql
    assert "FOR EACH ROW" in sql


def test_public_has_no_execute_and_the_function_exists_before_the_trigger() -> None:
    statements = _run(_FakeOp(), "upgrade")
    function = _index(statements, "CREATE FUNCTION")
    revoke = _index(
        statements, "REVOKE EXECUTE ON FUNCTION public.users_guard_last_admin() FROM PUBLIC"
    )
    assert function < revoke < _index(statements, "CREATE TRIGGER")


def test_downgrade_drops_trigger_function_then_table() -> None:
    statements = _run(_FakeOp(), "downgrade")
    assert _index(statements, "DROP TRIGGER trg_users_last_admin ON public.users") < _index(
        statements, "DROP FUNCTION public.users_guard_last_admin()"
    )
    assert _index(statements, "DROP FUNCTION") < _index(statements, "DROP TABLE admin_action_audit")


def test_downgrade_lifts_force_before_counting_rows() -> None:
    statements = _run(_FakeOp(), "downgrade")
    assert "ALTER TABLE public.admin_action_audit NO FORCE ROW LEVEL SECURITY" in statements


def test_downgrade_stops_when_the_audit_table_holds_rows() -> None:
    fake = _FakeOp(audit_rows=3)
    module = _load()
    vars(module)["op"] = fake
    with pytest.raises(RuntimeError, match="holds 3 rows"):
        module.downgrade()
    assert "DROP TABLE admin_action_audit" not in fake.statements
