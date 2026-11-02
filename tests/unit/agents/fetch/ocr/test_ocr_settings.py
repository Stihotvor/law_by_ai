import pytest

from config.settings import Settings

VARS = (
    "OCR_ENABLED",
    "MISTRAL_API_KEY",
    "MISTRAL_BASE_URL",
    "MISTRAL_OCR_MODEL",
    "OCR_TIMEOUT",
    "OCR_MAX_BYTES",
)


@pytest.fixture
def clean(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    Settings()  # may load a repo dotenv file; clear the vars after construction
    for name in VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_defaults(clean: pytest.MonkeyPatch) -> None:
    s = Settings()
    assert s.ocr_enabled is False
    assert s.mistral_api_key == ""
    assert s.mistral_base_url == "https://api.mistral.ai/v1"
    assert s.mistral_ocr_model == "mistral-ocr-latest"
    assert s.ocr_timeout == 120.0
    assert isinstance(s.ocr_timeout, float)
    assert s.ocr_max_bytes == 20971520
    assert isinstance(s.ocr_max_bytes, int)


def test_overrides(clean: pytest.MonkeyPatch) -> None:
    clean.setenv("OCR_ENABLED", "true")
    clean.setenv("MISTRAL_API_KEY", "k")
    clean.setenv("MISTRAL_BASE_URL", "https://h/v2")
    clean.setenv("MISTRAL_OCR_MODEL", "m")
    clean.setenv("OCR_TIMEOUT", "2.5")
    clean.setenv("OCR_MAX_BYTES", "7")
    s = Settings()
    assert s.ocr_enabled is True
    assert s.mistral_api_key == "k"
    assert s.mistral_base_url == "https://h/v2"
    assert s.mistral_ocr_model == "m"
    assert s.ocr_timeout == 2.5
    assert s.ocr_max_bytes == 7


@pytest.mark.parametrize("value", ["1", "true", "YES", "on", " On "])
def test_enabled_truthy(clean: pytest.MonkeyPatch, value: str) -> None:
    clean.setenv("OCR_ENABLED", value)
    assert Settings().ocr_enabled is True


@pytest.mark.parametrize("value", ["0", "false", "no", ""])
def test_enabled_falsy(clean: pytest.MonkeyPatch, value: str) -> None:
    clean.setenv("OCR_ENABLED", value)
    assert Settings().ocr_enabled is False
