# Security

Authentication and authorization (ADR-0004) plus tenant-isolation helpers
(ADR-0003).

- `auth.py` — JWT issue/verify
- `rbac.py` — role checks (`admin` / `user`)
- `tenant.py` — `tenant_id` context helpers for multi-tenant scoping
