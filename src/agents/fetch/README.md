# Fetch

Document fetching for legal sources: list, read metadata, download raw bytes.
Layout: `registry.py` (generic name registry), `errors.py` (typed errors), `contracts.py` (pydantic models),
`strategies/` (transports), `sources/` (one module per legal source),
`formats/` (parsers: bytes to text), `ocr/` (OCR manager and Mistral adapter, off by default),
`document_fetcher.py` (agent).
Modules in `strategies/`, `sources/`, and `formats/` are autoloaded; `base.py` and `_*` modules are skipped.
Rule: module stem == registered name.
The agent caches one strategy per source; call `close()` (or use it as a context manager) to release them.
`tenant_id` must match `[A-Za-z0-9_-]{1,64}`. The REST strategy rejects loopback, link-local
and private hosts unless the source sets `allow_private_hosts`. A fetch body read stops after `FETCH_TOTAL_TIMEOUT`.
Hosts are resolved at request time (initial URL and every redirect) and rejected unless all addresses are
global; the connection is not pinned to the checked address, so a DNS rebinding window remains.
