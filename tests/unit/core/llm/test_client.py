"""LLMClient.chat over httpx with a mock transport."""

import json
import os
import time
from collections.abc import Callable, Iterator

import httpx
import pytest

from config.settings import Settings
from core.llm.client import LLMClient
from core.llm.errors import LLMConfigError, LLMError, LLMTimeoutError

_AGENT = "bureaucracy_assistant"
_ONE = [{"role": "user", "content": "private-text"}]
Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """No env file; base URL, key and model set for bureaucracy_assistant."""
    monkeypatch.setattr("config.settings.load_env", lambda *a, **k: None)
    for name in list(os.environ):
        if name.startswith("LLM_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.test/v1/")
    monkeypatch.setenv("LLM_API_KEY", "sekret-key")
    monkeypatch.setenv("LLM_MODEL_BUREAUCRACY_ASSISTANT", "m1")
    return monkeypatch


class _Recorder:
    """Mock transport handler that records requests."""

    def __init__(self, handler: Handler) -> None:
        self.requests: list[httpx.Request] = []
        self._handler = handler

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._handler(request)


def _answer(content: object = "hello") -> Handler:
    body = {"choices": [{"message": {"role": "assistant", "content": content}}]}
    return lambda request: httpx.Response(200, json=body)


def _client(handler: Handler) -> tuple[LLMClient, _Recorder]:
    recorder = _Recorder(handler)
    return LLMClient(Settings(), transport=httpx.MockTransport(recorder)), recorder


def _fail(handler: Handler, messages: list[dict[str, str]] = _ONE) -> LLMError:
    client, _ = _client(handler)
    with pytest.raises(LLMError) as info:
        client.chat(_AGENT, messages)
    return info.value


def _assert_clean(error: Exception) -> None:
    for secret in ("sekret-key", "llm.test", "private-text"):
        assert secret not in str(error)


def test_bureaucracy_assistant_gets_an_answer(env: pytest.MonkeyPatch) -> None:
    client, recorder = _client(_answer("hello"))
    messages = [{"role": "user", "content": "hi"}]
    assert client.chat(_AGENT, messages) == "hello"
    (request,) = recorder.requests
    assert request.method == "POST"
    assert str(request.url) == "http://llm.test/v1/chat/completions"
    assert json.loads(request.content) == {"model": "m1", "messages": messages}
    assert request.headers["authorization"] == "Bearer sekret-key"


def test_document_processor_uses_its_own_model_and_key(env: pytest.MonkeyPatch) -> None:
    env.setenv("LLM_MODEL_DOCUMENT_PROCESSOR", "m2")
    env.setenv("LLM_API_KEY_DOCUMENT_PROCESSOR", "k2")
    client, recorder = _client(_answer())
    client.chat("document_processor", _ONE)
    (request,) = recorder.requests
    assert json.loads(request.content)["model"] == "m2"
    assert request.headers["authorization"] == "Bearer k2"


def test_empty_key_sends_no_authorization_header(env: pytest.MonkeyPatch) -> None:
    env.delenv("LLM_API_KEY")
    client, recorder = _client(_answer())
    client.chat(_AGENT, _ONE)
    assert "authorization" not in recorder.requests[0].headers


def test_unknown_agent_sends_no_request(env: pytest.MonkeyPatch) -> None:
    client, recorder = _client(_answer())
    with pytest.raises(LLMConfigError, match="nope"):
        client.chat("nope", _ONE)
    assert recorder.requests == []


def test_empty_messages_send_no_request(env: pytest.MonkeyPatch) -> None:
    client, recorder = _client(_answer())
    with pytest.raises(ValueError, match="messages"):
        client.chat(_AGENT, [])
    assert recorder.requests == []


def _slow_handler(request: httpx.Request) -> httpx.Response:
    time.sleep(0.5)
    return _answer()(request)


def _slow_body(request: httpx.Request) -> httpx.Response:
    def chunks() -> Iterator[bytes]:
        while True:
            time.sleep(0.1)
            yield b" "

    return httpx.Response(200, stream=_Stream(chunks()))


class _Stream(httpx.SyncByteStream):
    def __init__(self, chunks: Iterator[bytes]) -> None:
        self._chunks = chunks

    def __iter__(self) -> Iterator[bytes]:
        return self._chunks


def _read_timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("timed out", request=request)


@pytest.mark.parametrize("handler", [_slow_handler, _slow_body, _read_timeout])
def test_slow_server_times_out(env: pytest.MonkeyPatch, handler: Handler) -> None:
    env.setenv("LLM_TIMEOUT", "0.2")
    start = time.monotonic()
    error = _fail(handler)
    assert time.monotonic() - start < 1.25
    assert isinstance(error, LLMTimeoutError)
    assert issubclass(LLMTimeoutError, LLMError)
    _assert_clean(error)


def test_stall_after_one_chunk_times_out(env: pytest.MonkeyPatch) -> None:
    env.setenv("LLM_TIMEOUT", "0.2")
    seen: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        read = request.extensions["timeout"]["read"]
        seen.append(read)

        def chunks() -> Iterator[bytes]:
            yield b" "
            time.sleep(read)
            raise httpx.ReadTimeout("timed out", request=request)

        return httpx.Response(200, stream=_Stream(chunks()))

    start = time.monotonic()
    error = _fail(handler)
    assert time.monotonic() - start < 1.25
    assert isinstance(error, LLMTimeoutError)
    assert seen == [pytest.approx(0.05)]
    _assert_clean(error)


def test_body_over_one_mib(env: pytest.MonkeyPatch) -> None:
    error = _fail(lambda request: httpx.Response(200, content=b"x" * 1048577))
    assert type(error) is LLMError
    _assert_clean(error)


def _refuse(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("refused: sekret-key llm.test private-text", request=request)


@pytest.mark.parametrize(
    ("handler", "status"),
    [
        (lambda request: httpx.Response(500, text="private-text"), 500),
        (lambda request: httpx.Response(401, text="not json"), 401),
        (_refuse, None),
        (lambda request: httpx.Response(200, json={"id": "x"}), 200),
        (lambda request: httpx.Response(200, json={"choices": []}), 200),
        (lambda request: httpx.Response(200, json=[1]), 200),
        (_answer(5), 200),
        (lambda request: httpx.Response(200, text="x"), 200),
    ],
)
def test_http_and_transport_failures(
    env: pytest.MonkeyPatch, handler: Handler, status: int | None
) -> None:
    error = _fail(handler)
    assert type(error) is LLMError
    assert error.status_code == status
    _assert_clean(error)
    assert error.__cause__ is None
    assert error.__context__ is None


def test_redirect_is_not_followed(env: pytest.MonkeyPatch) -> None:
    location = {"location": "http://llm.test/v1/other"}
    client, recorder = _client(lambda request: httpx.Response(302, headers=location))
    with pytest.raises(LLMError) as info:
        client.chat(_AGENT, _ONE)
    assert info.value.status_code == 302
    assert len(recorder.requests) == 1
    _assert_clean(info.value)


def test_config_errors_hold_no_secret(env: pytest.MonkeyPatch) -> None:
    env.setenv("LLM_BASE_URL", "ftp://llm.test/v1")
    client, recorder = _client(_answer())
    with pytest.raises(LLMConfigError) as info:
        client.chat(_AGENT, _ONE)
    _assert_clean(info.value)
    assert recorder.requests == []
