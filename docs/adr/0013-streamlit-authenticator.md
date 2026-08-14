---
status: accepted
---

# ADR-0013: Use streamlit-authenticator for the core app (replace JWT)

## Context

ADR-0004 prescribed JWT-based authentication: short-lived RS256 access
tokens, Redis-backed refresh-token rotation, and a framework-agnostic
`core/security/` token layer. Early implementation (issue #52 branch) showed
this was overkill for the current shape of the product:

- The UI is a single Streamlit process; there is **no public API** and no
  micro-service that needs to validate tokens independently.
- JWT brought real operational weight: RSA key generation/mounting, token
  TTL/refresh bookkeeping, a Redis revocation store, and session-refresh
  plumbing in Streamlit — all for one login page.
- `streamlit-authenticator` provides battle-tested login/logout widgets,
  bcrypt password handling, signed session cookies, and failed-attempt
  tracking out of the box.

Multi-tenant isolation (ADR-0003) is unaffected: `tenant_id` still threads
through the `core/security/tenant.py` contextvar and is enforced by
PostgreSQL RLS / collection / subgraph scoping. The tenant and role are read
from the authenticated session instead of a JWT claim.

## Decision

- Replace the JWT auth layer (`auth.py`, `token_store.py`, key management,
  refresh flows) with **streamlit-authenticator** for the Streamlit app.
- Users live in PostgreSQL (`users`, `tenants` tables, bcrypt hashes) and are
  exposed to the authenticator as credentials; a bundled dev admin keeps the
  app runnable without a database.
- The UI adapter (`ui/components/auth.py`) keeps the existing surface:
  `login_form()`, `logout_button()`, `require_auth()`, `get_current_user()`,
  `is_admin()` / `require_admin()`, and threads `tenant_id` into the
  contextvar after login.
- RBAC (`core/security/rbac.py`) and tenant context
  (`core/security/tenant.py`) stay as-is; `hash_password()` /
  `check_password()` move to `core/security/passwords.py` (bcrypt).
- JWT may return later if a public API or service split requires it.

## Consequences

- **Positive**
  - Much smaller security surface: no signing keys, no token store, no
    refresh machinery.
  - Login/logout, cookie sessions, and failed-attempt tracking come from a
    maintained library.
  - The PostgreSQL user store doubles as the single source of truth for
    credentials (no YAML credential file).
- **Negative**
  - Authentication is tied to the Streamlit process; a future public API
    will need its own auth layer (OAuth2/JWT) — tracked as future work.
  - The authenticator's cookie is a session cookie, not a short-lived token;
    `AUTH_COOKIE_KEY` must be a strong secret in production.
- **Multi-tenant**: unchanged — RLS policies key on the session-scoped
  `app.current_tenant` setting; users/tenants tables are RLS-protected
  (ADR-0003, leak tests updated).
- **RBAC**: unchanged — `admin`/`user` roles still gate UI operations.

## Alternatives Considered

- **JWT (ADR-0004)** — stateless and service-agnostic, but heavy for a
  single-process UI; superseded by this ADR.
- **OAuth2/OIDC external IdP** — heavier still; revisit only if hosted
  identity becomes a requirement.
- **Streamlit `st.secrets`-based DIY login** — re-implements what
  streamlit-authenticator already provides (hashing, cookies, widgets).

## Related

- [ADR-0004](0004-auth-rbac.md) — superseded (RBAC retained, JWT dropped)
- [ADR-0003](0003-multi-tenancy.md) — isolation model, unchanged
- [Architecture](../architecture.md) — Security section
- [Intention](../intention.md) #27, #48, #49
