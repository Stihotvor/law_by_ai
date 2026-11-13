# Path 2: split connections

The app holds two engines. A tenant engine connects as `lawbyai_app` (NOBYPASSRLS). A small auth engine connects as `lawbyai_auth` (LOGIN, BYPASSRLS) and only the login lookup uses it.

## Components
- The tenant engine keeps the `begin` hook. The auth engine has no hook and a pool of 1 to 2 connections.
- An init script creates three roles. Compose and settings get a second DSN and a second password.

## Roles and grants
- `lawbyai_app` gets DML on the tables.
- `lawbyai_auth` gets column SELECT on `users` only.
- `lawbyai_owner` runs migrations.

## Migration
The roles check, the email check, the CHECK and the fail-closed policies are the same as in path 1. There is no function.

## Code change
- `get_login_user` selects explicit columns through the auth engine.
- A startup assertion checks the attributes of both roles.

## Failure modes
All listed failure modes are handled. It deviates from the requirements: `lawbyai_auth` is LOGIN, and the pg_proc metrics do not apply.

## Assessment
- Complexity: two engines, two pools and two secrets.
- Effort: M.
- Main risk: the app process holds a BYPASSRLS login that can read every `password_hash`. An SQL injection is not limited to one row.
