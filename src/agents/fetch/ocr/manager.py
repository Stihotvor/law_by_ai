"""OCR manager: routes bytes to the provider, or refuses when OCR is off."""

import logging
from functools import lru_cache
from typing import Protocol, runtime_checkable

from agents.fetch.ocr.errors import OcrConfigError, OcrDisabledError
from agents.fetch.ocr.mistral import MistralOcrProvider
from config.settings import get_settings

_log = logging.getLogger(__name__)


@runtime_checkable
class OcrProvider(Protocol):
    name: str
    destination: str

    def ocr_pdf(self, data: bytes) -> str: ...

    def ocr_image(self, data: bytes, media_type: str) -> str: ...


class OcrManager:
    def __init__(self, provider: OcrProvider | None = None) -> None:
        self._provider = provider
        if provider is not None:
            _log.warning(
                "OCR enabled: document content is sent to %s (%s)",
                provider.destination,
                provider.name,
            )

    @property
    def enabled(self) -> bool:
        return self._provider is not None

    def _require(self) -> OcrProvider:
        if self._provider is None:
            raise OcrDisabledError("OCR is disabled")
        return self._provider

    def read_pdf(self, data: bytes) -> str:
        return self._require().ocr_pdf(data)

    def read_image(self, data: bytes, media_type: str) -> str:
        return self._require().ocr_image(data, media_type)


@lru_cache(maxsize=1)
def get_ocr_manager() -> OcrManager:
    """Cached for the process: changed OCR settings take effect after a restart."""
    settings = get_settings()
    if not settings.ocr_enabled:
        return OcrManager(None)
    if not settings.mistral_api_key:
        raise OcrConfigError("Mistral API key is not set")
    provider = MistralOcrProvider(
        api_key=settings.mistral_api_key,
        base_url=settings.mistral_base_url,
        model=settings.mistral_ocr_model,
        timeout=settings.ocr_timeout,
        max_bytes=settings.ocr_max_bytes,
    )
    return OcrManager(provider)
