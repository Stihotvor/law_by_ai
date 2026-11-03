import socket
from collections.abc import Iterator
from typing import Any, NoReturn

import pytest

from agents.fetch.ocr.manager import get_ocr_manager

MARKER = "SECRET-MARKER"
KEY = "test-key-SECRET"


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*args: Any, **kwargs: Any) -> NoReturn:
        raise AssertionError("network")

    monkeypatch.setattr(socket.socket, "connect", _blocked)


@pytest.fixture
def clear_manager_cache() -> Iterator[None]:
    get_ocr_manager.cache_clear()
    yield
    get_ocr_manager.cache_clear()


class FakeProvider:
    name = "fake"
    destination = "ocr.example"

    def __init__(self, text: str = "ocr text") -> None:
        self.text = text
        self.calls: list[tuple[str, bytes, str | None]] = []

    def ocr_pdf(self, data: bytes) -> str:
        self.calls.append(("pdf", data, None))
        return self.text

    def ocr_image(self, data: bytes, media_type: str) -> str:
        self.calls.append(("image", data, media_type))
        return self.text
