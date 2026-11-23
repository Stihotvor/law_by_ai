"""LLMClient.chat over httpx with a mock transport."""

import json
import os
import time
from collections.abc import Callable, Iterator

import httpx
import pytest

from config.settings import Settings
from core.llm.client import _MAX_RESPONSE_BYTES, LLMClient
from core.llm.errors import LLMConfigError, LLMError, LLMTimeoutError

_AGENT = "bureaucracy_assistant"
_ONE = [{"role": "user", "content": "private-text"}]
Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture
def llm_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """No env file; base URL, key and model set for bureaucracy_assistant."""
    monkeypatch.setattr("config.settings.load_env", lambda *a, **k: None)
    for name in list(os.environ):
        if name.startswith("LLM_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.test/v1/")
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


def test_bureaucracy_assistant_gets_an_answer(llm_env: pytest.MonkeyPatch) -> None:
    client, recorder = _client(_answer("hello"))
    messages = [{"role": "user", "content": "hi"}]
    assert client.chat(_AGENT, messages) == "hello"
    (request,) = recorder.requests
    assert request.method == "POST"
    assert str(request.url) == "https://llm.test/v1/chat/completions"
    assert json.loads(request.content) == {"model": "m1", "messages": messages}
    assert request.headers["authorization"] == "Bearer sekret-key"


def test_document_processor_uses_its_own_model_and_key(llm_env: pytest.MonkeyPatch) -> None:
    llm_env.setenv("LLM_MODEL_DOCUMENT_PROCESSOR", "m2")
    llm_env.setenv("LLM_API_KEY_DOCUMENT_PROCESSOR", "k2")
    client, recorder = _client(_answer())
    client.chat("document_processor", _ONE)
    (request,) = recorder.requests
    assert json.loads(request.content)["model"] == "m2"
    assert request.headers["authorization"] == "Bearer k2"


def test_empty_key_sends_no_authorization_header(llm_env: pytest.MonkeyPatch) -> None:
    llm_env.delenv("LLM_API_KEY")
    client, recorder = _client(_answer())
    client.chat(_AGENT, _ONE)
    assert "authorization" not in recorder.requests[0].headers


def test_unknown_agent_sends_no_request(llm_env: pytest.MonkeyPatch) -> None:
    client, recorder = _client(_answer())
    with pytest.raises(LLMConfigError, match="nope"):
        client.chat("nope", _ONE)
    assert recorder.requests == []


def test_empty_messages_send_no_request(llm_env: pytest.MonkeyPatch) -> None:
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
def test_slow_server_times_out(llm_env: pytest.MonkeyPatch, handler: Handler) -> None:
    llm_env.setenv("LLM_TIMEOUT", "0.2")
    start = time.monotonic()
    error = _fail(handler)
    assert time.monotonic() - start < 1.25
    assert isinstance(error, LLMTimeoutError)
    assert issubclass(LLMTimeoutError, LLMError)
    _assert_clean(error)


def test_stall_after_one_chunk_times_out(llm_env: pytest.MonkeyPatch) -> None:
    llm_env.setenv("LLM_TIMEOUT", "0.2")
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


def test_body_over_max_size_is_rejected(llm_env: pytest.MonkeyPatch) -> None:
    error = _fail(lambda request: httpx.Response(200, content=b"x" * (_MAX_RESPONSE_BYTES + 1)))
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
        (lambda request: httpx.Response(200, json={"choices": [1]}), 200),
        (lambda request: httpx.Response(200, json={"choices": [{"message": "m"}]}), 200),
        (_answer(5), 200),
        (lambda request: httpx.Response(200, text="x"), 200),
    ],
)
def test_http_and_transport_failures(
    llm_env: pytest.MonkeyPatch, handler: Handler, status: int | None
) -> None:
    error = _fail(handler)
    assert type(error) is LLMError
    assert error.status_code == status
    _assert_clean(error)
    assert error.__cause__ is None
    assert error.__context__ is None


def test_redirect_is_not_followed(llm_env: pytest.MonkeyPatch) -> None:
    location = {"location": "http://llm.test/v1/other"}
    client, recorder = _client(lambda request: httpx.Response(302, headers=location))
    with pytest.raises(LLMError) as info:
        client.chat(_AGENT, _ONE)
    assert info.value.status_code == 302
    assert len(recorder.requests) == 1
    _assert_clean(info.value)


