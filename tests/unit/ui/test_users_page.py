"""Streamlit users page: admin guard, create form, user table and deactivate action.

No database: ``core.users.UserService`` is replaced with a fake service and
``ui.components.auth._store`` (behind ``get_store``) with a sentinel, so no
``PostgreSQLStore`` is built.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import streamlit as st
from sqlalchemy.exc import OperationalError
from streamlit.testing.v1 import AppTest

from core.security import PrincipalRequiredError
from core.security.passwords import MAX_PASSWORD_BYTES, MIN_PASSWORD_CHARS
from core.users import (
    LastAdminError,
    SelfDeactivationError,
    UserCreateRefusedError,
    UserNotFoundError,
    UserRecord,
    UserService,
)

SRC = Path(__file__).resolve().parents[3] / "src"
PAGE = str(SRC / "ui" / "pages" / "users.py")
APP = str(SRC / "ui" / "app.py")
STORE = object()
PASSWORD = "very-secret-password-1"  # noqa: S105 (test value)
HASH = "$2b$12$abcdefghijklmnopqrstuuSECRETHASHVALUEabcdefghijklmnop"
ADMIN_REQUIRED = "Admin role required."
DB_ERROR = "Database error. Try again later."
PW_KEY = "new_user_initial_cred"


def _record(uid: str, email: str, role: str = "user", *, active: bool = True) -> UserRecord:
    return {
        "id": uid,
        "tenant_id": "t-1",
        "email": email,
        "role": role,
        "name": email.split("@")[0],
        "is_active": active,
    }


@dataclass
class FakeService:
    """Stand-in for ``UserService``: records calls and raises configured errors."""

    users: list[Any] = field(default_factory=list)
    list_error: Exception | None = None
    create_error: Exception | None = None
    deactivate_error: Exception | None = None
    created: list[tuple[str, str, str, str]] = field(default_factory=list)
    deactivated: list[str] = field(default_factory=list)
    repos: list[object] = field(default_factory=list)

    def __call__(self, repo: object) -> FakeService:
        self.repos.append(repo)
        return self

    def list_users(self) -> list[Any]:
        if self.list_error is not None:
            raise self.list_error
        return self.users

    def create_user(self, email: str, password: str, role: str, name: str) -> UserRecord:
        self.created.append((email, password, role, name))
        if self.create_error is not None:
            raise self.create_error
        return _record("u-new", email, role)

    def deactivate_user(self, user_id: str) -> bool:
        self.deactivated.append(user_id)
        if self.deactivate_error is not None:
            raise self.deactivate_error
        return True


@pytest.fixture
def service() -> Iterator[FakeService]:
    fake = FakeService(
        users=[
            _record("u-1", "admin@x.com", "admin"),
            _record("u-2", "bob@x.com"),
            _record("u-3", "gone@x.com", active=False),
        ]
    )
    with (
        patch("core.users.UserService", fake),
        patch("ui.components.auth._store", lambda: STORE),
    ):
        yield fake


def _page(role: str | None = "admin") -> AppTest:
    at = AppTest.from_file(PAGE)
    if role is not None:
        at.session_state["user"] = {"role": role}
    return at.run()


def _fill(at: AppTest, email: str = "new@x.com", role: str = "user") -> AppTest:
    at.text_input(key="new_user_email").input(email)
    at.text_input(key="new_user_name").input("New")
    at.selectbox(key="new_user_role").select(role)
    at.text_input(key=PW_KEY).input(PASSWORD)
    next(b for b in at.button if b.label == "Create user").click()
    return at


def _create(at: AppTest, email: str = "new@x.com", role: str = "user") -> AppTest:
    return _fill(at, email, role).run()


def _deactivate(at: AppTest, user_id: str) -> AppTest:
    at.button(key=f"deactivate_{user_id}").click()
    return at.run()


def _all_text(at: AppTest) -> str:
    elements = [*at.markdown, *at.text, *at.error, *at.success, *at.warning, *at.caption]
    return " ".join(str(e.value) for e in elements)


def _deactivate_keys(at: AppTest) -> set[str]:
    return {b.key for b in at.button if b.key and b.key.startswith("deactivate_")}


# --- guard ----------------------------------------------------------------------


@pytest.mark.parametrize("role", ["user", None])
def test_non_admin_sees_admin_required_and_service_is_not_called(role: str | None) -> None:
    factory = MagicMock()
    with patch("core.users.UserService", factory), patch("ui.components.auth._store") as store:
        at = _page(role)
    assert [w.value for w in at.warning] == [ADMIN_REQUIRED]
    factory.assert_not_called()
    store.assert_not_called()
    assert len(at.button) == 0
    assert len(at.text_input) == 0


def test_demoted_session_cannot_create(service: FakeService) -> None:
    """The action runs after ``require_admin``: a session demoted before submit is stopped."""
    at = _fill(_page())
    at.session_state["user"] = {"role": "user"}
    at = at.run()
    assert service.created == []
    assert [w.value for w in at.warning] == [ADMIN_REQUIRED]


def test_demoted_session_cannot_deactivate(service: FakeService) -> None:
    at = _page()
    at.button(key="deactivate_u-2").click()
    at.session_state["user"] = {"role": "user"}
    at = at.run()
    assert service.deactivated == []
    assert [w.value for w in at.warning] == [ADMIN_REQUIRED]


# --- list -----------------------------------------------------------------------


def test_admin_sees_users_and_service_gets_the_store(service: FakeService) -> None:
    at = _page()
    assert not at.exception
    text = _all_text(at)
    for email in ("admin@x.com", "bob@x.com", "gone@x.com"):
        assert email in text
    assert service.repos
    assert all(repo is STORE for repo in service.repos)


def test_deactivate_button_only_for_active_users(service: FakeService) -> None:
    at = _page()
    assert _deactivate_keys(at) == {"deactivate_u-1", "deactivate_u-2"}


def test_table_never_shows_password_hash(service: FakeService) -> None:
    service.users = [{**_record("u-9", "leak@x.com"), "password_hash": HASH}]
    at = _page()
    assert "leak@x.com" in _all_text(at)
    assert HASH not in _all_text(at)
    assert "password_hash" not in _all_text(at)


def test_list_db_error_shows_generic_message(service: FakeService) -> None:
    service.list_error = OperationalError("SELECT secret_sql FROM users", {}, Exception("boom"))
    at = _page()
    assert not at.exception
    assert [e.value for e in at.error] == [DB_ERROR]
    assert "secret_sql" not in _all_text(at)
    assert "Traceback" not in _all_text(at)


def test_list_principal_error_shows_fixed_message(service: FakeService) -> None:
    service.list_error = PrincipalRequiredError("request principal is not an active admin")
    at = _page()
    assert [e.value for e in at.error] == [ADMIN_REQUIRED]
    assert "active admin" not in _all_text(at)


# --- create ---------------------------------------------------------------------


def test_create_calls_service_and_shows_success(service: FakeService) -> None:
    at = _create(_page(), "new@x.com", "admin")
    assert not at.exception
    assert service.created == [("new@x.com", PASSWORD, "admin", "New")]
    assert len(at.success) == 1
    assert len(at.error) == 0


def test_role_select_offers_admin_and_user(service: FakeService) -> None:
    at = _page()
    assert set(at.selectbox(key="new_user_role").options) == {"admin", "user"}


def test_form_has_no_tenant_field(service: FakeService) -> None:
    at = _page()
    labels = [t.label.lower() for t in at.text_input]
    assert not any("tenant" in label for label in labels)


@pytest.mark.parametrize("error", [None, UserCreateRefusedError("duplicate")])
def test_password_is_cleared_and_never_shown(service: FakeService, error: Exception | None) -> None:
    service.create_error = error
    at = _create(_page())
    assert at.text_input(key=PW_KEY).value == ""
    assert PASSWORD not in _all_text(at)


def test_password_is_cleared_for_the_next_submit(service: FakeService) -> None:
    at = _create(_page())
    next(b for b in at.button if b.label == "Create user").click()
    at.run()
    assert service.created[-1][1] == ""


def test_password_help_names_the_limits(service: FakeService) -> None:
    help_text = str(_page().text_input(key=PW_KEY).help)
    assert str(MIN_PASSWORD_CHARS) in help_text
    assert str(MAX_PASSWORD_BYTES) in help_text


def test_duplicate_email_shows_fixed_message(service: FakeService) -> None:
    service.create_error = UserCreateRefusedError("email taken in tenant t-1")
    at = _create(_page())
    assert [e.value for e in at.error] == ["Cannot create this user."]
    assert "t-1" not in _all_text(at)


class _ValidatingService(UserService):
    """Real ``UserService`` input checks; the actor lookup is bypassed (no tenant context)."""

    def _actor(self) -> UserRecord:
        return _record("u-1", "admin@x.com", "admin")


class _NoWriteRepo:
    """Repository that fails the test if invalid input ever reaches a write."""

    def list_users(self) -> list[UserRecord]:
        return []

    def insert_user(self, **_: str) -> UserRecord:
        raise AssertionError("invalid input reached the port")


def _submit(at: AppTest, email: str, password: str, name: str = "New") -> AppTest:
    at.text_input(key="new_user_email").input(email)
    at.text_input(key="new_user_name").input(name)
    at.text_input(key=PW_KEY).input(password)
    next(b for b in at.button if b.label == "Create user").click()
    return at.run()


# QA-045: each invalid input shows the fixed message and no stack trace
@pytest.mark.parametrize(
    ("email", "password", "name"),
    [
        ("", PASSWORD, "New"),
        ("no-at.example", PASSWORD, "New"),
        ("a@@x.com", PASSWORD, "New"),
        ("a" * 252 + "@x.com", PASSWORD, "New"),
        ("new@x.com", "p" * (MIN_PASSWORD_CHARS - 1), "New"),
        ("new@x.com", "p" * (MAX_PASSWORD_BYTES + 1), "New"),
        ("new@x.com", "ł" * 37, "New"),
        ("new@x.com", PASSWORD, "n" * 257),
    ],
    ids=[
        "empty-email",
        "no-at",
        "two-ats",
        "long-email",
        "short-pw",
        "73-byte-pw",
        "74-byte-multibyte-pw",
        "long-name",
    ],
)
def test_invalid_input_shows_fixed_message_and_no_trace(
    email: str, password: str, name: str
) -> None:
    with (
        patch("core.users.UserService", lambda _repo: _ValidatingService(_NoWriteRepo())),  # type: ignore[arg-type]
        patch("ui.components.auth._store", lambda: STORE),
    ):
        at = _submit(_page(), email, password, name)
    assert not at.exception
    assert [e.value for e in at.error] == ["Cannot create this user."]
    text = _all_text(at)
    assert "Traceback" not in text
    assert "password needs" not in text
    assert "email must hold" not in text


def test_bad_role_cannot_be_chosen(service: FakeService) -> None:
    """The role widget sends an option index, so a role outside the list cannot be sent."""
    at = _page()
    at.selectbox(key="new_user_role").select("root")
    at.text_input(key=PW_KEY).input(PASSWORD)
    next(b for b in at.button if b.label == "Create user").click()
    with pytest.raises(ValueError, match="'root' is not in list"):
        at.run()
    assert service.created == []


def test_create_db_error_shows_generic_message_without_raw_text(service: FakeService) -> None:
    service.create_error = OperationalError(
        "INSERT INTO users (password_hash) VALUES (%(h)s)", {"h": HASH}, Exception("boom")
    )
    at = _create(_page())
    assert not at.exception
    assert [e.value for e in at.error] == [DB_ERROR]
    text = _all_text(at)
    assert "Traceback" not in text
    assert "INSERT" not in text
    assert HASH not in text


# --- deactivate -----------------------------------------------------------------


def test_deactivate_calls_service_with_row_id(service: FakeService) -> None:
    at = _deactivate(_page(), "u-2")
    assert not at.exception
    assert service.deactivated == ["u-2"]
    assert len(at.success) == 1


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (UserNotFoundError("u-2"), "User not found."),
        (SelfDeactivationError("u-2"), "You cannot deactivate yourself."),
        (LastAdminError("t-1"), "Cannot deactivate the last admin."),
        (PrincipalRequiredError("no tenant is set"), ADMIN_REQUIRED),
        (OperationalError("UPDATE users raw detail", {}, Exception("boom")), DB_ERROR),
    ],
)
def test_deactivate_errors_show_fixed_messages(
    service: FakeService, error: Exception, message: str
) -> None:
    service.deactivate_error = error
    at = _deactivate(_page(), "u-2")
    assert not at.exception
    assert [e.value for e in at.error] == [message]
    assert str(error) not in _all_text(at)
    assert "Traceback" not in _all_text(at)


def test_db_error_logs_only_the_class_name(
    service: FakeService, caplog: pytest.LogCaptureFixture
) -> None:
    service.create_error = OperationalError(
        "INSERT INTO users (password_hash) VALUES (%(h)s)", {"h": HASH}, Exception("boom")
    )
    _create(_page())
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "OperationalError" in logged
    assert "INSERT" not in logged
    assert HASH not in logged


def test_unexpected_error_is_not_mapped(service: FakeService) -> None:
    service.deactivate_error = RuntimeError("bug")
    at = _deactivate(_page(), "u-2")
    assert at.exception
    assert DB_ERROR not in _all_text(at)


# --- registration in app.py -----------------------------------------------------


@contextmanager
def _app(role: str) -> Iterator[AppTest]:
    """Run app.py with no settings and ``require_auth`` returning a *role* principal."""
    at = AppTest.from_file(APP)
    at.session_state["user"] = {"role": role}
    with (
        patch("config.settings.get_settings", MagicMock()),
        patch("ui.components.auth.require_auth", lambda: {"role": role}),
    ):
        yield at.run()


def test_admin_has_users_page(service: FakeService) -> None:
    with _app("admin") as at:
        assert not at.exception
        at.switch_page("pages/users.py").run()
        assert not at.exception
        assert any(b.label == "Create user" for b in at.button)


def test_user_has_no_users_page(service: FakeService) -> None:
    titles: list[str] = []
    real = st.navigation

    def spy(pages: list[Any], **kwargs: Any) -> Any:
        titles.extend(page.title for page in pages)
        return real(pages, **kwargs)

    with patch("streamlit.navigation", spy), _app("user") as at:
        assert not at.exception
    assert titles == ["Home"]
    assert service.repos == []
