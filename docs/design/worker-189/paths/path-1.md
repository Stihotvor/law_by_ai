# Path 1: local handler

- Structure: `src/tasks/fetch.py` only. Module-level `_store: PostgreSQLStore | None` replaces `functools.cache`. `_close_store(**kwargs)` is connected with `@worker_process_shutdown.connect`. Fix the stale migration comment.
- Contract: kwargs ignored, returns None, never raises. Empty cache: no store built. Else `close()` once in try/except, warning with `exc_info`, `finally` clears the cache.
- Unit tests: 0 constructions with empty cache; 1 `close()` after many `_make_store()`; close raises -> warning, cache empty; new instance after close; signal send triggers handler.
- Integration: real store, one query, send signal, saved engine has `pool.checkedout() == 0`, cache empty.
- Main risk: receiver connects only when `tasks.fetch` is imported (`include=["tasks.fetch"]` ensures it). A future task module with its own cache needs its own handler.
- Effort: S (about 15 lines, one file).
