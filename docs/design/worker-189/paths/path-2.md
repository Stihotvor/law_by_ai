# Path 2: central lifecycle registry

- Structure: new `src/tasks/lifecycle.py` with `register_closable(name, peek, close)` and `close_all()`. `celery_app.py` connects one `worker_process_shutdown` handler that calls `close_all()`. `fetch.py` registers peek/close for its module-level `_store` at import.
- Contract: `close_all()` skips entries whose `peek()` is None; else `close()` once; errors logged as warning and swallowed, other entries still run; cache cleared in `finally`; re-register replaces.
- Unit tests: as path 1, plus failing entry does not block others, re-register replaces, signal wiring.
- Integration: real store, signal, `pool.checkedout() == 0`, cache empty.
- Main risk: more machinery than one store needs (no second consumer yet). Wider diff-cover and mutation surface. Touches `celery_app.py`.
- Effort: M (new module, two edits, about 8 unit tests + 1 integration).
