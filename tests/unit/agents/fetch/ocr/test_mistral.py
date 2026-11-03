import base64
import json
import logging
from collections.abc import Callable, Iterator
from typing import Any, cast

import httpx
import pytest

from agents.fetch.ocr import mistral as mistral_mod
from agents.fetch.ocr.errors import OcrConfigError, OcrInputError, OcrProviderError
from agents.fetch.ocr.mistral import MistralOcrProvider

from .conftest import KEY, MARKER

URL = "https://api.mistral.ai/v1/ocr"
Handler = Callable[[httpx.Request], httpx.Response]


def _ok(*pages: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json={"pages": list(pages)})


def _page(index: int, markdown: str) -> dict[str, Any]:
    return {"index": index, "markdown": markdown}


class Recorder:
    def __init__(self, response: httpx.Response | Exception) -> None:
        self.response = response
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _provider(
    handler: Handler, *, max_bytes: int = 1000, base_url: str = "https://api.mistral.ai/v1/"
) -> MistralOcrProvider:
    return MistralOcrProvider(
        api_key=KEY,
        base_url=base_url,
        model="mistral-ocr-latest",
        timeout=5.0,
        max_bytes=max_bytes,
        transport=httpx.MockTransport(handler),
    )


def test_pdf_request() -> None:
    rec = Recorder(_ok(_page(0, "hello")))
    assert _provider(rec).ocr_pdf(b"%PDF data") == "hello"
    assert len(rec.requests) == 1
    req = rec.requests[0]
    assert req.method == "POST"
    assert str(req.url) == URL
    assert req.headers["Authorization"] == f"Bearer {KEY}"
    body = json.loads(req.content)
    assert body["model"] == "mistral-ocr-latest"
    assert body["document"]["type"] == "document_url"
    prefix = "data:application/pdf;base64,"
    assert body["document"]["document_url"].startswith(prefix)
    assert base64.b64decode(body["document"]["document_url"][len(prefix) :]) == b"%PDF data"
    assert body["include_image_base64"] is False


@pytest.mark.parametrize("media", ["image/png", "image/jpeg"])
def test_image_request(media: str) -> None:
    rec = Recorder(_ok(_page(0, "t")))
    assert _provider(rec).ocr_image(b"img", media) == "t"
    body = json.loads(rec.requests[0].content)
    assert body["document"]["type"] == "image_url"
    encoded = base64.b64encode(b"img").decode()
    assert body["document"]["image_url"] == f"data:{media};base64,{encoded}"
    assert body["include_image_base64"] is False


def test_image_bad_media_type() -> None:
    rec = Recorder(_ok(_page(0, "t")))
    with pytest.raises(OcrInputError) as exc:
        _provider(rec).ocr_image(b"img", "image/gif")
    assert str(exc.value) == "unsupported media type"
    assert rec.requests == []


def test_pages_sorted_and_joined() -> None:
    rec = Recorder(_ok(_page(1, " second \n"), _page(2, "  "), _page(0, "first")))
    assert _provider(rec).ocr_pdf(b"x") == "first\n\nsecond"


@pytest.mark.parametrize("index", [True, False])
def test_bool_page_index_rejected(index: bool) -> None:
    rec = Recorder(_ok(_page(cast(Any, index), "a")))
    with pytest.raises(OcrProviderError):
        _provider(rec).ocr_pdf(b"x")


def test_equal_indexes_keep_response_order() -> None:
    rec = Recorder(_ok(_page(0, "b"), _page(0, "a")))
    assert _provider(rec).ocr_pdf(b"x") == "b\n\na"


def test_pages_sorted_by_index_not_text() -> None:
    rec = Recorder(_ok(_page(1, "a"), _page(0, "b")))
    assert _provider(rec).ocr_pdf(b"x") == "b\n\na"


def test_header_name_case_and_method() -> None:
    rec = Recorder(_ok(_page(0, "t")))
    _provider(rec).ocr_pdf(b"x")
    assert (b"Authorization", f"Bearer {KEY}".encode()) in rec.requests[0].headers.raw
    assert rec.requests[0].method == "POST"


def test_chunked_response_joined() -> None:
    raw = json.dumps({"pages": [_page(0, "ok")]}).encode()

    def chunks() -> Iterator[bytes]:
        yield raw[:5]
        yield raw[5:]

    assert _provider(Recorder(httpx.Response(200, content=chunks()))).ocr_pdf(b"x") == "ok"


