# Path 1: file-based, read-only content

Lens: procedures are reviewed YAML files in the repo. No database table and no seed script.

## Components
- `data/procedures/{pesel,residence-card,tax-id}.yaml`: one procedure per file. The `slug` field names the procedure. The file name is not trusted.
- `src/data/procedures.py`: frozen pydantic models and the loader.
  - `Step` (`extra="forbid"`): `text`, `source_url` (https only, no credentials), `last_checked` (a date, not in the future), `verify_with_office` (non-empty line).
  - `Procedure` (`extra="forbid"`): `schema_version` (Literal[1]), `slug`, `title`, `steps` (at least 1).
- `ProcedureLoadError(file, step_index, reason)`.
- `tests/unit/test_procedures_schema.py`.

## Interfaces
- `load_procedures(directory: Path = DEFAULT_DIR) -> dict[str, Procedure]`. Raises `ProcedureLoadError`.
- `list_procedures() -> list[Procedure]`, sorted by slug, `[]` for an empty directory.
- `get_procedure(slug: str) -> Procedure | None`. `None` means not found.
- The two public calls use a lazy cache over the default directory.

## Data flow
First call loads each `*.yaml` in sorted order with `yaml.safe_load`, validates it, wraps `ValidationError` and `YAMLError` into `ProcedureLoadError`, checks duplicate slugs, and caches an immutable registry.

## Failure handling
Fail closed: one invalid file stops the load and names the file. Schema drift is pinned by `schema_version` and a field-pin test. The owner gate is a PR rule. A bad file on `main` fails on first use, so a CI test over the real `data/procedures/` directory gates merge.

## Effort and risk
Effort S. Risks: one bad file takes all procedures down (guard: the CI test), content updates need a deploy, and the issue text names `scripts/seed_db.py`, so the issue must be amended.
