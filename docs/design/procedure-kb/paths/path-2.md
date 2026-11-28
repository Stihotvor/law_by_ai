# Path 2: database-backed, seeded

Lens: procedures and steps are shared PostgreSQL tables filled by a seed script from the same YAML files.

## Components
- `data/procedures/*.yaml` and the pydantic models and `load_procedures` in `src/data/procedures.py` (as in path 1).
- `scripts/seed_db.py` (new, absent today): load, validate, upsert in one transaction.
- Alembic migration after head `c4a91e7f2b58`: tables `procedure` and `procedure_step`, CHECK constraints (https URL, non-empty verify line, date not in the future), `UNIQUE(slug)`, `UNIQUE(procedure_id, position)`.
- ORM models, for example `src/plugins/relational_db/procedure_models.py`.
- `PostgreSQLStore.get_procedure(slug)` and `list_procedures()`.

## Data flow
An operator runs the migration and then the seed. The seed stops before any write if a file is invalid. It upserts by slug, replaces steps and deletes procedures that left the files. The assistant reads through the store with plain SELECTs. The app role gets SELECT only.

## Failure handling
Two gates: pydantic at seed and DB constraints. A failed seed rolls back. Not handled: direct SQL edits by a privileged role, and drift when nobody reruns the seed (needs a deploy step or a startup check). "At least one step" needs a deferred constraint trigger.

## Effort and risk
Effort M. Risks: a DB and a seed deploy step for 3 files of data, drift between files and rows, and SQL CHECKs that can disagree with the pydantic rules.
