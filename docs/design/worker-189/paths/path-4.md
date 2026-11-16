# Path 4: per-process provider in storage layer

- Structure: `get_store()` / `close_store()` with module-level `_store` and a `threading.Lock` next to `PostgreSQLStore` in `postgres.py`. `fetch.py` calls `get_store()`. `celery_app.py` connects the shutdown handler to `close_store()`.
- Contract: `get_store()` returns one process-wide store, built lazily. `close_store()` never raises; none cached -> no build; else clear first, `close()` once, warning on error. Twice -> `close` once.
- Unit tests: as path 1, plus double close, autouse reset fixture for the module global.
- Integration: real store, `close_store()`, `pool.checkedout() == 0`, cache None.
- Main risk: moves scope into the storage layer and `celery_app.py` (a requirements exception). Module global in a shared module can leak between tests. Reuse by Streamlit is speculative today.
- Effort: S-M (about 25 lines across 3 files).