def test_config_errors_hold_no_secret(llm_env: pytest.MonkeyPatch) -> None:
    llm_env.setenv("LLM_BASE_URL", "ftp://llm.test/v1")
    client, recorder = _client(_answer())
    with pytest.raises(LLMConfigError) as info:
        client.chat(_AGENT, _ONE)
    _assert_clean(info.value)
    assert recorder.requests == []


def test_agent_url_and_key_override_global(llm_env: pytest.MonkeyPatch) -> None:
    llm_env.setenv("LLM_BASE_URL_ANALYSIS", "https://b.local/v1")
    llm_env.setenv("LLM_API_KEY_ANALYSIS", "a-key")
    llm_env.setenv("LLM_MODEL_ANALYSIS", "m-an")
    client, recorder = _client(_answer())
    client.chat("analysis", _ONE)
    (request,) = recorder.requests
    assert str(request.url) == "https://b.local/v1/chat/completions"
    assert request.headers["authorization"] == "Bearer a-key"


def test_global_model_is_fallback(llm_env: pytest.MonkeyPatch) -> None:
    llm_env.setenv("LLM_MODEL", "global-m")
    client, recorder = _client(_answer())
    client.chat("analysis", _ONE)
    assert json.loads(recorder.requests[0].content)["model"] == "global-m"


@pytest.mark.parametrize("alias", ["bureaucracy", "processor"])
def test_old_agent_alias_is_rejected(llm_env: pytest.MonkeyPatch, alias: str) -> None:
    client, recorder = _client(_answer())
    with pytest.raises(LLMConfigError, match=alias):
        client.chat(alias, _ONE)
    assert recorder.requests == []


def test_no_model_sends_no_request(llm_env: pytest.MonkeyPatch) -> None:
    client, recorder = _client(_answer())
    with pytest.raises(LLMConfigError, match="LLM_MODEL_CHANGE_TRACKER") as info:
        client.chat("change_tracker", _ONE)
    assert "change_tracker" in str(info.value)
    assert recorder.requests == []


def test_body_of_exactly_max_size_is_accepted(llm_env: pytest.MonkeyPatch) -> None:
    prefix = '{"choices":[{"message":{"content":"'
    suffix = '"}}]}'
    pad = _MAX_RESPONSE_BYTES - len(prefix) - len(suffix)
    body = (prefix + "a" * pad + suffix).encode()
    assert len(body) == _MAX_RESPONSE_BYTES
    client, _ = _client(lambda request: httpx.Response(200, content=body))
    assert client.chat(_AGENT, _ONE) == "a" * pad


@pytest.mark.parametrize(
    "url",
    [
        "http://user:pass@llm.test/v1",
        "http://llm.test/v1?key=abc",
        "http://llm.test/v1#frag",
        "ftp://llm.test/v1",
        "file:///etc/x",
    ],
)
def test_bad_base_url_sends_nothing(llm_env: pytest.MonkeyPatch, url: str) -> None:
    llm_env.setenv("LLM_BASE_URL", url)
    client, recorder = _client(_answer())
    with pytest.raises(LLMConfigError) as info:
        client.chat(_AGENT, _ONE)
    assert _AGENT in str(info.value)
    assert "pass" not in str(info.value)
    assert url not in str(info.value)
    assert recorder.requests == []


def test_http_localhost_is_allowed(llm_env: pytest.MonkeyPatch) -> None:
    llm_env.setenv("LLM_BASE_URL", "http://localhost:11434/v1")
    client, recorder = _client(_answer("ok"))
    assert client.chat(_AGENT, _ONE) == "ok"
    assert str(recorder.requests[0].url) == "http://localhost:11434/v1/chat/completions"


@pytest.mark.parametrize("status", [401, 404, 429, 503])
def test_error_status_is_not_retried(llm_env: pytest.MonkeyPatch, status: int) -> None:
    client, recorder = _client(lambda request: httpx.Response(status, text="x"))
    with pytest.raises(LLMError) as info:
        client.chat(_AGENT, _ONE)
    assert info.value.status_code == status
    assert len(recorder.requests) == 1


def test_proxy_env_is_ignored(llm_env: pytest.MonkeyPatch) -> None:
    llm_env.setenv("HTTP_PROXY", "http://proxy.local:3128")
    llm_env.setenv("http_proxy", "http://proxy.local:3128")
    client, recorder = _client(_answer())
    client.chat(_AGENT, _ONE)
    assert recorder.requests[0].url.host == "llm.test"


