"""LLMClient over a real loopback socket: hard deadline and connection reuse."""

import contextlib
import os
import socket
import threading
import time
from collections.abc import Callable, Iterator

import httpcore
import pytest

from config.settings import Settings
from core.llm import client as client_module
from core.llm.client import LLMClient
from core.llm.errors import LLMTimeoutError

_AGENT = "bureaucracy_assistant"
_ONE = [{"role": "user", "content": "private-text"}]
_BODY = b'{"choices":[{"message":{"content":"hello"}}]}'
_OK = b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: %d\r\n\r\n%s" % (
    len(_BODY),
    _BODY,
)
Serve = Callable[[socket.socket], None]


def _read_request(conn: socket.socket) -> bool:
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(65536)
        if not chunk:
            return False
        data += chunk
    head, _, rest = data.partition(b"\r\n\r\n")
    length = 0
    for line in head.split(b"\r\n"):
        if line.lower().startswith(b"content-length:"):
            length = int(line.split(b":")[1])
    while len(rest) < length:
        rest += conn.recv(65536)
    return True


@pytest.fixture
def server(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[[Serve], list[int]]]:
    """Start a loopback server; return the list of accepted connection counts."""
    listener = socket.create_server(("127.0.0.1", 0))
    stop = threading.Event()
    accepted: list[int] = []

    def start(serve: Serve) -> list[int]:
        def loop() -> None:
            listener.settimeout(0.1)
            while not stop.is_set():
                try:
                    conn, _ = listener.accept()
                except TimeoutError:
                    continue
                accepted.append(1)
                with conn, contextlib.suppress(OSError):
                    serve(conn)

        threading.Thread(target=loop, daemon=True).start()
        return accepted

    monkeypatch.setattr("config.settings.load_env", lambda *a, **k: None)
    for name in list(os.environ):
        if name.startswith("LLM_"):
            monkeypatch.delenv(name)
    port = listener.getsockname()[1]
    monkeypatch.setenv("LLM_BASE_URL", f"http://127.0.0.1:{port}/v1")
    monkeypatch.setenv("LLM_MODEL_BUREAUCRACY_ASSISTANT", "m1")
    yield start
    stop.set()
    listener.close()


def _trickle_headers(conn: socket.socket) -> None:
    _read_request(conn)
    for byte in b"HTTP/1.1 200 OK\r\nX-Slow: " + b"a" * 100:
        conn.sendall(bytes([byte]))
        time.sleep(0.05)


def _keep_alive(conn: socket.socket) -> None:
    while _read_request(conn):
        conn.sendall(_OK)


def test_header_trickle_stops_at_deadline(
    server: Callable[[Serve], list[int]], monkeypatch: pytest.MonkeyPatch
) -> None:
    server(_trickle_headers)
    monkeypatch.setenv("LLM_TIMEOUT", "0.5")
    start = time.monotonic()
    with pytest.raises(LLMTimeoutError) as info:
        LLMClient(Settings()).chat(_AGENT, _ONE)
    assert time.monotonic() - start < 0.5 + 0.25
    assert info.value.__cause__ is None
    assert info.value.__context__ is None


def test_calls_reuse_one_connection(server: Callable[[Serve], list[int]]) -> None:
    accepted = server(_keep_alive)
    with LLMClient(Settings()) as client:
        assert [client.chat(_AGENT, _ONE) for _ in range(3)] == ["hello"] * 3
    assert len(accepted) == 1


def test_close_is_idempotent_and_client_reopens(server: Callable[[Serve], list[int]]) -> None:
    server(_keep_alive)
    client = LLMClient(Settings())
    client.close()
    assert client.chat(_AGENT, _ONE) == "hello"
    client.close()
    client.close()
    assert client.chat(_AGENT, _ONE) == "hello"
    client.close()


def test_clip_without_deadline_keeps_timeout() -> None:
    assert client_module._clip(3.0) == 3.0


def test_clip_after_deadline_raises_timeout() -> None:
    token = client_module._deadline.set(time.monotonic() - 1)
    try:
        with pytest.raises(httpcore.ReadTimeout):
            client_module._clip(3.0)
    finally:
        client_module._deadline.reset(token)


def test_clip_shrinks_timeout_to_time_left() -> None:
    token = client_module._deadline.set(time.monotonic() + 1)
    try:
        clipped = client_module._clip(None)
        assert clipped is not None
        assert 0 < clipped <= 1
        assert client_module._clip(0.1) == 0.1
    finally:
        client_module._deadline.reset(token)


class _FakeStream(httpcore.NetworkStream):
    def __init__(self) -> None:
        self.tls_timeout: float | None = None

    def start_tls(
        self, ssl_context: object, server_hostname: str | None = None, timeout: float | None = None
    ) -> httpcore.NetworkStream:
        self.tls_timeout = timeout
        return self


def test_tls_handshake_is_clipped_and_stays_wrapped() -> None:
    inner = _FakeStream()
    token = client_module._deadline.set(time.monotonic() + 1)
    try:
        wrapped = client_module._DeadlineStream(inner).start_tls(object(), "h", 5.0)
    finally:
        client_module._deadline.reset(token)
    assert isinstance(wrapped, client_module._DeadlineStream)
    assert inner.tls_timeout is not None
    assert inner.tls_timeout <= 1