def test_total_deadline_between_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    ticks = iter([0.0, 0.5, 500.0])
    monkeypatch.setattr(mistral_mod, "_now", lambda: next(ticks))

    def chunks() -> Iterator[bytes]:
        yield b"{"
        yield b'"pages"'
        yield b":[]}"

    with pytest.raises(OcrProviderError) as exc:
        _provider(Recorder(httpx.Response(200, content=chunks()))).ocr_pdf(b"x")
    assert str(exc.value) == "ocr timeout"


def test_all_empty() -> None:
    with pytest.raises(OcrProviderError) as exc:
        _provider(Recorder(_ok(_page(0, " "), _page(1, "")))).ocr_pdf(b"x")
    assert str(exc.value) == "OCR returned no text"


def test_no_pages_at_all() -> None:
    with pytest.raises(OcrProviderError) as exc:
        _provider(Recorder(_ok())).ocr_pdf(b"x")
    assert str(exc.value) == "OCR returned no text"


def test_redirect_not_followed() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if str(request.url) == URL:
            return httpx.Response(302, headers={"Location": "https://evil.example/x"})
        raise AssertionError("redirect followed")

    with pytest.raises(OcrProviderError, match="redirect not allowed") as exc:
        _provider(handler).ocr_pdf(b"x")
    assert exc.value.status_code == 302
    assert seen == [URL]


@pytest.mark.parametrize("status", [300, 301, 399])
def test_3xx_is_redirect(status: int) -> None:
    with pytest.raises(OcrProviderError) as exc:
        _provider(Recorder(httpx.Response(status))).ocr_pdf(b"x")
    assert str(exc.value) == "redirect not allowed"
    assert exc.value.status_code == status


@pytest.mark.parametrize("status", [400, 401, 429, 500])
def test_http_errors(status: int) -> None:
    resp = httpx.Response(status, text=f"{MARKER} body")
    with pytest.raises(OcrProviderError) as exc:
        _provider(Recorder(resp)).ocr_pdf(b"x")
    assert exc.value.status_code == status
    assert str(exc.value) == f"HTTP {status}"


