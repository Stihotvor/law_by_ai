"""UserService rules, checked against a fake UserRepository."""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from core.security import (
    PrincipalRequiredError,
    RequestPrincipal,
    check_password,
    principal_context,
    tenant_context,
)
from core.security.passwords import MAX_PASSWORD_BYTES, MIN_PASSWORD_CHARS
from core.users import (
    LastAdminError,
    SelfDeactivationError,
    UserCreateRefusedError,
    UserNotFoundError,
    UserRecord,
    UserService,
)

TENANT = "t1"
GOOD_PASSWORD = "correct-horse-1"  # noqa: S105
SHORT_PASSWORD = "short-pw"  # noqa: S105


def _record(user_id: str, email: str, role: str = "user") -> UserRecord:
    return UserRecord(id=user_id, tenant_id=TENANT, email=email, role=role, name="", is_active=True)


class FakeRepo:
    """In-memory UserRepository that records every call."""

    def __init__(self, admin: UserRecord | None = None) -> None:
        self.admin: UserRecord | None = admin or _record("A1", "a@x.pl", "admin")
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.writes: list[tuple[str, dict[str, Any]]] = []
        self.deactivate_result: bool | Exception = True

    def find_active_admin(self, email: str) -> UserRecord | None:
        self.calls.append(("find_active_admin", {"email": email}))
        if self.admin is None or self.admin["email"] != email:
            return None
        return self.admin

    def insert_user(self, *, email: str, password_hash: str, role: str, name: str) -> UserRecord:
        args = {"email": email, "password_hash": password_hash, "role": role, "name": name}
        self.calls.append(("insert_user", args))
        self.writes.append(("insert_user", args))
        return UserRecord(
            id="U9", tenant_id=TENANT, email=email, role=role, name=name, is_active=True
        )

    def list_users(self) -> list[UserRecord]:
        self.calls.append(("list_users", {}))
        return [self.admin] if self.admin else []

    def deactivate_user(self, user_id: str, *, actor_id: str) -> bool:
        args = {"user_id": user_id, "actor_id": actor_id}
        self.calls.append(("deactivate_user", args))
        if isinstance(self.deactivate_result, Exception):
            raise self.deactivate_result
        self.writes.append(("deactivate_user", args))
        return self.deactivate_result


@pytest.fixture(autouse=True)
def _fast_bcrypt(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BCRYPT_ROUNDS", "4")


@pytest.fixture
def repo() -> FakeRepo:
    return FakeRepo()


@pytest.fixture
def service(repo: FakeRepo) -> UserService:
    return UserService(repo)


@pytest.fixture
def as_admin() -> Iterator[None]:
    with tenant_context(TENANT), principal_context(RequestPrincipal(" A@X.pl ", "admin")):
        yield


def _create(service: UserService, **overrides: str) -> UserRecord:
    args = {"email": "new@x.pl", "password": GOOD_PASSWORD, "role": "user", "name": "N"}
    args.update(overrides)
    return service.create_user(**args)


CALLS: dict[str, Callable[[UserService], object]] = {
    "create": _create,
    "deactivate": lambda s: s.deactivate_user("U2"),
    "list": lambda s: s.list_users(),
}


# Scenario: Role user is refused
@pytest.mark.parametrize("call", ["create", "deactivate"])
def test_role_user_is_refused(service: UserService, repo: FakeRepo, call: str) -> None:
    principal = RequestPrincipal("a@x.pl", "user")
    with (
        tenant_context(TENANT),
        principal_context(principal),
        pytest.raises(PrincipalRequiredError),
    ):
        CALLS[call](service)
    assert repo.writes == []


def test_no_principal_is_refused(service: UserService, repo: FakeRepo) -> None:
    with tenant_context(TENANT), pytest.raises(PrincipalRequiredError):
        service.list_users()
    assert repo.calls == []


# Scenario: Empty tenant
@pytest.mark.parametrize("tenant", [None, ""])
@pytest.mark.parametrize("call", sorted(CALLS))
def test_empty_tenant_refused_before_port(
    service: UserService, repo: FakeRepo, call: str, tenant: str | None
) -> None:
    principal = RequestPrincipal("a@x.pl", "admin")
    with (
        tenant_context(tenant),
        principal_context(principal),
        pytest.raises(PrincipalRequiredError),
    ):
        CALLS[call](service)
    assert repo.calls == []


# Scenario: Actor is not an active admin
@pytest.mark.parametrize("call", sorted(CALLS))
@pytest.mark.usefixtures("as_admin")
def test_actor_not_active_admin(call: str) -> None:
    repo = FakeRepo()
    repo.admin = None
    with pytest.raises(PrincipalRequiredError):
        CALLS[call](UserService(repo))
    assert [name for name, _ in repo.calls] == ["find_active_admin"]


@pytest.mark.usefixtures("as_admin")
def test_actor_lookup_uses_normalised_principal_email(service: UserService, repo: FakeRepo) -> None:
    service.list_users()
    assert repo.calls[0] == ("find_active_admin", {"email": "a@x.pl"})


# Scenario: Invalid input
@pytest.mark.parametrize(
    "overrides",
    [
        {"role": "root"},
        {"role": ""},
        {"email": ""},
        {"email": "   "},
        {"email": "no-at.pl"},
        {"email": "a@@x.pl"},
        {"email": "a" * 252 + "@x.pl"},
        {"name": "n" * 257},
        {"password": "p" * 11},
        {"password": "ą" * 36 + "p"},
    ],
)
@pytest.mark.usefixtures("as_admin")
def test_invalid_input_refused(
    service: UserService, repo: FakeRepo, overrides: dict[str, str]
) -> None:
    with pytest.raises(UserCreateRefusedError):
        _create(service, **overrides)
    assert repo.writes == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"email": "a" * 251 + "@x.pl"},
        {"name": "n" * 256},
        {"password": "p" * 12},
        {"password": "ą" * 36},
    ],
)
@pytest.mark.usefixtures("as_admin")
def test_limits_are_inclusive(
    service: UserService, repo: FakeRepo, overrides: dict[str, str]
) -> None:
    _create(service, **overrides)
    assert len(repo.writes) == 1


