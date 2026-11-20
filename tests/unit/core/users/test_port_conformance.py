"""The UserRepository port and its implementations must not drift apart.

Compares signatures with ``inspect`` only. No DB connection is opened.
"""

from __future__ import annotations

import importlib.util
import inspect
import typing
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from core.users import UserRecord, UserRepository
from plugins.relational_db.postgres import PostgreSQLStore

SERVICE_TESTS = Path(__file__).with_name("test_service.py")


def _load_fake_repo() -> type:
    """Load the FakeRepo that the service unit tests use."""
    spec = importlib.util.spec_from_file_location("_users_service_tests", SERVICE_TESTS)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.FakeRepo


def port_methods() -> list[str]:
    """Names of the methods declared on the port."""
    return sorted(typing.get_protocol_members(UserRepository))


def _params(fn: Callable[..., Any]) -> list[tuple[str, Any, Any]]:
    sig = inspect.signature(fn)
    return [(p.name, p.kind, p.default) for p in sig.parameters.values()]


def signature_mismatches(port_fn: Callable[..., Any], impl_fn: Callable[..., Any]) -> list[str]:
    """Differences in parameter names, kinds, defaults, and resolved type hints."""
    problems: list[str] = []
    port_params, impl_params = _params(port_fn), _params(impl_fn)
    if port_params != impl_params:
        problems.append(f"parameters: port={port_params} impl={impl_params}")
    port_hints, impl_hints = typing.get_type_hints(port_fn), typing.get_type_hints(impl_fn)
    if port_hints != impl_hints:
        problems.append(f"annotations: port={port_hints} impl={impl_hints}")
    return problems


def conformance_report(impl: type) -> dict[str, list[str]]:
    """Map each port method to its problems on *impl*; empty when it conforms."""
    report: dict[str, list[str]] = {}
    for name in port_methods():
        impl_fn = getattr(impl, name, None)
        if not callable(impl_fn):
            report[name] = ["missing"]
            continue
        problems = signature_mismatches(getattr(UserRepository, name), impl_fn)
        if problems:
            report[name] = problems
    return report


def test_port_declares_expected_methods() -> None:
    assert port_methods() == ["deactivate_user", "find_active_admin", "insert_user", "list_users"]


# Scenario: Signatures match
@pytest.mark.parametrize("impl", [PostgreSQLStore, _load_fake_repo()], ids=["store", "fake"])
def test_signatures_match(impl: type) -> None:
    assert conformance_report(impl) == {}


class _RenamedParamStore:
    def find_active_admin(self, email: str) -> UserRecord | None: ...

    def insert_user(
        self, *, email: str, password_hash: str, role: str, name: str, actor_id: str
    ) -> UserRecord:
        raise NotImplementedError

    def list_users(self) -> list[UserRecord]:
        return []

    def deactivate_user(self, user_id: str, *, actor: str) -> bool:
        return False


class _DriftedStore:
    def find_active_admin(self, email: str, strict: bool = False) -> UserRecord | None: ...

    def insert_user(self, email: str, password_hash: str, role: str, name: str) -> UserRecord:
        raise NotImplementedError

    def list_users(self) -> list[dict[str, Any]]:
        return []


# Scenario: Drift is detected
def test_renamed_parameter_is_reported() -> None:
    report = conformance_report(_RenamedParamStore)

    assert list(report) == ["deactivate_user"]
    assert "actor" in report["deactivate_user"][0]


def test_mutated_store_signature_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    def deactivate_user(self: Any, user_id: str, *, actor: str) -> bool:
        return False

    monkeypatch.setattr(PostgreSQLStore, "deactivate_user", deactivate_user)

    assert list(conformance_report(PostgreSQLStore)) == ["deactivate_user"]


def test_other_drift_is_reported() -> None:
    report = conformance_report(_DriftedStore)

    assert report["deactivate_user"] == ["missing"]
    assert any("parameters" in p for p in report["find_active_admin"])
    assert any("parameters" in p for p in report["insert_user"])
    assert len(report["list_users"]) == 1
    assert report["list_users"][0].startswith("annotations")
