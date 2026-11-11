---
status: accepted
---

# ADR-0013: Use streamlit-authenticator for the core app (replace JWT)

## Context

ADR-0004 prescribed JWT-based authentication: short-lived RS256 access
tokens, Redis-backed refresh-token rotation, and a framework-agnostic
`core/security/` token layer. Early implementation (the auth branch) showed
this was overkill for the current shape of the product:

- The UI is a single Streamlit process; there is **no public API** and no
  micro-service that needs to validate tokens independently.
- JWT brought real operational weight: RSA key generation/mounting, token
  TTL/refresh bookkeeping, a Redis revocation store, and session-refresh
  plumbing in Streamlit — all for one login page.
- `streamlit-authenticator` provides battle-tested login/logout widgets,
  bcrypt password handling, signed session cookies, and failed-attempt
  tracking out of the box. (The amendment uses only the cookie.)

Multi-tenant isolation (ADR-0003) is unaffected: `tenant_id` still threads
through the `core/security/tenant.py` contextvar and is enforced by
PostgreSQL RLS / collection / subgraph scoping. The tenant and role are read
from the user row in PostgreSQL on every rerun, not from a JWT claim.

## Decision

- Replace the JWT auth layer (`auth.py`, `token_store.py`, key management,
  refresh flows) with **streamlit-authenticator** for the Streamlit app.
- Users live in PostgreSQL (`users`, `tenants` tables, bcrypt hashes). The
  amendment below describes the login flow.
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
  - Signed cookie sessions come from a maintained library.
  - The PostgreSQL user store doubles as the single source of truth for
    credentials (no YAML credential file).
- **Negative**
  - Authentication is tied to the Streamlit process; a future public API
    will need its own auth layer (OAuth2/JWT) — tracked as future work.
  - The authenticator's cookie is a session cookie, not a short-lived token;
    `AUTH_COOKIE_KEY` must be a strong secret in production.
- **Multi-tenant**: unchanged — RLS policies key on the session-scoped
  `app.current_tenant` setting; users/tenants tables are RLS-protected
  (ADR-0003). Cross-tenant leak tests are not built yet.
- **RBAC**: unchanged — `admin`/`user` roles still gate UI operations.

## Amendment (2026-11): login reads one user from the database

The library's `login()` checks passwords only against an in-memory credentials
dict. To use it, the app would have to load every user of every tenant, with
their bcrypt hashes, into each Streamlit process. That read crosses tenants,
and a deactivated user stays valid until the dict is reloaded. The app
therefore uses the library differently:

- A custom `st.form` collects email and password. The app reads one user by
  normalised email (`strip().lower()`) and checks the password with
  `check_password()`. A dummy hash keeps the timing equal when no user exists.
- streamlit-authenticator is used only for the signed session cookie
  (`CookieModel`). The cookie holds the email, never the role or tenant.
- On every rerun, `require_auth()` reads the user from PostgreSQL again and
  derives the role and `tenant_id` from that row. An inactive user or an
  invalid role ends the session.
- Each user row has a `sessions_valid_after` timestamp. Deactivation,
  reactivation and a password change set it to the current time.
  `require_auth()` rejects a cookie that was issued before that time (issue
  time = the cookie expiry minus `AUTH_COOKIE_EXPIRY_DAYS`). A copied cookie
  therefore stops working for good, also after a reactivation.
- Emails are normalised on every write as well as on login. Existing rows are
  migrated, and collisions are resolved before a check constraint is added.
- The library's failed-attempt tracking is not used. It counted per session
  only. A database-backed lockout is future work.
- There is no bundled dev admin. The database seed creates the first admin.
- The pre-tenant lookup moves to a `SECURITY DEFINER` function owned by a
  dedicated role, with fail-closed RLS policies and a non-superuser app role.
- `AUTH_COOKIE_KEY` is required, at least 32 characters, and not the library
  default. `AUTH_COOKIE_NAME` and `AUTH_COOKIE_EXPIRY_DAYS` (at least 1) are
  settings.

## Alternatives Considered

- **JWT (ADR-0004)** — stateless and service-agnostic, but heavy for a
  single-process UI; superseded by this ADR.
- **OAuth2/OIDC external IdP** — heavier still; revisit only if hosted
  identity becomes a requirement.
- **Load all users into the library's credentials dict** (amendment) — keeps
  the library's login widget and lockout, but reads every tenant's users and
  hashes into memory and misses deactivations until reload.
- **Streamlit `st.secrets`-based DIY login** — re-implements what
  streamlit-authenticator already provides (hashing, cookies, widgets).

## Related

- [ADR-0004](0004-auth-rbac.md) — superseded (RBAC retained, JWT dropped)
- [ADR-0003](0003-multi-tenancy.md) — isolation model, unchanged
- [Architecture](../architecture.md) — Security section
- [Intention](../intention.md) #27, #48, #49