def test_timeout_wrapped_and_client_options(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[dict[str, Any]] = []
    real = httpx.Client

    def spy(**kwargs: Any) -> httpx.Client:
        created.append(kwargs)
        return real(**kwargs)

    monkeypatch.setattr(httpx, "Client", spy)
    with pytest.raises(OcrProviderError, match="request failed: ReadTimeout") as exc:
        _provider(Recorder(httpx.ReadTimeout(MARKER))).ocr_pdf(b"x")
    assert MARKER not in str(exc.value)
    assert isinstance(exc.value.__cause__, httpx.ReadTimeout)
    (kw,) = created
    assert kw["follow_redirects"] is False
    assert kw["trust_env"] is False
    assert kw["timeout"] == httpx.Timeout(5.0)
    assert "verify" not in kw


def test_input_checks_before_client(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(**kwargs: Any) -> None:
        raise AssertionError("client created")

    monkeypatch.setattr(httpx, "Client", boom)
    p = _provider(Recorder(_ok(_page(0, "t"))), max_bytes=3)
    with pytest.raises(OcrInputError) as e1:
        p.ocr_pdf(b"")
    with pytest.raises(OcrInputError):
        p.ocr_image(b"", "image/png")
    with pytest.raises(OcrInputError) as e2:
        p.ocr_pdf(b"abcd")
    assert str(e1.value) == "empty input"
    assert str(e2.value) == "input too large"


def test_input_at_limit_allowed() -> None:
    assert _provider(Recorder(_ok(_page(0, "t"))), max_bytes=3).ocr_pdf(b"abc") == "t"


def test_response_cap_by_content_length(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mistral_mod, "_MAX_RESPONSE_BYTES", 10)
    resp = httpx.Response(200, headers={"Content-Length": "11"}, content=b"{}")
    with pytest.raises(OcrProviderError) as exc:
        _provider(Recorder(resp)).ocr_pdf(b"x")
    assert str(exc.value) == "response too large"


def test_response_cap_streamed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mistral_mod, "_MAX_RESPONSE_BYTES", 10)

    def chunks() -> Iterator[bytes]:
        yield b"x" * 6
        yield b"x" * 6

    resp = httpx.Response(200, content=chunks())
    with pytest.raises(OcrProviderError) as exc:
        _provider(Recorder(resp)).ocr_pdf(b"x")
    assert str(exc.value) == "response too large"


def test_response_at_cap_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    raw = json.dumps({"pages": [_page(0, "ok")]}).encode()
    monkeypatch.setattr(mistral_mod, "_MAX_RESPONSE_BYTES", len(raw))
    resp = httpx.Response(200, headers={"Content-Length": str(len(raw))}, content=raw)
    assert _provider(Recorder(resp)).ocr_pdf(b"x") == "ok"


def test_non_numeric_content_length_ignored() -> None:
    resp = httpx.Response(200, headers={"Content-Length": "abc"}, content=b'{"pages":[]}')
    with pytest.raises(OcrProviderError):
        _provider(Recorder(resp)).ocr_pdf(b"x")


@pytest.mark.parametrize(
    "content",
    [
        b"not json",
        b"{}",
        b'{"pages": "x"}',
        b"[1]",
        b'{"pages": [1]}',
        b'{"pages": [{"index": 0, "markdown": 5}]}',
        b'{"pages": [{"markdown": "a"}]}',
        b'{"pages": [{"index": "0", "markdown": "a"}]}',
    ],
)
def test_bad_shape(content: bytes) -> None:
    with pytest.raises(OcrProviderError) as exc:
        _provider(Recorder(httpx.Response(200, content=content))).ocr_pdf(b"x")
    assert str(exc.value) == "unexpected response shape"


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"base_url": "http://api.mistral.ai/v1"}, "OCR base URL must use https"),
        (
            {"base_url": "https://user:pw@api.mistral.ai/v1"},
            "OCR base URL must not hold credentials",
        ),
        ({"base_url": "https://"}, "OCR base URL has no host"),
        (
            {"base_url": "https://api.mistral.ai/v1?x=1"},
            "OCR base URL must not hold a query or fragment",
        ),
        (
            {"base_url": "https://api.mistral.ai/v1#f"},
            "OCR base URL must not hold a query or fragment",
        ),
        ({"api_key": ""}, "Mistral API key is not set"),
    ],
)
def test_constructor_rejects(override: dict[str, Any], message: str) -> None:
    args: dict[str, Any] = {
        "api_key": KEY,
        "base_url": "https://api.mistral.ai/v1",
        "model": "m",
        "timeout": 1.0,
        "max_bytes": 1,
    }
    args.update(override)
    with pytest.raises(OcrConfigError) as exc:
        MistralOcrProvider(**args)
    assert str(exc.value) == message


def test_destination_and_repr() -> None:
    p = _provider(Recorder(_ok(_page(0, "t"))))
    assert p.destination == "api.mistral.ai"
    assert p.name == "mistral"
    assert KEY not in repr(p)
    assert "api.mistral.ai" in repr(p)
    assert "mistral-ocr-latest" in repr(p)


def test_no_leaks(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    payload = (MARKER * 3).encode()
    b64 = base64.b64encode(payload).decode()
    body_text = f"{MARKER} response body"
    messages: list[str] = []
    for resp in (
        httpx.Response(500, text=body_text),
        httpx.Response(200, text=body_text),
        httpx.Response(302, headers={"Location": f"https://x/?k={MARKER}"}),
        httpx.Response(200, json={"pages": []}),
    ):
        with pytest.raises(OcrProviderError) as exc:
            _provider(Recorder(resp), max_bytes=10_000).ocr_pdf(payload)
        messages.append(str(exc.value))
    with pytest.raises(OcrInputError) as exc2:
        _provider(Recorder(_ok()), max_bytes=1).ocr_pdf(payload)
    messages.append(str(exc2.value))
    logged = " ".join(r.getMessage() for r in caplog.records)
    for text in [*messages, logged, repr(_provider(Recorder(_ok())))]:
        for leaked in (KEY, b64, MARKER, "response body"):
            assert leaked not in text


def test_deeply_nested_json_is_a_typed_error() -> None:
    body = b"[" * 100000 + b"]" * 100000
    rec = Recorder(httpx.Response(200, content=body))
    with pytest.raises(OcrProviderError):
        _provider(rec).ocr_pdf(b"x")
