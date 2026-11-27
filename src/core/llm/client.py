"""OpenAI-compatible chat client. No logging here: key and content must not leak.

Errors are raised outside ``except`` blocks so they carry no cause or context
that could hold the request URL, the key or the messages.
"""

import json
import time
from contextvars import ContextVar
from types import TracebackType
from typing import Self, cast

import httpcore
import httpx

from config.settings import Settings
from core.llm.config import resolve
from core.llm.errors import LLMError, LLMTimeoutError

__all__ = ["LLMClient"]

_MAX_RESPONSE_BYTES = 1024 * 1024
# httpx applies its timeout per phase (connect, write, pool, each read).
_HTTPX_PHASES = 4
_now = time.monotonic
_WRITE_SLICE = 4096
# Deadline of the call in progress in this thread, read by every socket operation.
_deadline: ContextVar[float | None] = ContextVar("llm_deadline", default=None)


def _clip(timeout: float | None) -> float | None:
    """Shrink a socket timeout to the time left before the call deadline."""
    deadline = _deadline.get()
    if deadline is None:
        return timeout
    left = deadline - _now()
    if left <= 0:
        raise httpcore.ReadTimeout("deadline passed")
    return left if timeout is None else min(timeout, left)


class _DeadlineStream(httpcore.NetworkStream):
    """Socket stream whose reads and writes end at the call deadline.

    httpx applies its timeout to each socket read, so a server that sends the
    headers one byte at a time is not stopped. Here each read gets only the time left.
    """

    def __init__(self, stream: httpcore.NetworkStream) -> None:
        self._stream = stream

    def read(self, max_bytes: int, timeout: float | None = None) -> bytes:
        return self._stream.read(max_bytes, _clip(timeout))

    def write(self, buffer: bytes, timeout: float | None = None) -> None:
        # httpcore reuses one timeout for every partial send, so a peer that reads
        # slowly could hold a large body past the deadline. Small slices re-clip often.
        for start in range(0, len(buffer), _WRITE_SLICE):
            self._stream.write(buffer[start : start + _WRITE_SLICE], _clip(timeout))

    def close(self) -> None:
        self._stream.close()

    def start_tls(
        self, ssl_context: object, server_hostname: str | None = None, timeout: float | None = None
    ) -> httpcore.NetworkStream:
        stream = self._stream.start_tls(ssl_context, server_hostname, _clip(timeout))  # type: ignore[arg-type]
        return _DeadlineStream(stream)

    def get_extra_info(self, info: str) -> object:
        return self._stream.get_extra_info(info)


class _DeadlineBackend(httpcore.SyncBackend):
    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: object = None,
    ) -> httpcore.NetworkStream:
        stream = super().connect_tcp(host, port, _clip(timeout), local_address, socket_options)  # type: ignore[arg-type]
        return _DeadlineStream(stream)


def _deadline_transport() -> httpx.HTTPTransport:
    transport = httpx.HTTPTransport(trust_env=False)
    # httpx takes no network backend argument, so the pool is rebuilt with one.
    transport._pool = httpcore.ConnectionPool(  # pyright: ignore[reportPrivateUsage]
        ssl_context=httpx.create_ssl_context(trust_env=False),
        network_backend=_DeadlineBackend(),
    )
    return transport


def _check_deadline(deadline: float) -> None:
    if _now() > deadline:
        raise LLMTimeoutError("LLM request timed out")


def _read_capped(response: httpx.Response, deadline: float) -> bytes:
    chunks: list[bytes] = []
    total = 0
    stream = response.iter_bytes()
    while True:
        _check_deadline(deadline)
        chunk = next(stream, None)
        if chunk is None:
            return b"".join(chunks)
        total += len(chunk)
        if total > _MAX_RESPONSE_BYTES:
            raise LLMError("LLM response too large", status_code=response.status_code)
        chunks.append(chunk)
        _check_deadline(deadline)


def _check_status(response: httpx.Response) -> None:
    status = response.status_code
    if not 200 <= status < 300:
        raise LLMError(f"LLM HTTP {status}", status_code=status)


