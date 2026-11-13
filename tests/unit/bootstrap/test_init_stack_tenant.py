"""Init program under fail-closed RLS: tenant context, owner URL, role passwords."""

from __future__ import annotations

from dataclasses import replace
from unittest.mock import MagicMock

import pytest
import sqlalchemy
from factories.bootstrap import OWNER_URL, FakeBucket, FakeSettings, FakeStore, integrity_error

from bootstrap import init_stack
from bootstrap.init_stack import ensure_schema, ensure_tenant, run, validate_config
from core.security import ADMIN, get_current_tenant

TENANT_STEP_CALLS = ("list_tenants", "create_tenant", "get_login_user", "create_user")


def go(store: FakeStore, settings: FakeSettings | None = None) -> int:
    """Run the init program with fakes and no real sleeps."""
    return run(
        settings or FakeSettings(),
        store,
        FakeBucket(),
        revision=store.current_revision,
        upgrade=store.upgrade,
        sleep=lambda _: None,
    )


def test_tenant_and_admin_steps_run_in_init_tenant_context() -> None:
    """Scenario: Bootstrap runs in the init tenant context."""
    store = FakeStore()
    assert go(store, FakeSettings(init_tenant_id="platform")) == 0
    assert {name: store.tenant_seen[name] for name in TENANT_STEP_CALLS} == dict.fromkeys(
        TENANT_STEP_CALLS, "platform"
    )
    assert get_current_tenant() is None


def test_schema_step_runs_without_a_tenant() -> None:
    """Only the tenant and admin steps get the tenant context."""
    store = FakeStore()
    go(store)
    assert store.tenant_seen["upgrade"] is None
    assert store.tenant_seen["initialize"] is None


def test_admin_is_found_through_get_login_user() -> None:
    """Scenario: Bootstrap runs in the init tenant context (admin lookup)."""
    store = FakeStore(users={"admin@example.com": {"role": ADMIN, "is_active": True}})
    assert go(store, FakeSettings(init_admin_email=" Admin@Example.com ")) == 0
    assert "get_login_user" in store.calls
    assert "create_user" not in store.calls


def test_existing_tenant_is_reported_as_exists(caplog: pytest.LogCaptureFixture) -> None:
    """Scenario: Tenant step is idempotent."""
    store = FakeStore(fail={"create_tenant": integrity_error()})
    assert ensure_tenant(store, "platform", "Platform") == "exists"
    assert go(FakeStore(fail={"create_tenant": integrity_error()})) == 0
    assert "step=tenant result=exists" in caplog.text


def test_schema_step_upgrades_with_the_owner_url() -> None:
    """Scenario: Schema step uses the owner URL."""
    store = FakeStore()
    result = ensure_schema(store, store.current_revision, lambda: store.upgrade(OWNER_URL))
    assert result == "created"
    assert store.upgrade_urls == [OWNER_URL]
    assert store.calls.index("upgrade") < store.calls.index("initialize")


def test_run_passes_the_owner_url_to_upgrade() -> None:
    """``run`` hands ``postgres_owner_url``, not the app URL, to the upgrade."""
    store = FakeStore()
    go(store, FakeSettings(postgres_owner_url="postgresql://owner@db/x"))
    assert store.upgrade_urls == ["postgresql://owner@db/x"]


def test_alembic_upgrade_targets_head_with_the_given_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """The default upgrade runs ``alembic upgrade head`` with the URL it receives."""
    upgrade = MagicMock()
    monkeypatch.setattr(init_stack.command, "upgrade", upgrade)
    init_stack.alembic_upgrade("postgresql://owner:p%40ss@db/x")
    cfg, target = upgrade.call_args.args
    assert target == "head"
    assert cfg.get_main_option("sqlalchemy.url") == "postgresql://owner:p%40ss@db/x"


class EngineReached(Exception):
    """Raised by the fake engine factory; carries the URL env.py passed to it."""

    def __init__(self, url: str) -> None:
        super().__init__(url)
        self.url = url


def test_alembic_upgrade_url_reaches_the_env_py_engine(monkeypatch: pytest.MonkeyPatch) -> None:
    """The URL given to ``alembic_upgrade`` is the URL env.py builds its engine from."""

    def fake_engine_from_config(options: dict[str, str], **_: object) -> None:
        raise EngineReached(options["sqlalchemy.url"])

    monkeypatch.setenv("POSTGRES_OWNER_URL", "postgresql://from-settings@db/x")
    monkeypatch.setattr(sqlalchemy, "engine_from_config", fake_engine_from_config)
    with pytest.raises(EngineReached) as reached:
        init_stack.alembic_upgrade("postgresql://owner:p%40ss@db/x")
    assert reached.value.url == "postgresql://owner:p%40ss@db/x"


@pytest.mark.parametrize(
    ("field", "var"),
    [
        ("postgres_owner_password", "LAWBYAI_OWNER_PASSWORD"),
        ("postgres_app_password", "LAWBYAI_APP_PASSWORD"),
    ],
)
def test_role_password_placeholder_is_rejected(field: str, var: str) -> None:
    """The owner and app role passwords join the change-me check."""
    settings = replace(FakeSettings(), **{field: "change-me-role"})
    assert validate_config(settings) == [f"{var} starts with change-me"]
