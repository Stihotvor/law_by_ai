# Fetch

Document fetching for legal sources: list, read metadata, download raw bytes.
Layout: `registry.py` (generic name registry), `contracts.py` (pydantic models),
`strategies/` (transports), `sources/` (one module per legal source),
`formats/` (parsers: bytes to text), `ocr/` (OCR manager and Mistral adapter, off by default),
`document_fetcher.py` (agent).
Modules in `strategies/`, `sources/`, and `formats/` are autoloaded; `base.py` and `_*` modules are skipped.
Rule: module stem == registered name.
