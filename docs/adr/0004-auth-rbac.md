---
status: proposed
---

# ADR-0004: JWT auth + RBAC (admin/user)

## Context

The platform holds legal data and tenant-private state. Any UI/backend access
must be authenticated, and not every user should be able to mutate data. The
original plan had no explicit auth story.

## Decision

- **Authentication**: JWT issued on login; validated on every request and
  reflected in Streamlit session state.
- **Authorization (RBAC)**:
  - `admin` — manages data: ingest documents, edit/delete, manage users.
  - `user` — read-only: search, browse, query, view diffs.
- Enforced in a shared auth/RBAC layer (`core/security/`) used by the UI and
  agents; tenant context (`tenant_id`) threaded from the token.
- Tokens are short-lived; refresh/rotation handled by the auth layer.

## Consequences

- Secure-by-default: all pages and operations require a valid token.
- Clear separation of data management vs. consumption.
- Adds a user/tenant model and login flow to PostgreSQL and UI.
- RBAC must be tested (privilege escalation tests) alongside tenant leak tests.

## Alternatives Considered

- **Session cookies only** — less flexible for future API/server use.
- **OAuth2/OIDC external IdP** — heavier than needed for a self-hosted MVP.

## Related

- [Architecture](../architecture.md) — Security, Streamlit UI
- [Intention](../intention.md) #27, #48, #49