def test_key_and_content_are_not_logged(
    llm_env: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level("DEBUG")
    client, _ = _client(_answer())
    client.chat(_AGENT, _ONE)
    bad, _ = _client(lambda request: httpx.Response(500, text="private-text"))
    with pytest.raises(LLMError):
        bad.chat(_AGENT, _ONE)
    for secret in ("sekret-key", "private-text"):
        assert secret not in caplog.text


def test_repeated_calls_get_separate_answers(llm_env: pytest.MonkeyPatch) -> None:
    answers = iter(["A", "B"])
    client, recorder = _client(lambda request: _answer(next(answers))(request))
    assert [client.chat(_AGENT, _ONE), client.chat(_AGENT, _ONE)] == ["A", "B"]
    assert len(recorder.requests) == 2


def test_non_ascii_messages_sent_unchanged(llm_env: pytest.MonkeyPatch) -> None:
    llm_env.setenv("LLM_MODEL_LEGAL_RESEARCH", "m3")
    messages = [
        {"role": "system", "content": "Jesteś asystentem"},
        {"role": "user", "content": "Ile kosztuje wiza?"},
    ]
    client, recorder = _client(_answer())
    client.chat("legal_research", messages)
    assert json.loads(recorder.requests[0].content)["messages"] == messages


def test_every_agent_uses_its_own_model(llm_env: pytest.MonkeyPatch) -> None:
    from core.llm.config import LLM_AGENTS

    for agent in LLM_AGENTS:
        llm_env.setenv(f"LLM_MODEL_{agent.upper()}", f"m-{agent}")
    client, recorder = _client(_answer())
    for agent in LLM_AGENTS:
        client.chat(agent, _ONE)
    models = [json.loads(r.content)["model"] for r in recorder.requests]
    assert models == [f"m-{agent}" for agent in LLM_AGENTS]


def test_no_thread_left_after_100_calls(llm_env: pytest.MonkeyPatch) -> None:
    import threading

    before = threading.active_count()
    client, recorder = _client(_answer())
    for _ in range(100):
        client.chat(_AGENT, _ONE)
    assert len(recorder.requests) == 100
    assert threading.active_count() <= before


def test_asks_for_uncompressed_body(llm_env: pytest.MonkeyPatch) -> None:
    client, recorder = _client(_answer())
    client.chat(_AGENT, _ONE)
    assert recorder.requests[0].headers["accept-encoding"] == "identity"


def test_invalid_url_is_wrapped(llm_env: pytest.MonkeyPatch) -> None:
    llm_env.setenv("LLM_BASE_URL", "https://llm.test/v1\x01")
    client, recorder = _client(_answer())
    with pytest.raises(LLMError) as info:
        client.chat(_AGENT, _ONE)
    assert type(info.value) is LLMError
    assert str(info.value) == "LLM request failed: InvalidURL"
    assert info.value.__cause__ is None
    assert info.value.__context__ is None
    _assert_clean(info.value)
    assert recorder.requests == []


class _RecordingStream(httpx.SyncByteStream):
    def __init__(self, body: bytes) -> None:
        self.read = False
        self._body = body

    def __iter__(self) -> Iterator[bytes]:
        self.read = True
        yield self._body


@pytest.mark.parametrize("encoding", ["gzip", "br", "deflate", "zstd", ""])
def test_compressed_response_is_rejected_unread(llm_env: pytest.MonkeyPatch, encoding: str) -> None:
    stream = _RecordingStream(b"private-text")
    headers = {"content-encoding": encoding}
    error = _fail(lambda request: httpx.Response(200, headers=headers, stream=stream))
    assert type(error) is LLMError
    assert str(error) == "LLM response is compressed"
    assert error.status_code == 200
    assert stream.read is False
    _assert_clean(error)


def test_identity_content_encoding_is_accepted(llm_env: pytest.MonkeyPatch) -> None:
    body = {"choices": [{"message": {"content": "ok"}}]}
    headers = {"content-encoding": "identity"}
    client, _ = _client(lambda request: httpx.Response(200, headers=headers, json=body))
    assert client.chat(_AGENT, _ONE) == "ok"


def test_deeply_nested_json_is_a_malformed_response(llm_env: pytest.MonkeyPatch) -> None:
    body = b"[" * 100000 + b"]" * 100000
    assert len(body) <= _MAX_RESPONSE_BYTES
    error = _fail(lambda request: httpx.Response(200, content=body))
    assert type(error) is LLMError
    assert error.status_code == 200
    assert error.__cause__ is None
    assert error.__context__ is None
    _assert_clean(error)
