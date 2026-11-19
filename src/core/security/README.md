# Security

Authentication and authorization (ADR-0013) plus tenant-isolation helpers
(ADR-0003).

- `passwords.py` — bcrypt hash and check
- `login_throttle.py` — failed-login throttling
- `principal.py` — request principal and admin guard
- `rbac.py` — role checks (`admin` / `user`)
- `tenant.py` — `tenant_id` context helpers for multi-tenant scoping
