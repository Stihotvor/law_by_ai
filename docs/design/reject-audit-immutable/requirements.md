# Requirements: reject audit is append-only

## Business Goals
- An admin's reject decision is an audit record. Nobody can change or delete it through the app role `lawbyai_app`.
- The actor in the record is the authenticated admin. A caller cannot write another person's email.
- The retention rule is decided: rows are kept forever. Only the migration owner `lawbyai_owner` can fix or purge a row by hand. ADR-0016 records this rule.
- Why now: the table exists (migration `963e40b83003`) and `b7e2d41c9a30` grants UPDATE and DELETE on it to the app role. The table is not yet used by a production caller, so the change is cheap now.

## Technical Constraints
- PostgreSQL with three roles from `docker/initdb/00-roles.sh`: `lawbyai_owner` (owns objects, runs Alembic), `lawbyai_app` (app and worker), `lawbyai_auth` (NOLOGIN).
- The change is one new Alembic revision after head `b7e2d41c9a30`. It revokes UPDATE, DELETE and TRUNCATE on `rejected_document` from `lawbyai_app`. SELECT and INSERT stay. The sequence grants stay.
- The owner keeps all rights (user decision: owner only, no trigger).
- `PostgreSQLStore.reject` takes the actor from the request context, the same way the tenant guard reads `core.security.tenant`. It no longer takes a free `admin` argument.
- The actor value comes from the authenticated session (`get_current_user()` in `src/ui/components/auth.py`) and is set in the context by the UI layer. The store does not import the UI.
- No new dependency. Python 3.13, SQLAlchemy 2.x, Alembic.

## Edge Cases
- `reject()` runs with no actor in the context: it raises an error before any write. No document is deleted and no audit row is written.
- The actor in the context is an empty or blank string: same as no actor.
- Two concurrent rejects of one document: unchanged, only one deletes the row and writes the audit row.
- The app role runs `UPDATE`, `DELETE` or `TRUNCATE` on `rejected_document`: PostgreSQL denies it with SQLSTATE `42501`.
- The app role runs `INSERT` and `SELECT`: both still work.
- The migration downgrade, run as the owner: it restores UPDATE and DELETE to the app role, as in `b7e2d41c9a30`, and TRUNCATE only if `b7e2d41c9a30` granted it.

## Failure Modes
- A later migration runs `GRANT ALL ON ALL TABLES` to the app role and silently restores UPDATE and DELETE. A test must catch this: it checks `has_table_privilege` for the app role on the head schema.
- A caller sets the actor in the context and never clears it, so a later reject in the same thread uses a stale actor. The context helper must reset the value after the request (same pattern as the tenant context).
- The reject fails because no actor is set: the UI shows an error, and the document stays.
- What must survive: every existing audit row, the reject transaction (delete plus insert in one transaction), and the owner's ability to downgrade.

## Success Metrics
- 3 of 3 denied statements: an integration test as `lawbyai_app` gets `42501` for UPDATE, DELETE and TRUNCATE on `rejected_document`.
- 2 of 2 allowed statements: INSERT and SELECT as `lawbyai_app` succeed.
- 1 test: `reject()` with no actor raises and writes 0 rows.
- 1 test: the audit row's actor equals the actor in the context, not any caller argument.
- Upgrade, downgrade and upgrade again pass as the owner in the Docker suite, with 0 failures.
- Quality gate: ruff, ruff format --check, pyright and pytest pass. diff-cover is 90% or more on changed lines.
