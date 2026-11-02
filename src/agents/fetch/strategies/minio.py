"""MinIO fetch strategy (S3 compatible object storage)."""

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import urllib3
from minio import Minio
from minio.error import MinioException, S3Error

from agents.fetch.contracts import DocumentFilter, DocumentMeta, DocumentPage, DocumentRef
from agents.fetch.errors import (
    DocumentNotFoundError,
    FetchTransportError,
    InvalidReferenceError,
    ResponseTooLargeError,
    SourceConfigError,
)
from agents.fetch.strategies.base import STRATEGIES
from config.settings import get_settings

_TRANSPORT_ERRORS = (MinioException, urllib3.exceptions.HTTPError)


def _prefix_from(base_url: str) -> str:
    path = urlsplit(base_url).path.lstrip("/")
    if not path or ".." in path.split("/"):
        raise SourceConfigError("base_url needs a path prefix without '..'")
    return path.rstrip("/") + "/"


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _safe_id(external_id: str) -> None:
    segments = external_id.split("/")
    if (
        not external_id
        or "\\" in external_id
        or any(ord(c) < 32 or ord(c) == 127 for c in external_id)
        or any(s in {"", ".", ".."} for s in segments)
    ):
        raise InvalidReferenceError("unsafe external_id")


@STRATEGIES.register("minio")
class MinioStrategy:
    """Reads documents from a MinIO bucket.

    Endpoint, bucket, credentials and the secure flag come from settings. The
    ``base_url`` is only a label: its PATH is the object key prefix
    (``https://minio.local/gov_pl/`` gives ``gov_pl/``). Its scheme and host are
    never used for a connection.
    """

    def __init__(self, base_url: str, *, client: Minio | None = None) -> None:
        self._label = base_url.rstrip("/")
        self._prefix = _prefix_from(base_url)
        settings = get_settings()
        self._bucket = settings.minio_bucket
        if client is None:
            client = self._build_client()
        self._client = client

    @staticmethod
    def _build_client() -> Minio:
        settings = get_settings()
        if not settings.minio_access_key or not settings.minio_secret_key:
            raise SourceConfigError("MinIO credentials are not set")
        timeout = settings.fetch_http_timeout
        return Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
            http_client=urllib3.PoolManager(
                timeout=urllib3.Timeout(connect=timeout, read=timeout),
                retries=urllib3.Retry(total=0),
            ),
        )

    def list_refs(self, source: str, flt: DocumentFilter) -> DocumentPage:
        if flt.cursor is not None and not flt.cursor.startswith(self._prefix):
            raise InvalidReferenceError("cursor outside the source prefix")
        keys: list[str] = []
        more = False
        try:
            for obj in self._client.list_objects(
                self._bucket,
                prefix=self._prefix,
                recursive=True,
                start_after=flt.cursor or None,
            ):
                if not self._matches(obj, flt):
                    continue
                if len(keys) == flt.limit:
                    more = True
                    break
                keys.append(str(obj.object_name))
        except _TRANSPORT_ERRORS as exc:
            raise self._transport_error("list", self._prefix, exc) from exc
        refs = tuple(self._ref(source, key[len(self._prefix) :]) for key in keys)
        return DocumentPage(items=refs, next_cursor=keys[-1] if more else None)

    def _matches(self, obj: Any, flt: DocumentFilter) -> bool:
        name: str = obj.object_name
        if obj.is_dir or name.endswith("/"):
            return False
        if flt.keyword and flt.keyword.lower() not in name[len(self._prefix) :].lower():
            return False
        if flt.date_from is None and flt.date_to is None:
            return True
        if obj.last_modified is None:
            return False
        modified = _aware(obj.last_modified)
        if flt.date_from is not None and modified < flt.date_from:
            return False
        return flt.date_to is None or modified <= flt.date_to

    def _ref(self, source: str, external_id: str) -> DocumentRef:
        return DocumentRef(
            source=source, external_id=external_id, url=self._label + "/" + external_id
        )

    def get_meta(self, ref: DocumentRef) -> DocumentMeta:
        key = self._key(ref.external_id)
        try:
            stat = self._client.stat_object(self._bucket, key)
        except S3Error as exc:
            raise self._s3_error("stat", key, exc) from exc
        except _TRANSPORT_ERRORS as exc:
            raise self._transport_error("stat", key, exc) from exc
        return DocumentMeta(
            ref=ref,
            title=ref.external_id.rsplit("/", 1)[-1],
            doc_type=None,
            published_at=_aware(stat.last_modified) if stat.last_modified else None,
            language=None,
            extra={
                "content_type": stat.content_type,
                "size": stat.size,
                "etag": stat.etag,
            },
        )

    def read(self, ref: DocumentRef) -> bytes:
        key = self._key(ref.external_id)
        max_bytes = get_settings().fetch_max_bytes
        try:
            response = self._client.get_object(self._bucket, key)
            try:
                data: bytes = response.read(max_bytes + 1)
            finally:
                response.close()
                response.release_conn()
        except S3Error as exc:
            raise self._s3_error("get", key, exc) from exc
        except _TRANSPORT_ERRORS as exc:
            raise self._transport_error("get", key, exc) from exc
        if len(data) > max_bytes:
            raise ResponseTooLargeError(f"get {key}: body larger than {max_bytes} bytes")
        return data

    def _key(self, external_id: str) -> str:
        _safe_id(external_id)
        return self._prefix + external_id

    def _s3_error(self, op: str, key: str, exc: S3Error) -> Exception:
        if exc.code == "NoSuchKey":
            return DocumentNotFoundError(f"{op} {key}: not found")
        return self._transport_error(op, key, exc)

    @staticmethod
    def _transport_error(op: str, key: str, exc: Exception) -> FetchTransportError:
        code = getattr(exc, "code", None) or type(exc).__name__
        return FetchTransportError(f"{op} {key}: {code}")
