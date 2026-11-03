"""OCR errors. A separate family: ocr/ must not import formats/."""


class OcrError(Exception):
    """Base class for OCR errors."""


class OcrDisabledError(OcrError):
    """OCR is off; nothing was sent."""


class OcrConfigError(OcrError):
    """OCR is enabled but the key or URL is invalid."""


class OcrInputError(OcrError):
    """Input is empty, too large, or has an unsupported media type."""


class OcrProviderError(OcrError):
    """HTTP, transport or response failure."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
