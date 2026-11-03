import socket
from typing import Any, NoReturn

import pytest


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*args: Any, **kwargs: Any) -> NoReturn:
        raise AssertionError("network")

    monkeypatch.setattr(socket.socket, "connect", _blocked)


@pytest.fixture
def settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FETCH_HTTP_TIMEOUT", "3.5")
    monkeypatch.setenv("FETCH_MAX_BYTES", "100")
    monkeypatch.setenv("MINIO_ENDPOINT", "minio.test:9000")
    monkeypatch.setenv("MINIO_ACCESS_KEY", "test-access")
    monkeypatch.setenv("MINIO_SECRET_KEY", "test-secret-value")
    monkeypatch.setenv("MINIO_BUCKET", "test-bucket")
    monkeypatch.setenv("MINIO_SECURE", "true")
