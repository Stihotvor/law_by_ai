# Fetch

Document fetching for legal sources: list, read metadata, download raw bytes.
Layout: `registry.py` (generic name registry), `contracts.py` (pydantic models),
`strategies/` (transports), `sources/` (one module per legal source), `document_fetcher.py` (agent).
Modules in `strategies/` and `sources/` are autoloaded; `base.py` and `_*` modules are skipped.
Rule: module stem == registered name.
