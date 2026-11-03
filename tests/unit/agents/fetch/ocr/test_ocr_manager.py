import logging
from unittest.mock import MagicMock

import httpx
import pytest

from agents.fetch.formats.base import FormatError
from agents.fetch.ocr import manager as manager_mod
from agents.fetch.ocr.errors import (
    OcrConfigError,
    OcrDisabledError,
    OcrError,
    OcrInputError,
    OcrProviderError,
)
from agents.fetch.ocr.manager import OcrManager, OcrProvider, get_ocr_manager

from .conftest import KEY, MARKER, FakeProvider

pytestmark = pytest.mark.usefixtures("clear_manager_cache")


def test_disabled_manager(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    m = OcrManager(None)
    assert m.enabled is False
    with pytest.raises(OcrDisabledError) as e1:
        m.read_pdf(MARKER.encode())
    with pytest.raises(OcrDisabledError) as e2:
        m.read_image(MARKER.encode(), "image/png")
    assert MARKER not in str(e1.value) + str(e2.value)
    assert str(e1.value) == "OCR is disabled"
    assert caplog.records == []


def test_disabled_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCR_ENABLED", "false")
    provider_cls = MagicMock()
    client_cls = MagicMock()
    monkeypatch.setattr(manager_mod, "MistralOcrProvider", provider_cls)
    monkeypatch.setattr(httpx, "Client", client_cls)
    m = get_ocr_manager()
    assert m.enabled is False
    provider_cls.assert_not_called()
    client_cls.assert_not_called()


def test_enabled_delegates() -> None:
    fake = FakeProvider("hello")
    m = OcrManager(fake)
    assert m.enabled is True
    assert isinstance(fake, OcrProvider)
    assert m.read_pdf(b"abc") == "hello"
    assert m.read_image(b"xyz", "image/png") == "hello"
    assert fake.calls == [("pdf", b"abc", None), ("image", b"xyz", "image/png")]


def test_enable_logs_one_warning(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    m = OcrManager(FakeProvider(MARKER))
    assert len(caplog.records) == 1
    rec = caplog.records[0]
    assert rec.levelno == logging.WARNING
    text = rec.getMessage()
    assert text == "OCR enabled: document content is sent to ocr.example (fake)"
    assert MARKER not in text and KEY not in text
    m.read_pdf(b"a")
    m.read_image(b"a", "image/png")
    assert len(caplog.records) == 1


def test_factory_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCR_ENABLED", "true")
    monkeypatch.setenv("MISTRAL_API_KEY", KEY)
    monkeypatch.setenv("MISTRAL_BASE_URL", "https://x.example/v1")
    monkeypatch.setenv("MISTRAL_OCR_MODEL", "m1")
    monkeypatch.setenv("OCR_TIMEOUT", "7.5")
    monkeypatch.setenv("OCR_MAX_BYTES", "99")
    provider_cls = MagicMock()
    provider_cls.return_value = FakeProvider()
    monkeypatch.setattr(manager_mod, "MistralOcrProvider", provider_cls)
    m = get_ocr_manager()
    assert m.enabled is True
    provider_cls.assert_called_once_with(
        api_key=KEY,
        base_url="https://x.example/v1",
        model="m1",
        timeout=7.5,
        max_bytes=99,
    )
    assert get_ocr_manager() is m
    provider_cls.assert_called_once()


def test_factory_enabled_empty_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OCR_ENABLED", "true")
    monkeypatch.setenv("MISTRAL_API_KEY", "")
    provider_cls = MagicMock()
    monkeypatch.setattr(manager_mod, "MistralOcrProvider", provider_cls)
    with pytest.raises(OcrConfigError) as exc:
        get_ocr_manager()
    assert KEY not in str(exc.value)
    provider_cls.assert_not_called()


def test_error_family() -> None:
    for cls in (OcrDisabledError, OcrConfigError, OcrInputError, OcrProviderError):
        assert issubclass(cls, OcrError)
    assert not issubclass(OcrError, FormatError)
    err = OcrProviderError("x", status_code=429)
    assert err.status_code == 429
    assert OcrProviderError("x").status_code is None
