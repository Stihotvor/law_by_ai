# Path 3: database-centric enforcement
A new Alembic migration adds SQL functions `admin_create_user` and `admin_deactivate_user`, a `ck_users_role_valid` check and a `trg_users_last_admin` backstop trigger. PostgreSQL enforces tenant, role, last admin and self-deactivation. Python hashes the password, calls the function and maps errors. A thin service adds `require_admin_principal` and the audit log.
- Effort: M.
- Gain: the invariants hold for every caller, including the seed script and a future buggy service.
- Risks: the drift test and the RLS hardening checks (owners, grants) must grow. Rules split across SQL and Python can drift. The mutation and coverage gates do not measure plpgsql. Hard to debug. Downgrade is complex.
