"""Fakes for the init program: settings, store and S3 client."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.exc import IntegrityError

STRONG = "a-long-admin-secret"
STRONG_PG = "pg-strong-secret"
STRONG_S3 = "s3-strong-secret"
STRONG_REDIS = "redis-strong-secret"


@dataclass
class FakeSettings:
    """Settings stub with valid values for every field init reads."""

    postgres_password: str = STRONG_PG
    redis_password: str = STRONG_REDIS
    postgres_url: str = "sqlite://"
    minio_endpoint: str = "s3:8333"
    minio_access_key: str = "init-access"
    minio_secret_key: str = STRONG_S3
    minio_bucket: str = "legal-documents"
    minio_secure: bool = False
    init_tenant_id: str = "platform"
    init_tenant_name: str = "Platform"
    init_admin_email: str = "admin@example.com"
    init_admin_name: str = "Admin"
    init_admin_password: str = STRONG


def integrity_error() -> IntegrityError:
    return IntegrityError("INSERT", {}, Exception("duplicate key"))


@dataclass
class FakeStore:
    """In-memory store. ``fail`` maps a method name to the error it always raises.

    ``errors`` maps a method name to errors raised one per call, then the call works.
    """

    revision: str | None = None
    tenants: dict[str, str] = field(default_factory=dict)
    users: dict[str, dict[str, Any]] = field(default_factory=dict)
    fail: dict[str, Exception] = field(default_factory=dict)
    errors: dict[str, list[Exception]] = field(default_factory=dict)
    revision_errors: list[Exception] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)

    def _call(self, name: str) -> None:
        self.calls.append(name)
        if name in self.fail:
            raise self.fail[name]
        if self.errors.get(name):
            raise self.errors[name].pop(0)

    def current_revision(self) -> str | None:
        self.calls.append("current_revision")
        if self.revision_errors:
            raise self.revision_errors.pop(0)
        return self.revision

    def initialize(self) -> None:
        self._call("initialize")
        self.revision = "head"

    def list_tenants(self) -> list[dict[str, Any]]:
        self._call("list_tenants")
        return [{"id": k, "name": v} for k, v in self.tenants.items()]

    def create_tenant(self, name: str, tenant_id: str | None = None) -> dict[str, Any]:
        self._call("create_tenant")
        self.tenants[str(tenant_id)] = name
        return {"id": tenant_id, "name": name}

    def get_user_by_email(self, email: str) -> dict[str, Any] | None:
        self._call("get_user_by_email")
        return self.users.get(email)

    def create_user(
        self, *, email: str, password: str, role: str, tenant_id: str, name: str = ""
    ) -> dict[str, Any]:
        self._call("create_user")
        user = {"email": email, "password": password, "role": role}
        user |= {"tenant_id": tenant_id, "name": name, "is_active": True}
        self.users[email] = user
        return user


@dataclass
class FakeBucket:
    """S3 client stub. ``exists_errors`` and ``make_errors`` are raised one per call."""

    buckets: set[str] = field(default_factory=set)
    exists_errors: list[Exception] = field(default_factory=list)
    make_error: Exception | None = None
    make_errors: list[Exception] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)

    def bucket_exists(self, bucket_name: str) -> bool:
        self.calls.append("bucket_exists")
        if self.exists_errors:
            raise self.exists_errors.pop(0)
        return bucket_name in self.buckets

    def make_bucket(self, bucket_name: str) -> None:
        self.calls.append("make_bucket")
        if self.make_error is not None:
            raise self.make_error
        if self.make_errors:
            raise self.make_errors.pop(0)
        self.buckets.add(bucket_name)
