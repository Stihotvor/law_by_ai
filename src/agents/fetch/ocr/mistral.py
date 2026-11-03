"""Mistral Document AI OCR adapter. No logging here: content and key must not leak."""

import base64
import json
from typing import Any
from urllib.parse import urlsplit

import httpx

from agents.fetch.ocr.errors import OcrConfigError, OcrInputError, OcrProviderError

_MAX_RESPONSE_BYTES = 16 * 1024 * 1024
_IMAGE_TYPES = frozenset({"image/png", "image/jpeg"})


def _parse_host(base_url: str) -> str:
    if not base_url.startswith("https://"):
        raise OcrConfigError("OCR base URL must use https")
    parts = urlsplit(base_url)
    if "@" in parts.netloc:
        raise OcrConfigError("OCR base URL must not hold credentials")
    if not parts.hostname:
        raise OcrConfigError("OCR base URL has no host")
    return parts.hostname


def _data_url(media_type: str, data: bytes) -> str:
    return f"data:{media_type};base64,{base64.b64encode(data).decode('ascii')}"


def _extract_text(raw: bytes) -> str:
    try:
        payload = json.loads(raw)
    except ValueError as exc:
        raise OcrProviderError("unexpected response shape") from exc
    pages = payload.get("pages") if isinstance(payload, dict) else None
    if not isinstance(pages, list):
        raise OcrProviderError("unexpected response shape")
    items: list[tuple[int, str]] = []
    for page in pages:
        if not isinstance(page, dict):
            raise OcrProviderError("unexpected response shape")
        index, markdown = page.get("index"), page.get("markdown")
        if isinstance(index, bool) or not isinstance(index, int) or not isinstance(markdown, str):
            raise OcrProviderError("unexpected response shape")
        items.append((index, markdown.strip()))
    texts = [text for _, text in sorted(items, key=lambda item: item[0]) if text]
    if not texts:
        raise OcrProviderError("OCR returned no text")
    return "\n\n".join(texts)


def _read_capped(response: httpx.Response) -> bytes:
    declared = response.headers.get("content-length")
    if declared is not None and declared.isdigit() and int(declared) > _MAX_RESPONSE_BYTES:
        raise OcrProviderError("response too large")
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > _MAX_RESPONSE_BYTES:
            raise OcrProviderError("response too large")
        chunks.append(chunk)
    return b"".join(chunks)


class MistralOcrProvider:
    name = "mistral"

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float,
        max_bytes: int,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise OcrConfigError("Mistral API key is not set")
        self.destination: str = _parse_host(base_url)
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._max_bytes = max_bytes
        self._transport = transport

    def __repr__(self) -> str:
        return f"MistralOcrProvider(model={self._model!r}, destination={self.destination!r})"

    def ocr_pdf(self, data: bytes) -> str:
        self._check(data)
        document = {
            "type": "document_url",
            "document_url": _data_url("application/pdf", data),
        }
        return self._post(document)

    def ocr_image(self, data: bytes, media_type: str) -> str:
        if media_type not in _IMAGE_TYPES:
            raise OcrInputError("unsupported media type")
        self._check(data)
        document = {"type": "image_url", "image_url": _data_url(media_type, data)}
        return self._post(document)

    def _check(self, data: bytes) -> None:
        if not data:
            raise OcrInputError("empty input")
        if len(data) > self._max_bytes:
            raise OcrInputError("input too large")

    def _post(self, document: dict[str, str]) -> str:
        body: dict[str, Any] = {
            "model": self._model,
            "document": document,
            "include_image_base64": False,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            with (
                httpx.Client(
                    timeout=httpx.Timeout(self._timeout),
                    follow_redirects=False,
                    trust_env=False,
                    transport=self._transport,
                ) as client,
                client.stream(
                    "POST", f"{self._base_url}/ocr", json=body, headers=headers
                ) as response,
            ):
                self._check_status(response)
                raw = _read_capped(response)
        except httpx.HTTPError as exc:
            raise OcrProviderError(f"request failed: {type(exc).__name__}") from exc
        return _extract_text(raw)

    @staticmethod
    def _check_status(response: httpx.Response) -> None:
        status = response.status_code
        if 300 <= status < 400:
            raise OcrProviderError("redirect not allowed", status_code=status)
        if status >= 300:
            raise OcrProviderError(f"HTTP {status}", status_code=status)
