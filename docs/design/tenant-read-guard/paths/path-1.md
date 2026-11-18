# Path 1: predicates in the SQL of every statement

Lens: the tenant filter lives in the SQL `WHERE` of each statement. Each predicate has one source.

## Changes
- `_readable_by(tenant)`: read predicate. `tenant` set gives `or_(tenant_id == tenant, tenant_id.is_(None))`. `None` gives `tenant_id.is_(None)`.
- `_owned_by(tenant)`: write predicate, `tenant_id.is_not_distinct_from(tenant)`. `_owned_row_for_update` uses it.
- `get_document`: `select(LegalDocument).where(id == :id, _readable_by(T))`, then `scalar_one_or_none()`. Replaces `session.get`.
- `search_documents` and `get_recent_changes`: add `_readable_by(T)` to the existing `WHERE`.
- `delete_document`: `delete(LegalDocument).where(id == :id, _owned_by(T))` in one transaction. Zero rows is a no-op. `reject` already uses a Core delete, so this is not a new pattern.

## Fit
- T2, T3, E1, E2: met. The tenant is a bound parameter in SQL.
- E6: met. The database applies `LIMIT` after the filter.
- F1-F3: met. Check and delete are one atomic statement, so there is no race window.

Effort: S. About 20 changed lines and two small helpers.

## Risks
1. The Core delete skips ORM cascades and `before_delete` hooks. Today `LegalDocument` has none in use (the reject path deletes the same way).
2. `get_document` no longer uses the identity map. This has no effect, because each call opens a new session.
