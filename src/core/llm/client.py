"""OpenAI-compatible chat client. No logging here: key and content must not leak.

Errors are raised outside ``except`` blocks so they carry no cause or context
that could hold the request URL, the key or the messages.
"""

import json
import time
from typing import cast

import httpx

from config.settings import Settings
from core.llm.config import resolve
from core.llm.errors import LLMError, LLMTimeoutError

__all__ = ["LLMClient"]

_MAX_RESPONSE_BYTES = 1024 * 1024
# httpx applies its timeout per phase (connect, write, pool, each read).
_HTTPX_PHASES = 4
_now = time.monotonic


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
    """Sends chat requests for one agent to an OpenAI-compatible server."""

    def __init__(self, settings: Settings, *, transport: httpx.BaseTransport | None = None) -> None:
        self._settings = settings
        self._transport = transport

    def chat(self, agent_name: str, messages: list[dict[str, str]]) -> str:
        """Return ``choices[0].message.content`` for ``messages``."""
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
        # httpx fixes the read timeout once per body, so each phase gets a share:
        # the last read started before the deadline ends by (1 + 1/phases) x timeout.
        deadline = _now() + timeout
        with (
            httpx.Client(
                timeout=httpx.Timeout(timeout / _HTTPX_PHASES),
                follow_redirects=False,
                trust_env=False,
                transport=self._transport,
            ) as client,
            client.stream("POST", url, json=body, headers=headers) as response,
        ):
            _check_status(response)
            _check_encoding(response)
            return _read_capped(response, deadline)
