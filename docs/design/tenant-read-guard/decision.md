# Decision: tenant read guard

Status: accepted (owner, 2026-11-18). Path 1, with the owner answers to Q1 and Q2.

## Context
`get_document`, `search_documents`, `get_recent_changes` and `delete_document` accept `tenant_id` and ignore it. A tenant can read and delete a foreign row by id. `legal_document` has no RLS. No code in `src/` calls these four methods today. Only tests call them. Size S (one module, no schema change), so two paths were compared.

## Options
- Path 1, predicates in the SQL of every statement, Core delete.
- Path 2, ORM load and a Python check for single rows, SQL filter for lists.

| Row | Path 1 | Path 2 |
|---|---|---|
| Fit to constraints (T1-T6) | Full | T3 partly: rule in Python and SQL |
| Failure modes F1-F4 | Met | Met |
| Race between check and delete | None (one statement) | Gap, but no leak |
| Foreign row loaded into memory | No | Yes |
| Complexity | 2 helpers, one per rule | 1 helper, two forms of one rule |
| Effort | S | S |
| Main risk | Core delete skips ORM cascades (none today) | Python and SQL rules drift apart |

## Decision
Path 1, with these rules.
- D1. Tenant: `T = _resolve_tenant(tenant_id)`, the write-guard helper, unchanged.
- D2. Read predicate `_readable_by(T)`: `T` set gives `tenant_id = T OR tenant_id IS NULL`. `T` is `None` gives `tenant_id IS NULL`. A Python branch picks the form, because a B-tree index cannot use `IS NOT DISTINCT FROM` (dba). Used by `get_document`, `search_documents`, `get_recent_changes`.
- D3. Write predicate `_owned_by(T)`: `tenant_id IS NOT DISTINCT FROM T`, the write-guard rule. Used by `_owned_row_for_update` and `delete_document`. A tenant cannot delete a shared row.
- D4. `delete_document` returns `None`. It runs one atomic `DELETE ... WHERE id = :id AND _owned_by(T)`. A missing or foreign id is a no-op, with no error. Reasons: the public contract stays, foreign and missing give the same answer, and a Celery retry does not fail. The write guard set no precedent for delete (it only kept the existing `KeyError` of `update_document`).

## Consequences
- A tenant cannot read, list or delete a foreign row through the store.
- A tenant reads the shared corpus but cannot delete or write it.
- A no-tenant caller reads only shared rows, and can delete every shared row. Caller RBAC (`admin`) is the only guard until RLS exists.
- A caller cannot tell a failed delete from a delete of a missing id.
- Reads and writes now use different rules. The helper names make the difference clear.
- Follow-ups: see "Out of scope / follow-ups" in `requirements.md`.
