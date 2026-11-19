# Path 2: minimal inline

- `migrations/env.py`: add `compare_server_default=True` to both `context.configure` calls.
- Tests run `alembic.command.check(cfg)`, which runs env.py, so env.py is the only option source.
- New drift test: change `LegalDocument.__table__.c.status.server_default`, assert `command.check` raises, restore in `finally`.
- `models.py`: comment above the CHECK that the name is final.
- Unit test: `"ck" not in Base.metadata.naming_convention`.

Failure modes: one option source; drift raises; a convention fails the unit test.
Not handled: cast false positive; the diff list is not visible (only a raise), so the `modify_default` metric is weak.
Effort: S. Main risk: `command.check` runs env.py with the advisory lock and the owner URL from the test config; the mutation of shared metadata leaks if the restore fails.
