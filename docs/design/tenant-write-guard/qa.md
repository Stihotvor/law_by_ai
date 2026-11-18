# QA cases: tenant write guard

Setup: rows `A1` (tenant `A`), `B1` (tenant `B`), `S1` (shared, `NULL`). "Unchanged" means all 10 `doc_to_dict` fields are equal before and after (M2). All cases run on the Docker PostgreSQL.

### QA-1
Covers: T2, E3
Given the context tenant is `A`
When `save_document` inserts a new row with payload `tenant_id="B"`
Then the row has `tenant_id="A"` and the warning names `tenant_id`

### QA-2
Covers: T2, E1c
Given no context tenant and no argument
When `save_document` inserts a new row with payload `tenant_id="B"`
Then the row has `tenant_id` NULL

### QA-3
Covers: E4, F2, M3a
Given the context tenant is `A`
When `save_document({"id": "B1", ...})` runs
Then it raises `StoreDocumentNotFoundError` with the text `Document not found: B1` and no new row exists

### QA-4
Covers: F1
Given the context tenant is `A`
When `update_document("B1", {"title": "x"})` runs
Then it raises `StoreDocumentNotFoundError` and `B1` is unchanged

### QA-5
Covers: G2, M3
Given the context tenant is `A`
When `update_document` runs for `B1` and for an id with no row
Then both raise the same type with the text `Document not found: <id>`

### QA-6
Covers: E1a
Given the context tenant is `A`
When `update_document("S1", ...)` and `save_document({"id": "S1", ...})` run
Then both raise `StoreDocumentNotFoundError` and `S1` is unchanged

### QA-7
Covers: E1b
Given no tenant
When `update_document("A1", {"title": "x"})` runs
Then it raises `StoreDocumentNotFoundError` and `A1` is unchanged

### QA-8
Covers: E1, E1d
Given no tenant
When `update_document("S1", {"title": "x"})` runs
Then the title is `x` and `tenant_id` stays NULL

### QA-9
Covers: E2
Given the context tenant is `B` and the argument is `A`
When `update_document("A1", {"title": "x"}, tenant_id="A")` runs
Then the title is `x`

### QA-10
Covers: T2, F6
Given the context tenant is `A`
When `update_document("A1", {"title": "x", "tenant_id": "B"})` runs
Then the title is `x`, `tenant_id` stays `A`, and the warning holds the operation name and `tenant_id`, but no value and no document id

### QA-11
Covers: E5
Given the context tenant is `A` and the argument is `""`
When `update_document("S1", {"title": "x"}, tenant_id="")` runs
Then it raises `StoreDocumentNotFoundError`, `S1` is unchanged, and `update_document("A1", {"title": "y"}, tenant_id="")` sets the title of `A1` to `y`

### QA-12
Covers: F3
Given a `StoreDocumentNotFoundError` is raised
When an `except KeyError` handler wraps the call
Then the handler catches it, `str(exc)` has no quotes, and `isinstance(exc, LookupError)` is true

### QA-13
Covers: F2
Given the context tenant is `A` and a payload dict `{"id": "B1", "title": "x", ...}`
When `save_document` raises `StoreDocumentNotFoundError`
Then `B1` is unchanged and the payload dict is equal to a copy taken before the call

### QA-14
Covers: F5
Given two sessions on two database backends and one new id with no row
When session 1 runs the lookup and the insert and keeps the transaction open, and session 2 runs the lookup (it misses) and the insert in a second thread
And the test waits until `pg_blocking_pids` of backend 2 contains backend 1, then commits session 1
Then session 1 returns the id and session 2 raises `IntegrityError`

### QA-15
Covers: F7
Given the context tenant is `A` and the flush of an `A1` update raises `StaleDataError`
When `update_document("A1", {"title": "x"})` runs
Then it raises `StoreDocumentNotFoundError` with the text `Document not found: A1` and the session rolls back

### QA-16
Covers: T7
Given session 1 holds the lock on `A1` through an open `update_document` transaction for tenant `A`
When `update_document("A1", {"title": "x"})` runs for tenant `B` in session 2
Then session 2 raises `StoreDocumentNotFoundError` at once, without a wait on the lock of session 1
