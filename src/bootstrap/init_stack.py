"""Init program: bring a fresh stack to a known state.

Steps run in order: schema, bucket, tenant, admin. Each step checks state
first, so a second run creates nothing. Existing data is never changed.

Exit codes: 0 done, 2 invalid configuration, 3 Postgres or S3 unreachable
after retries, 4 a step failed. Logs never hold secrets or URLs.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any, Literal, Protocol

import urllib3
from alembic.runtime.migration import MigrationContext
from minio import Minio
from minio.error import S3Error, ServerError
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError, OperationalError

from config.settings import get_settings
from core.security import ADMIN
from plugins.relational_db.postgres import PostgreSQLStore

_log = logging.getLogger(__name__)

OK, BAD_CONFIG, UNREACHABLE, STEP_FAILED = 0, 2, 3, 4
TRIES = 5
PLACEHOLDER = "change-me"
MIN_PASSWORD_CHARS = 12
MAX_PASSWORD_BYTES = 72  # bcrypt limit
Transient = tuple[type[Exception], ...]
PG_DOWN: Transient = (OperationalError,)
S3_DOWN: Transient = (urllib3.exceptions.HTTPError, ServerError)

Result = Literal["created", "exists"]
Sleep = Callable[[float], None]


class Unreachable(Exception):
    """A service did not answer after all tries."""


class InitSettings(Protocol):
    @property
    def postgres_password(self) -> str: ...
    @property
    def redis_password(self) -> str: ...
    @property
    def postgres_url(self) -> str: ...
    @property
    def minio_endpoint(self) -> str: ...
    @property
    def minio_access_key(self) -> str: ...
    @property
    def minio_secret_key(self) -> str: ...
    @property
    def minio_bucket(self) -> str: ...
    @property
    def minio_secure(self) -> bool: ...
    @property
    def init_tenant_id(self) -> str: ...
    @property
    def init_tenant_name(self) -> str: ...
    @property
    def init_admin_email(self) -> str: ...
    @property
    def init_admin_name(self) -> str: ...
    @property
    def init_admin_password(self) -> str: ...


class Store(Protocol):
    def initialize(self) -> None: ...
    def list_tenants(self) -> list[dict[str, Any]]: ...
    def create_tenant(self, name: str, tenant_id: str | None = None) -> dict[str, Any]: ...
    def get_user_by_email(self, email: str) -> dict[str, Any] | None: ...
    def create_user(
        self, *, email: str, password: str, role: str, tenant_id: str, name: str = ""
    ) -> dict[str, Any]: ...


class Bucket(Protocol):
    def bucket_exists(self, bucket_name: str) -> bool: ...
    def make_bucket(self, bucket_name: str) -> None: ...


def validate_config(s: InitSettings) -> list[str]:
    """Return config problems. Messages name variables, never values."""
    required = {
        "MINIO_ENDPOINT": s.minio_endpoint,
        "MINIO_ACCESS_KEY": s.minio_access_key,
        "MINIO_SECRET_KEY": s.minio_secret_key,
        "MINIO_BUCKET": s.minio_bucket,
        "INIT_TENANT_ID": s.init_tenant_id,
        "INIT_TENANT_NAME": s.init_tenant_name,
    }
    secrets = {
        "INIT_ADMIN_PASSWORD": s.init_admin_password,
        "POSTGRES_PASSWORD": s.postgres_password,
        "MINIO_SECRET_KEY": s.minio_secret_key,
        "REDIS_PASSWORD": s.redis_password,
    }
    problems = [f"{name} is empty" for name, value in required.items() if not value]
    if "@" not in s.init_admin_email:
        problems.append("INIT_ADMIN_EMAIL has no @")
    password = s.init_admin_password
    if len(password) < MIN_PASSWORD_CHARS or len(password.encode()) > MAX_PASSWORD_BYTES:
        problems.append("INIT_ADMIN_PASSWORD needs 12 or more characters and 72 or fewer bytes")
    placeholders = [n for n, v in secrets.items() if v.lower().startswith(PLACEHOLDER)]
    problems += [f"{name} starts with {PLACEHOLDER}" for name in placeholders]
    return problems


def retry[T](call: Callable[[], T], transient: Transient, sleep: Sleep) -> T:
    """Call up to TRIES times, sleeping 1 s, 2 s, 4 s, ... between transient errors."""
    for attempt in range(TRIES - 1):
        try:
            return call()
        except transient:
            sleep(2.0**attempt)
    try:
        return call()
    except transient as exc:
        raise Unreachable(type(exc).__name__) from None


def db_revision(url: str) -> str | None:
    """Return the Alembic revision of the database, or None before migrations."""
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            return MigrationContext.configure(conn).get_current_revision()
    finally:
        engine.dispose()


def ensure_schema(store: Store, revision: Callable[[], str | None]) -> Result:
    before = revision()
    store.initialize()
    return "created" if revision() != before else "exists"


def ensure_bucket(client: Bucket, bucket: str) -> Result:
    if client.bucket_exists(bucket):
        return "exists"
    try:
        client.make_bucket(bucket)
    except S3Error as exc:
        if exc.code != "BucketAlreadyOwnedByYou":
            raise
        return "exists"
    return "created"


def ensure_tenant(store: Store, tenant_id: str, name: str) -> Result:
    if any(t["id"] == tenant_id for t in store.list_tenants()):
        return "exists"
    try:
        store.create_tenant(name, tenant_id=tenant_id)
    except IntegrityError:
        return "exists"
    return "created"


def ensure_admin(store: Store, s: InitSettings) -> Result:
    user = store.get_user_by_email(s.init_admin_email)
    if user is not None:
        if user["role"] != ADMIN or not user["is_active"]:
            _log.warning("step=admin existing user is not an active admin; not changed")
        return "exists"
    try:
        store.create_user(
            email=s.init_admin_email,
            password=s.init_admin_password,
            role=ADMIN,
            tenant_id=s.init_tenant_id,
            name=s.init_admin_name,
        )
    except IntegrityError:
        return "exists"
    return "created"


def _run_step(name: str, step: Callable[[], Result], transient: Transient, sleep: Sleep) -> int:
    try:
        # Safe to re-run a whole step: it checks state first and treats a race as "exists".
        result = retry(step, transient, sleep)
    except Unreachable as exc:
        _log.error("step=%s result=failed reason=unreachable error=%s", name, exc)
        return UNREACHABLE
    except Exception as exc:
        _log.error("step=%s result=failed error=%s", name, type(exc).__name__)
        return STEP_FAILED
    _log.info("step=%s result=%s", name, result)
    return OK


def s3_client(s: InitSettings) -> Minio:
    """Build an S3 client without its own retries, so `retry` owns the backoff."""
    pool = urllib3.PoolManager(
        timeout=urllib3.Timeout(connect=5.0, read=30.0), retries=urllib3.Retry(total=0)
    )
    return Minio(
        s.minio_endpoint,
        access_key=s.minio_access_key,
        secret_key=s.minio_secret_key,
        secure=s.minio_secure,
        http_client=pool,
    )


def run(
    settings: InitSettings,
    store: Store,
    client: Bucket | None = None,
    *,
    revision: Callable[[], str | None] | None = None,
    sleep: Sleep = time.sleep,
) -> int:
    """Run every step in order and return the exit code."""
    if problems := validate_config(settings):
        _log.error("step=config result=failed problems=%s", "; ".join(problems))
        return BAD_CONFIG
    s3 = client if client is not None else s3_client(settings)
    current = revision or (lambda: db_revision(settings.postgres_url))
    steps: tuple[tuple[str, Callable[[], Result], Transient], ...] = (
        ("schema", lambda: ensure_schema(store, current), PG_DOWN),
        ("bucket", lambda: ensure_bucket(s3, settings.minio_bucket), S3_DOWN),
        (
            "tenant",
            lambda: ensure_tenant(store, settings.init_tenant_id, settings.init_tenant_name),
            PG_DOWN,
        ),
        ("admin", lambda: ensure_admin(store, settings), PG_DOWN),
    )
    for name, step, transient in steps:
        if code := _run_step(name, step, transient, sleep):
            return code
    return OK


def main() -> int:
    logging.basicConfig(format="%(levelname)s %(name)s %(message)s")
    _log.setLevel(logging.INFO)
    store = PostgreSQLStore()
    try:
        return run(get_settings(), store)
    finally:
        store.close()