# QA-017: the password limit counts UTF-8 bytes, not characters
@pytest.mark.parametrize(
    "password",
    ["p" * MAX_PASSWORD_BYTES, "ł" * (MAX_PASSWORD_BYTES // 2), "€" * (MAX_PASSWORD_BYTES // 3)],
    ids=["ascii-72-chars", "2-byte-36-chars", "3-byte-24-chars"],
)
@pytest.mark.usefixtures("as_admin")
def test_password_of_72_bytes_is_accepted(
    service: UserService, repo: FakeRepo, password: str
) -> None:
    assert len(password.encode()) == MAX_PASSWORD_BYTES
    _create(service, password=password)
    assert check_password(password, repo.writes[0][1]["password_hash"])


@pytest.mark.parametrize(
    "password",
    ["p" * (MAX_PASSWORD_BYTES + 1), "ł" * (MAX_PASSWORD_BYTES // 2) + "p", "ł" * 37],
    ids=["ascii-73-chars", "2-byte-37-chars-73-bytes", "2-byte-37-chars-74-bytes"],
)
@pytest.mark.usefixtures("as_admin")
def test_password_over_72_bytes_is_refused(
    service: UserService, repo: FakeRepo, password: str
) -> None:
    assert len(password.encode()) > MAX_PASSWORD_BYTES
    with pytest.raises(UserCreateRefusedError):
        _create(service, password=password)
    assert repo.writes == []


@pytest.mark.usefixtures("as_admin")
def test_admin_role_is_accepted(service: UserService, repo: FakeRepo) -> None:
    _create(service, role="admin")
    assert repo.writes[0][1]["role"] == "admin"


# Scenario: Email is normalised
@pytest.mark.usefixtures("as_admin")
def test_email_normalised_and_password_hashed(service: UserService, repo: FakeRepo) -> None:
    result = _create(service, email="  A@X2.PL ")
    _, args = repo.writes[0]
    assert args["email"] == "a@x2.pl"
    assert args["password_hash"] != GOOD_PASSWORD
    assert args["password_hash"].startswith("$2")
    assert check_password(GOOD_PASSWORD, args["password_hash"])
    assert (args["role"], args["name"]) == ("user", "N")
    assert result["id"] == "U9"
    assert "password_hash" not in result


# QA-009: case and surrounding spaces are removed before the port sees the email
@pytest.mark.usefixtures("as_admin")
def test_email_case_and_spaces_normalised_before_port(service: UserService, repo: FakeRepo) -> None:
    _create(service, email=" A@B.com ")
    assert [args["email"] for name, args in repo.calls if name == "insert_user"] == ["a@b.com"]


@pytest.mark.usefixtures("as_admin")
def test_duplicate_from_port_propagates(service: UserService, repo: FakeRepo) -> None:
    def refuse(**_: str) -> UserRecord:
        raise UserCreateRefusedError("taken")

    repo.insert_user = refuse  # type: ignore[method-assign]
    with pytest.raises(UserCreateRefusedError):
        _create(service)


# Scenario: Actor id goes to the port
@pytest.mark.usefixtures("as_admin")
def test_actor_id_goes_to_port(service: UserService, repo: FakeRepo) -> None:
    assert service.deactivate_user("U2") is True
    assert repo.writes == [("deactivate_user", {"user_id": "U2", "actor_id": "A1"})]


@pytest.mark.parametrize(
    "error", [UserNotFoundError, SelfDeactivationError, LastAdminError, PrincipalRequiredError]
)
@pytest.mark.usefixtures("as_admin")
def test_port_errors_propagate(
    service: UserService, repo: FakeRepo, error: type[Exception]
) -> None:
    repo.deactivate_result = error("x")
    with pytest.raises(error):
        service.deactivate_user("U2")


@pytest.mark.usefixtures("as_admin")
def test_list_users_returns_port_records(service: UserService, repo: FakeRepo) -> None:
    assert repo.admin is not None
    assert service.list_users() == [repo.admin]


# Scenario: Logs and audit
_EXTRA_KEYS = ("actor_id", "target_id", "action", "changed", "error")


def _extras(record: logging.LogRecord) -> dict[str, Any]:
    """Return the ``extra`` fields of *record* that the service sets."""
    return {key: record.__dict__[key] for key in _EXTRA_KEYS if key in record.__dict__}


def _with_action(records: list[logging.LogRecord], action: str) -> list[dict[str, Any]]:
    return [_extras(r) for r in records if _extras(r).get("action") == action]


def _dumped(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [repr(r.__dict__) + r.getMessage() for r in caplog.records]


@pytest.mark.usefixtures("as_admin")
def test_logs_hold_no_password_or_hash(
    service: UserService, repo: FakeRepo, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    _create(service)
    service.deactivate_user("U2")
    password_hash = repo.writes[0][1]["password_hash"]
    assert not any(GOOD_PASSWORD in t or password_hash in t for t in _dumped(caplog))


@pytest.mark.usefixtures("as_admin")
def test_audit_holds_actor_target_and_change(
    service: UserService, repo: FakeRepo, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    _create(service)
    repo.deactivate_result = False
    service.deactivate_user("U2")
    assert _with_action(caplog.records, "create_user") == [
        {"actor_id": "A1", "target_id": "U9", "action": "create_user", "changed": True}
    ]
    assert _with_action(caplog.records, "deactivate_user") == [
        {"actor_id": "A1", "target_id": "U2", "action": "deactivate_user", "changed": False}
    ]


@pytest.mark.usefixtures("as_admin")
def test_failed_deactivate_emits_no_audit(
    service: UserService, repo: FakeRepo, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    repo.deactivate_result = LastAdminError("x")
    with pytest.raises(LastAdminError):
        service.deactivate_user("U2")
    assert not [r for r in caplog.records if "target_id" in r.__dict__]


# Scenario: Refusals are logged
def _refusals(caplog: pytest.LogCaptureFixture) -> list[dict[str, Any]]:
    return [_extras(r) for r in caplog.records if r.levelno == logging.WARNING]


@pytest.mark.parametrize(
    "error", [UserNotFoundError, SelfDeactivationError, LastAdminError, PrincipalRequiredError]
)
@pytest.mark.usefixtures("as_admin")
def test_port_refusal_is_logged_with_actor(
    service: UserService, repo: FakeRepo, caplog: pytest.LogCaptureFixture, error: type[Exception]
) -> None:
    repo.deactivate_result = error("detail-U2")
    with pytest.raises(error):
        service.deactivate_user("U2")
    assert _refusals(caplog) == [
        {"actor_id": "A1", "action": "deactivate_user", "error": error.__name__}
    ]
    assert not any("detail-U2" in text for text in _dumped(caplog))


def test_principal_refusal_is_logged_without_actor(
    service: UserService, caplog: pytest.LogCaptureFixture
) -> None:
    with (
        tenant_context(TENANT),
        principal_context(RequestPrincipal("a@x.pl", "user")),
        pytest.raises(PrincipalRequiredError),
    ):
        _create(service)
    assert _refusals(caplog) == [
        {"actor_id": None, "action": "create_user", "error": "PrincipalRequiredError"}
    ]


@pytest.mark.usefixtures("as_admin")
def test_create_refusal_log_holds_no_email_or_password(
    service: UserService, caplog: pytest.LogCaptureFixture
) -> None:
    with pytest.raises(UserCreateRefusedError):
        _create(service, email="secret-mail@x.pl", password=SHORT_PASSWORD)
    assert _refusals(caplog) == [
        {"actor_id": "A1", "action": "create_user", "error": "UserCreateRefusedError"}
    ]
    dumped = _dumped(caplog)
    assert not any("secret-mail" in t or SHORT_PASSWORD in t for t in dumped)


# QA-041: a duplicate refusal logs a WARNING without password, hash or email
@pytest.mark.usefixtures("as_admin")
def test_duplicate_refusal_log_holds_no_password_hash_or_email(
    service: UserService, repo: FakeRepo, caplog: pytest.LogCaptureFixture
) -> None:
    hashes: list[str] = []

    def refuse(*, email: str, password_hash: str, role: str, name: str) -> UserRecord:
        hashes.append(password_hash)
        raise UserCreateRefusedError(f"email {email} taken")

    repo.insert_user = refuse  # type: ignore[method-assign]
    caplog.set_level(logging.DEBUG)
    with pytest.raises(UserCreateRefusedError):
        _create(service, email="dup-mail@x.pl")
    assert _refusals(caplog) == [
        {"actor_id": "A1", "action": "create_user", "error": "UserCreateRefusedError"}
    ]
    assert len(hashes) == 1
    secrets = (GOOD_PASSWORD, hashes[0], "dup-mail", "$2")
    assert not any(s in t for t in _dumped(caplog) for s in secrets)


@pytest.mark.usefixtures("as_admin")
def test_password_rule_names_the_limits(service: UserService) -> None:
    with pytest.raises(UserCreateRefusedError) as caught:
        _create(service, password=SHORT_PASSWORD)
    assert str(MIN_PASSWORD_CHARS) in str(caught.value)
    assert str(MAX_PASSWORD_BYTES) in str(caught.value)
