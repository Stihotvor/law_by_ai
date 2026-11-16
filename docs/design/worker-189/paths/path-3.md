# Path 3: task-owned resource (Celery Task base)

- Structure: `fetch.py` only. `class _StoreTask(celery.Task)` with lazy `store` property and `close_store()`. `fetch_document` uses `base=_StoreTask, bind=True` and reads `self.store`. A `worker_process_shutdown` handler calls `fetch_document.close_store()`. `functools.cache` removed.
- Contract: first `.store` builds one store; `close_store()` with none cached builds nothing; else clears `_store` first, then `close()` once, warning on error.
- Unit tests: as path 1, with patches on the property or `_store`. Existing `fetch_document` tests change for `bind=True`.
- Integration: real store via `.store`, signal, `pool.checkedout() == 0`, `_store is None`.
- Main risk: `bind=True` changes the task signature for direct calls in tests; every `_make_store` patch must change.
- Effort: S (one file plus test edits; Celery's documented pattern).
