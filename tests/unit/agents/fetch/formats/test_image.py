from unittest.mock import MagicMock

import pytest

import agents.fetch.document_fetcher
from agents.fetch.formats import image as image_mod
from agents.fetch.formats._safety import CorruptDocumentError
from agents.fetch.formats.base import FORMATS, find_parser
from agents.fetch.formats.image import ImageParser
from agents.fetch.ocr.errors import OcrDisabledError, OcrProviderError
from agents.fetch.ocr.manager import OcrManager

PNG = b"\x89PNG\r\n\x1a\n" + b"junk"
JPG = b"\xff\xd8\xff\xe0" + b"junk"


class Fake:
    name = "fake"
    destination = "ocr.example"

    def __init__(self) -> None:
        self.calls: list[tuple[bytes, str]] = []
        self.error: Exception | None = None

    def ocr_pdf(self, data: bytes) -> str:
        raise AssertionError("pdf")

    def ocr_image(self, data: bytes, media_type: str) -> str:
        if self.error is not None:
            raise self.error
        self.calls.append((data, media_type))
        return "ocr text"


def _use(monkeypatch: pytest.MonkeyPatch, manager: OcrManager) -> MagicMock:
    getter = MagicMock(return_value=manager)
    monkeypatch.setattr(image_mod, "get_ocr_manager", getter)
    return getter


@pytest.mark.parametrize(
    ("name", "mime"),
    [
        ("a.PNG", None),
        ("a.jpg", None),
        ("a.jpeg", None),
        ("blob", "image/png"),
        ("blob", "image/jpeg; x=1"),
    ],
)
def test_find_parser(name: str, mime: str | None) -> None:
    assert isinstance(find_parser(name, mime), ImageParser)


def test_registered_names() -> None:
    assert agents.fetch.document_fetcher is not None
    assert FORMATS.names() == ("docx", "html", "image", "pdf", "text")


@pytest.mark.parametrize(("data", "media"), [(PNG, "image/png"), (JPG, "image/jpeg")])
def test_ocr_on(monkeypatch: pytest.MonkeyPatch, data: bytes, media: str) -> None:
    fake = Fake()
    _use(monkeypatch, OcrManager(fake))
    assert ImageParser().parse(data) == "ocr text"
    assert fake.calls == [(data, media)]


def test_magic_wins_over_name(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = Fake()
    _use(monkeypatch, OcrManager(fake))
    find_parser("a.jpg").parse(PNG)
    assert fake.calls == [(PNG, "image/png")]


def test_ocr_off(monkeypatch: pytest.MonkeyPatch) -> None:
    provider_cls = MagicMock()
    monkeypatch.setattr("agents.fetch.ocr.manager.MistralOcrProvider", provider_cls)
    _use(monkeypatch, OcrManager(None))
    with pytest.raises(OcrDisabledError):
        ImageParser().parse(PNG)
    provider_cls.assert_not_called()


@pytest.mark.parametrize("data", [b"GIF89a", b"", b"\x89PNG", b"\xff\xd8"])
def test_not_an_image(monkeypatch: pytest.MonkeyPatch, data: bytes) -> None:
    manager = MagicMock(wraps=OcrManager(None))
    getter = _use(monkeypatch, manager)
    with pytest.raises(CorruptDocumentError, match=r"^not a png or jpeg image$"):
        ImageParser().parse(data)
    getter.assert_not_called()
    manager.read_image.assert_not_called()


def test_provider_failure_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = Fake()
    fake.error = OcrProviderError("HTTP 500", status_code=500)
    _use(monkeypatch, OcrManager(fake))
    with pytest.raises(OcrProviderError) as exc:
        ImageParser().parse(PNG)
    assert exc.value is fake.error
