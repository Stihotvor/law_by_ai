import contextvars
import threading
from collections.abc import Iterator

import pytest

from core.security.principal import (
    PrincipalRequiredError,
    RequestPrincipal,
    get_principal,
    principal_context,
    require_admin_principal,
    reset_principal,
    set_principal,
)


@pytest.fixture(autouse=True)
def _clear_principal() -> Iterator[None]:
    reset_principal()
    yield
    reset_principal()


def test_set_get_and_reset() -> None:
    admin = RequestPrincipal(email="a@x.pl", role="admin")
    assert get_principal() is None

    set_principal(admin)
    assert get_principal() == admin

    reset_principal()
    assert get_principal() is None


def test_context_manager_restores_previous_value_on_exception() -> None:
    a = RequestPrincipal(email="a@x.pl", role="admin")
    b = RequestPrincipal(email="b@x.pl", role="admin")
    set_principal(a)
    seen: list[RequestPrincipal | None] = []

    def run_and_fail() -> None:
        with principal_context(b):
            seen.append(get_principal())
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        run_and_fail()

    assert seen == [b]
    assert get_principal() == a


def test_new_thread_does_not_inherit_principal() -> None:
    set_principal(RequestPrincipal(email="admin@example.com", role="admin"))
    seen: list[RequestPrincipal | None] = []
    errors: list[BaseException] = []

    def work() -> None:
        seen.append(get_principal())
        try:
            require_admin_principal()
        except PrincipalRequiredError as exc:
            errors.append(exc)

    # Run in an empty context: Python 3.14 can let a thread inherit the caller's context.
    thread = threading.Thread(target=contextvars.Context().run, args=(work,))
    thread.start()
    thread.join()

    assert seen == [None]
    assert len(errors) == 1
    assert get_principal() is not None


def test_missing_principal_is_refused() -> None:
    with pytest.raises(PrincipalRequiredError):
        require_admin_principal()


def test_non_admin_is_refused() -> None:
    set_principal(RequestPrincipal(email="u@x.pl", role="user"))
    with pytest.raises(PrincipalRequiredError):
        require_admin_principal()


def test_blank_email_is_refused() -> None:
    set_principal(RequestPrincipal(email="   ", role="admin"))
    with pytest.raises(PrincipalRequiredError):
        require_admin_principal()


def test_admin_passes_with_stripped_email() -> None:
    set_principal(RequestPrincipal(email=" a@x.pl ", role="admin"))
    result = require_admin_principal()
    assert result.email == "a@x.pl"
    assert result.role == "admin"


def test_principal_required_error_is_permission_error() -> None:
    assert issubclass(PrincipalRequiredError, PermissionError)
