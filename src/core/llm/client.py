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

_MAX_RESPONSE_BYTES = 1024 * 1024
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


def _loads(raw: bytes) -> object:
    try:
        return json.loads(raw)
    except ValueError:
        return None


def _item(value: object, key: str) -> object:
    return cast("dict[str, object]", value).get(key) if isinstance(value, dict) else None


def _first(value: object) -> object:
    items = cast("list[object]", value) if isinstance(value, list) else []
    return items[0] if items else None


def _content(raw: bytes) -> str:
    message = _item(_first(_item(_loads(raw), "choices")), "message")
    content = _item(message, "content")
    if not isinstance(content, str):
        raise LLMError("unexpected LLM response shape", status_code=200)
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
        headers = {"Authorization": f"Bearer {config.api_key}"} if config.api_key else {}
        url = f"{config.base_url.rstrip('/')}/chat/completions"
        body = {"model": config.model, "messages": messages}
        failure: LLMError | None = None
        raw = b""
        try:
            raw = self._post(url, body, headers, config.timeout)
        except httpx.TimeoutException:
            failure = LLMTimeoutError("LLM request timed out")
        except httpx.HTTPError as exc:
            failure = LLMError(f"LLM request failed: {type(exc).__name__}")
        if failure is not None:
            raise failure
        return _content(raw)

    def _post(self, url: str, body: object, headers: dict[str, str], timeout: float) -> bytes:
        deadline = _now() + timeout
        with (
            httpx.Client(
                timeout=httpx.Timeout(timeout),
                follow_redirects=False,
                trust_env=False,
                transport=self._transport,
            ) as client,
            client.stream("POST", url, json=body, headers=headers) as response,
        ):
            _check_status(response)
            return _read_capped(response, deadline)
