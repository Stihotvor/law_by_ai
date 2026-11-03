"""Safety limits and typed errors shared by the office format parsers."""

from agents.fetch.formats.base import FormatError

MAX_PDF_PAGES = 1000
MAX_ZIP_ENTRIES = 1000
MAX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024  # sum of declared entry sizes
MAX_BODY_BYTES = 16 * 1024 * 1024  # declared size of word/document.xml (lxml expands it)
MAX_COMPRESSION_RATIO = 200  # per entry, only when entry size > RATIO_MIN_BYTES
RATIO_MIN_BYTES = 1024 * 1024
MAX_NESTING_DEPTH = 8  # tables inside tables


class CorruptDocumentError(FormatError):
    """Bytes are not a valid document of this format."""


class EncryptedDocumentError(FormatError):
    """Document is encrypted and cannot be opened."""


class NoTextLayerError(FormatError):
    """No extractable text. A scan needs OCR."""