def _check_encoding(response: httpx.Response) -> None:
    encoding = response.headers.get("content-encoding")
    if encoding is not None and encoding.strip().lower() != "identity":
        raise LLMError("LLM response is compressed", status_code=response.status_code)


def _shape_error() -> LLMError:
    return LLMError("unexpected LLM response shape", status_code=200)


def _loads(raw: bytes) -> object:
    try:
        return json.loads(raw)
    except (ValueError, RecursionError):
        return None


def _parse_content(raw: bytes) -> str:
    """Return ``choices[0].message.content`` or raise ``LLMError`` on any other shape."""
    data = _loads(raw)
    if not isinstance(data, dict):
        raise _shape_error()
    choices = cast("dict[str, object]", data).get("choices")
    if not isinstance(choices, list) or not choices:
        raise _shape_error()
    first = cast("list[object]", choices)[0]
    if not isinstance(first, dict):
        raise _shape_error()
    message = cast("dict[str, object]", first).get("message")
    if not isinstance(message, dict):
        raise _shape_error()
    content = cast("dict[str, object]", message).get("content")
    if not isinstance(content, str):
        raise _shape_error()
    return content


class LLMClient:
    """Sends chat requests for one agent to an OpenAI-compatible server.

    One ``httpx.Client`` is made on first use and reused, so calls share connections.
    Call ``close()`` or use the client as a context manager to free it.
    """

    def __init__(self, settings: Settings, *, transport: httpx.BaseTransport | None = None) -> None:
        self._settings = settings
        self._transport = transport
        self._client: httpx.Client | None = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        """Close the pooled connections. The next call opens a new client.

        An injected ``transport`` is closed too, so pass one that can be reused.
        """
        client, self._client = self._client, None
        if client is not None:
            client.close()

    def _http(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(
                follow_redirects=False,
                trust_env=False,
                transport=self._transport or _deadline_transport(),
            )
        return self._client

    def chat(self, agent_name: str, messages: list[dict[str, str]]) -> str:
        """Return ``choices[0].message.content`` for ``messages``.

        A raised error has no traceback below this frame, and this frame drops its
        arguments first: a logger that prints frame locals cannot show the key,
        the base URL or the messages.
        """
        try:
            return self._chat(agent_name, messages)
        except Exception as exc:
            failure = exc.with_traceback(None)
        # An unmapped error may chain to an error whose frames hold the secrets.
        failure.__cause__ = None
        failure.__context__ = None
        failure.__suppress_context__ = True
        del agent_name, messages
        raise failure

    def _chat(self, agent_name: str, messages: list[dict[str, str]]) -> str:
        if not messages:
            raise ValueError("messages must not be empty")
        config = resolve(self._settings, agent_name)
        headers = {"Accept-Encoding": "identity"}
        if config.api_key:
            headers["Authorization"] = f"Bearer {config.api_key}"
        url = f"{config.base_url.rstrip('/')}/chat/completions"
        body = {"model": config.model, "messages": messages}
        failure: LLMError | None = None
        raw = b""
        try:
            raw = self._post(url, body, headers, config.timeout)
        except httpx.TimeoutException:
            failure = LLMTimeoutError("LLM request timed out")
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            failure = LLMError(f"LLM request failed: {type(exc).__name__}")
        if failure is not None:
            raise failure
        return _parse_content(raw)

    def _post(self, url: str, body: object, headers: dict[str, str], timeout: float) -> bytes:
        # The real transport clips every socket operation to the deadline. A custom
        # transport has no such hook and must enforce its own deadline: the phase share
        # and the checks between body reads do not stop a header trickle.
        deadline = _now() + timeout
        token = _deadline.set(deadline)
        try:
            with self._http().stream(
                "POST",
                url,
                json=body,
                headers=headers,
                timeout=httpx.Timeout(timeout / _HTTPX_PHASES),
            ) as response:
                _check_status(response)
                _check_encoding(response)
                return _read_capped(response, deadline)
        finally:
            _deadline.reset(token)
