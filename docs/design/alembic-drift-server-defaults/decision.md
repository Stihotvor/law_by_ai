# Decision: Alembic drift test compares server defaults

## Context
The drift test calls `compare_metadata` with no options, so Alembic 1.20.1 does not compare server defaults. A changed model default passes silently. Alembic 1.20.1 does not compare CHECK constraints by default (name-based detection is an opt-in plugin, not enabled here). The CHECK name `ck_legal_document_status` would change if someone adds a naming convention with a `%(constraint_name)s` ck token.

## Options
- Path 1: one shared options dict used by `env.py` and the test, `conv()` pins the CHECK name, and a drift test on an isolated metadata copy.
- Path 2: inline flags in `env.py`, tests run `command.check` through `env.py`, and a comment plus a convention guard protect the name.

## Decision
Path 1, chosen by the owner at G1. Reviewer fixes are included:
- New `src/data/autogen.py` holds `AUTOGEN_COMPARE_OPTS = {"compare_server_default": True}`. It is a plain dict with no Alembic import.
- `migrations/env.py` spreads the dict into the online `context.configure`. It also spreads it into the offline call, with a comment that says this is for parity only, because autogenerate does not run offline.
- `src/data/models.py` names the CHECK `conv("ck_legal_document_status")`. The DDL name stays byte-identical to the plain string in migration `963e40b83003`.
- `test_autogenerate_finds_no_changes` passes `opts=AUTOGEN_COMPARE_OPTS` and still asserts `diff == []`.
- A new integration test copies every table of `Base.metadata` with `Table.to_metadata()` into a fresh `MetaData`, so no `remove_table` and no missing FK target appear. It changes the `status` server default on the copy, flattens the nested diff, and asserts exactly 1 `modify_default` entry for `legal_document.status`. `Base.metadata` stays unchanged.
- A new unit test builds a `MetaData` with `naming_convention={"ck": "ck_%(table_name)s_%(constraint_name)s"}`, copies the table into it, and asserts the CHECK name is exactly `ck_legal_document_status`.
- The `pg_get_constraintdef` test stays as the guard of the CHECK text.

## Consequences
- The test and `env.py` read one dict, so their options cannot differ.
- Accepted gap: the test does not run `env.py` itself. `env.py` has no `include_object` or other compare hooks today, so both runs give the same result.
- No false drift is expected (dba): `'needs_review'` is compared on the server, and `0` matches as text. The 0-diff test confirms this.
- No migration file and no schema change.
