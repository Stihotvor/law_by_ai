# Path 4: async command workflow
The page enqueues `create_user` and `deactivate_user` as Celery tasks. The worker rebuilds the principal, resolves the tenant from the DB, runs one transaction and writes the outcome to a tenant-scoped status row. The page polls. The bcrypt hash, not the plaintext, travels through Redis.
- Effort: L. It adds a task layer, a status table with a migration and a polling UI. `failed_tasks.py` is listed in the README but missing, so ADR-0006 persistence may need building.
- Risks: the hash sits in the broker and in failure records. Latency and a cold worker conflict with the 1 second target. A forged message needs a DB re-check of the actor on every run.
