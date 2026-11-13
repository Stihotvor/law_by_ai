"""Unit checks for the rls-201 revision (T3, T4): role checks, NO FORCE window,
policies, ``auth_lookup_user``, grants and the downgrade.

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
# (rolsuper, rolbypassrls, rolcanlogin) as the init script creates each role.
GOOD_ATTRS = {
    "lawbyai_owner": (False, False, True),
    "lawbyai_app": (False, False, True),
    "lawbyai_auth": (False, True, False),
}
# (table, policy) as 4439761c5e40 creates them.
GOOD_POLICIES = {("tenants", "tenants_isolation"), ("users", "users_isolation")}


def _load() -> ModuleType:
    """Import the revision file as a module."""
    spec = importlib.util.spec_from_file_location("rls_revision", REVISION_FILE)
    assert spec
    assert spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Result:
    """A query result with ``all()`` and ``scalar_one()``."""

    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[Any, ...]]:
        return self._rows

    def scalar_one(self) -> Any:
        assert len(self._rows) == 1
        return self._rows[0][0]


class _FakeOp:
    """Records ``op.execute`` statements and holds the fake catalog for its bind."""

    def __init__(
        self,
        roles: set[str],
        tables: dict[str, str] | None = None,
        functions: dict[str, str] | None = None,
        *,
        auth_can_create: bool = True,
        attrs: dict[str, tuple[bool, bool, bool]] | None = None,
        app_in_auth: bool = False,
        policies: set[tuple[str, str]] | None = None,
        rls: dict[str, bool] | None = None,
    ) -> None:
        self.roles = roles
        self.attrs = GOOD_ATTRS | (attrs or {})
        self.app_in_auth = app_in_auth
        self.tables = _good_tables() if tables is None else tables
        self.functions = _good_functions() if functions is None else functions
        self.auth_can_create = auth_can_create
        self.policies = GOOD_POLICIES if policies is None else policies
        self.rls = {"tenants": True, "users": True} | (rls or {})
        self.statements: list[str] = []

    def execute(self, sql: Any) -> None:
        self.statements.append(" ".join(str(sql).split()))

    def get_bind(self) -> "_FakeBind":
        return _FakeBind(self)


class _FakeBind:
    """A connection that answers the catalog queries (pg_roles, pg_class, ...) by SQL text."""

    def __init__(self, op: _FakeOp) -> None:
        self._op = op

    def execute(self, sql: Any, params: dict[str, Any] | None = None) -> _Result:
        text = str(sql)
        if "has_schema_privilege" in text:
            return _Result([(self._op.auth_can_create,)])
        assert params is not None
        assert "pg_auth_members" not in text, "use pg_has_role to catch indirect chains"
        if "pg_has_role" in text:
            return self._has_role(params)
        names = params["names"]
        if "pg_roles" in text:
            return _Result([(n, *self._op.attrs[n]) for n in names if n in self._op.roles])
        if "pg_policy" in text:
            return _Result([p for p in sorted(self._op.policies) if p[1] in names])
        if "relrowsecurity" in text:
            return _Result([(n, self._op.rls[n]) for n in names if n in self._op.rls])
        if "pg_proc" in text:
            return _Result(_rows(names, self._op.functions))
        if "pg_class" in text:
            return _Result(_rows(names, self._op.tables))
        raise AssertionError(f"unexpected query: {text}")

    def _has_role(self, params: dict[str, Any]) -> _Result:
        """Answer pg_has_role; like PostgreSQL, fail on a role that does not exist."""
        member, role = params["member"], params["role"]
        if not {member, role} <= self._op.roles:
            raise AssertionError(f"pg_has_role on a missing role: {member}, {role}")
        assert (member, role) == ("lawbyai_app", "lawbyai_auth")
        return _Result([(self._op.app_in_auth,)])


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
    vars(module)["op"] = fake
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
    assert not [s for s in force if "legal_document" in s or "rejected_document" in s]


def test_lock_timeout_is_set() -> None:
    """Scenario: Lock timeout is set (and it is the first statement of upgrade)."""
    assert "SET LOCAL lock_timeout = '5s'" in REVISION_FILE.read_text()
    fake = _run(_FakeOp(ALL_ROLES))
    assert fake.statements[0] == "SET LOCAL lock_timeout = '5s'"


def test_downgrade_restores_the_old_policies() -> None:
    """The downgrade puts back the 4439761c5e40 policy expressions."""
    module = _load()
    fake = _FakeOp(ALL_ROLES)
    vars(module)["op"] = fake
    module.downgrade()
    joined = "\n".join(fake.statements)
    pattern = r"ALTER POLICY tenants_isolation ON public\.tenants USING \(current_setting"
    assert re.search(pattern, joined)
    assert "OR tenant_id IS NULL" in joined
    assert TENANT not in joined


FUNC = "public.auth_lookup_user(text)"
AUTH_COLUMNS = "id, tenant_id, email, role, name, is_active, password_hash, session_version"
APP_TABLES = ("tenants", "users", "legal_document", "rejected_document")


def _downgrade() -> list[str]:
    """Run downgrade() against a fake op and return its statements."""
    module = _load()
    fake = _FakeOp(ALL_ROLES)
    vars(module)["op"] = fake
    module.downgrade()
    return fake.statements


def _one(statements: list[str], prefix: str) -> int:
    """Return the index of the single statement that starts with ``prefix``."""
    found = [i for i, s in enumerate(statements) if s.startswith(prefix)]
    assert len(found) == 1, (prefix, statements)
    return found[0]


def test_function_is_defined_as_designed() -> None:
    """Scenario: Function is defined as designed (prosecdef, proconfig, proowner)."""
    stmts = _run(_FakeOp(ALL_ROLES)).statements
    index = _one(stmts, "CREATE FUNCTION public.auth_lookup_user(p_email text)")
    create = stmts[index].replace("( ", "(").replace(" )", ")")
    assert (
        "RETURNS TABLE (id varchar, tenant_id varchar, email varchar, role varchar, "
        "name varchar, is_active boolean, password_hash varchar, session_version integer)"
    ) in create
    for part in ("LANGUAGE sql", "STABLE", "STRICT", "SECURITY DEFINER"):
        assert part in create
    assert "SET search_path = pg_catalog, pg_temp" in create
    assert "FROM public.users u WHERE u.email = lower(btrim(p_email))" in create
    owner = _one(stmts, f"ALTER FUNCTION {FUNC} OWNER TO lawbyai_auth")
    assert stmts.index(_force("users", on=True)) < index < owner


def test_public_has_no_execute() -> None:
    """Scenario: PUBLIC has no EXECUTE; lawbyai_app has it.

    REVOKE and GRANT run while lawbyai_owner still owns the function: the owner
    role does not inherit lawbyai_auth, so it could not change the ACL after
    ALTER OWNER. The ACL moves to the new owner with the ownership.
    """
    stmts = _run(_FakeOp(ALL_ROLES)).statements
    create = _one(stmts, "CREATE FUNCTION public.auth_lookup_user")
    revoke = _one(stmts, f"REVOKE EXECUTE ON FUNCTION {FUNC} FROM PUBLIC")
    grant = _one(stmts, f"GRANT EXECUTE ON FUNCTION {FUNC} TO lawbyai_app")
    owner = _one(stmts, f"ALTER FUNCTION {FUNC} OWNER TO lawbyai_auth")
    assert create < revoke < owner
    assert create < grant < owner
    assert (
        "ALTER DEFAULT PRIVILEGES FOR ROLE lawbyai_owner REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC"
        in stmts
    )


def test_auth_role_has_column_select_on_users() -> None:
    """Scenario: Auth role has column SELECT on users (exactly the function columns)."""
    stmts = _run(_FakeOp(ALL_ROLES)).statements
    grants = [s for s in stmts if s.startswith("GRANT") and "lawbyai_auth" in s]
    assert grants == [f"GRANT SELECT ({AUTH_COLUMNS}) ON public.users TO lawbyai_auth"]


def test_app_can_read_the_revision() -> None:
    """Scenario: App can read the revision; it also gets DML and the sequence."""
    stmts = _run(_FakeOp(ALL_ROLES)).statements
    assert "GRANT SELECT ON public.alembic_version TO lawbyai_app" in stmts
    for table in APP_TABLES:
        assert f"GRANT SELECT, INSERT, UPDATE, DELETE ON public.{table} TO lawbyai_app" in stmts
    assert "GRANT USAGE, SELECT ON SEQUENCE public.rejected_document_id_seq TO lawbyai_app" in stmts


def test_downgrade_undoes_upgrade_and_keeps_force_and_check() -> None:
    """Scenario: Downgrade and upgrade again (statement level; the live run is in T8)."""
    stmts = _downgrade()
    assert stmts[0] == "SET LOCAL lock_timeout = '5s'"
    drop = _one(stmts, f"DROP FUNCTION IF EXISTS {FUNC}")
    # Only the function owner may drop it; lawbyai_owner does not inherit lawbyai_auth.
    assert stmts[drop - 1] == "SET LOCAL ROLE lawbyai_auth"
    assert stmts[drop + 1] == "RESET ROLE"
    assert (
        "ALTER DEFAULT PRIVILEGES FOR ROLE lawbyai_owner GRANT EXECUTE ON FUNCTIONS TO PUBLIC"
        in stmts
    )
    upgrade = _run(_FakeOp(ALL_ROLES)).statements
    for grant in [s for s in upgrade if s.startswith("GRANT") and " ON public." in s]:
        revoke = grant.replace("GRANT ", "REVOKE ", 1).replace(" TO ", " FROM ")
        assert revoke in stmts, revoke
    assert not [s for s in stmts if "FORCE" in s]
    assert not [s for s in stmts if "ck_users_email_normalised" in s or "CONSTRAINT" in s]
    policies = [i for i, s in enumerate(stmts) if s.startswith("ALTER POLICY")]
    assert len(policies) == 2
    assert drop < min(policies)


def test_auth_role_without_schema_create_stops_the_migration() -> None:
    """Step 1 names a missing CREATE on schema public for lawbyai_auth (ALTER OWNER needs it)."""
    fake = _FakeOp(ALL_ROLES, auth_can_create=False)
    with pytest.raises(RuntimeError) as err:
        _run(fake)
    assert "lawbyai_auth has no CREATE on schema public" in str(err.value)
    assert not [s for s in fake.statements if s.startswith(("ALTER", "GRANT", "CREATE"))]


def test_missing_auth_role_skips_the_schema_check() -> None:
    """With no lawbyai_auth role, step 1 names the role and does not query its privilege."""
    with pytest.raises(RuntimeError) as err:
        _run(_FakeOp(ALL_ROLES - {"lawbyai_auth"}, auth_can_create=False))
    assert "no CREATE on schema" not in str(err.value)


def test_downgrade_literals_match_the_constants() -> None:
    """The downgrade spells roles, sequence and columns as literals; they must match."""
    module = _load()
    joined = "\n".join(_downgrade())
    found = {
        "app": re.findall(r"REVOKE SELECT ON public\.alembic_version FROM (\w+)$", joined, re.M),
        "seq": re.findall(r"ON SEQUENCE public\.(\w+) FROM (\w+)$", joined, re.M),
        "cols": re.findall(r"REVOKE SELECT \(([^)]*)\) ON public\.users FROM (\w+)$", joined, re.M),
        "role": re.findall(r"^SET LOCAL ROLE (\w+)$", joined, re.M),
    }
    assert found["app"] == [module.APP_ROLE]
    assert found["seq"] == [(module.APP_SEQUENCE, module.APP_ROLE)]
    assert found["cols"] == [(module.AUTH_COLUMN_LIST, module.AUTH_ROLE)]
    assert found["role"] == [module.AUTH_ROLE]


def test_wrong_role_attributes_are_all_named() -> None:
    """Step 1 names every wrong rolsuper, rolbypassrls and rolcanlogin in one error."""
    attrs = {
        "lawbyai_owner": (True, False, True),
        "lawbyai_app": (False, True, False),
        "lawbyai_auth": (True, False, True),
    }
    fake = _FakeOp(ALL_ROLES, attrs=attrs)
    with pytest.raises(RuntimeError) as err:
        _run(fake)
    message = str(err.value)
    for expected in (
        "role lawbyai_owner has rolsuper true, expected false",
        "role lawbyai_app has rolbypassrls true, expected false",
        "role lawbyai_app has rolcanlogin false, expected true",
        "role lawbyai_auth has rolsuper true, expected false",
        "role lawbyai_auth has rolbypassrls false, expected true",
        "role lawbyai_auth has rolcanlogin true, expected false",
    ):
        assert expected in message
    assert "lawbyai_owner has rolbypassrls" not in message
    assert not [s for s in fake.statements if s.startswith(("ALTER", "GRANT", "CREATE"))]


def test_app_member_of_auth_stops_the_migration() -> None:
    """Step 1 stops when lawbyai_app is a member of lawbyai_auth (pg_has_role)."""
    fake = _FakeOp(ALL_ROLES, app_in_auth=True)
    with pytest.raises(RuntimeError, match="lawbyai_app is a member of lawbyai_auth"):
        _run(fake)
    assert not [s for s in fake.statements if s.startswith(("ALTER", "GRANT", "CREATE"))]


def test_membership_and_attribute_problems_join_other_problems() -> None:
    """One error lists a wrong owner, a wrong attribute and the membership together."""
    fake = _FakeOp(
        ALL_ROLES,
        tables=_good_tables() | {"users": "postgres"},
        attrs={"lawbyai_app": (False, True, True)},
        app_in_auth=True,
    )
    with pytest.raises(RuntimeError) as err:
        _run(fake)
    message = str(err.value)
    assert "table users is owned by postgres" in message
    assert "role lawbyai_app has rolbypassrls true" in message
    assert "lawbyai_app is a member of lawbyai_auth" in message


def test_missing_app_role_skips_the_membership_check() -> None:
    """With no lawbyai_app role, step 1 names the role and does not call pg_has_role."""
    with pytest.raises(RuntimeError) as err:
        _run(_FakeOp(ALL_ROLES - {"lawbyai_app"}, app_in_auth=True))
    message = str(err.value)
    assert "role lawbyai_app does not exist" in message
    assert "member of" not in message


def test_membership_check_uses_pg_has_role_member() -> None:
    """The membership check follows indirect chains: pg_has_role with MEMBER."""
    sql = " ".join(_load().MEMBERSHIP_SQL.split())
    assert sql == "SELECT pg_has_role(:member, :role, 'MEMBER')"


def test_missing_auth_role_skips_the_membership_check() -> None:
    """With no lawbyai_auth role, step 1 does not call pg_has_role (it would raise)."""
    with pytest.raises(RuntimeError) as err:
        _run(_FakeOp(ALL_ROLES - {"lawbyai_auth"}, app_in_auth=True))
    assert "member of" not in str(err.value)


def test_missing_policy_stops_the_migration() -> None:
    """Step 1 names a missing users_isolation policy (from pg_policy) before any change."""
    fake = _FakeOp(ALL_ROLES, policies={("tenants", "tenants_isolation")})
    with pytest.raises(RuntimeError) as err:
        _run(fake)
    message = str(err.value)
    assert "policy users_isolation on users does not exist" in message
    assert "tenants_isolation" not in message
    assert not [s for s in fake.statements if s.startswith(("ALTER", "GRANT", "CREATE"))]


def test_rls_disabled_stops_the_migration() -> None:
    """Step 1 names a table with relrowsecurity false, together with other problems."""
    fake = _FakeOp(ALL_ROLES, policies=set(), rls={"users": False})
    with pytest.raises(RuntimeError) as err:
        _run(fake)
    message = str(err.value)
    assert "row level security is not enabled on users" in message
    assert "row level security is not enabled on tenants" not in message
    assert "policy tenants_isolation on tenants does not exist" in message
    assert not [s for s in fake.statements if s.startswith(("ALTER", "GRANT", "CREATE"))]
