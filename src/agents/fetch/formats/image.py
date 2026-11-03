"""Image parser (PNG, JPEG): text comes from the OCR manager."""

from typing import ClassVar

from agents.fetch.formats._safety import CorruptDocumentError
from agents.fetch.formats.base import FORMATS
from agents.fetch.formats.text import finish_ocr_text
from agents.fetch.ocr.manager import get_ocr_manager

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_JPEG_MAGIC = b"\xff\xd8\xff"


def _media_type(data: bytes) -> str:
    if data.startswith(_PNG_MAGIC):
        return "image/png"
    if data.startswith(_JPEG_MAGIC):
        return "image/jpeg"
    raise CorruptDocumentError("not a png or jpeg image")


@FORMATS.register("image")
class ImageParser:
    suffixes: ClassVar[tuple[str, ...]] = (".png", ".jpg", ".jpeg")
    mime_types: ClassVar[tuple[str, ...]] = ("image/png", "image/jpeg")

    def parse(self, data: bytes, *, charset: str | None = None) -> str:
        media_type = _media_type(data)
        return finish_ocr_text(get_ocr_manager().read_image(data, media_type))
