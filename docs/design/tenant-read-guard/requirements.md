# Requirements: tenant read guard

Scope: `PostgreSQLStore.get_document`, `search_documents`, `get_recent_changes` and `delete_document` in `src/plugins/relational_db/postgres.py`.

Source of facts: the code at commit `bc02a46`. The owner fixed the rules below on 2026-11-18.

## Business Goals
- G1. A tenant cannot read or delete a document of another tenant through the store. This is a charter item ("tenant leak tests") for the MVP (planning date 2027-02-28).
- G2. A caller cannot learn that a foreign document exists from a read or a delete. A foreign row gives the same answer as a missing row.
- G3. Tenant users can read the shared corpus (charter: "shared documents, per-tenant data").
- G4. Close the read and delete follow-up of the tenant write guard before RLS work starts.

Decided: the store, not its callers, enforces the read rule and the delete rule.

## Technical Constraints
- T1. Python 3.13, SQLAlchemy 2.0 ORM, PostgreSQL. No new dependency. No schema change and no migration.
- T2. Reuse `_resolve_tenant` without change. The tenant is the `tenant_id` argument, else `get_current_tenant()`. `""` counts as `None`.
- T3. Two predicates, each with one source:
  - Read predicate: tenant `T` set gives `tenant_id = T OR tenant_id IS NULL`. `T` is `None` gives `tenant_id IS NULL`. A Python branch picks the form. Do not use `IS NOT DISTINCT FROM` for reads, because a B-tree index cannot use it (dba).
  - Write predicate: `tenant_id IS NOT DISTINCT FROM T`, the write-guard rule, unchanged. `_owned_row_for_update` and `delete_document` use it.
- T4. Keep the public signatures and return types of the four calls. The protocol in `src/core/plugins/protocols/relational_db.py` does not change.
- T5. Celery prefork workers do not carry the contextvar. They pass `tenant_id` as an argument.
- T6. Quality gate: ruff check, ruff format --check, pyright, pytest. Integration tests run on the Docker PostgreSQL. Coverage and mutation gates as in CONTRIBUTING.md.

## Edge Cases
- E1. Read rule: a tenant caller sees its own rows and shared rows. A no-tenant caller sees only shared rows. A foreign row is never visible.
- E2. Delete rule: the write-guard rule (`NULL` is equal to `NULL`). A tenant deletes only its own rows. A tenant cannot delete a shared row. A no-tenant caller deletes only shared rows.
- E3. A no-tenant caller can delete every shared row. Caller RBAC (`admin` role, ADR-0013) is the only guard on this path until RLS exists.
- E4. Argument and context both set and different: the argument wins.
- E5. Empty-string tenant in the argument: falls back to the context tenant. It never widens access.
- E6. `search_documents` with `limit`: the limit applies after the tenant filter.
- E7. `get_recent_changes` with `since`: the tenant filter and the `since` filter both apply.

## Failure Modes
- F1. `get_document` of a foreign id returns `None`, the same as a missing id.
- F2. `search_documents` and `get_recent_changes` omit foreign rows.
- F3. `delete_document` of a missing, foreign or (for a tenant caller) shared id is a no-op. It returns `None` and raises no error. The row stays unchanged.
- F4. No log line contains the caller tenant, the row tenant or the document id.

## Success Metrics
- M1. 100% of the QA cases pass on the Docker PostgreSQL.
- M2. `get_document`: the result for a foreign id and a missing id is equal (`None`) in 100% of the cases.
- M3. 0 foreign rows in the results of `search_documents` and `get_recent_changes`. Shared rows are in the results of a tenant caller.
- M4. 0 deleted foreign rows, and 0 shared rows deleted by a tenant caller. The kept row has all 10 `doc_to_dict` fields unchanged.
- M5. 0 regressions in the existing store tests (unit and Docker integration suite).
- M6. Coverage and mutation scores on the changed lines meet the CONTRIBUTING.md gates (no gate lowered).

## Out of scope / follow-ups
- RLS on `legal_document`.
- No index and no migration now. `legal_document.tenant_id` has no index. Add `(tenant_id, last_updated DESC)` with the RLS migration.
- `get_recent_changes` has no `LIMIT`. It returns all visible rows.
- The RLS session hook (`_set_tenant_setting`) sets the tenant from the context, not from the resolved argument. The RLS work must close this gap.
- Do not copy the `setting = ''` policy pattern of `tenants` and `users` to `legal_document`.
- `reject` stays global (no tenant check).
- Server-generated ids only.
