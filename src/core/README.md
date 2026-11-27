# Core (application kernel)

`core/` is the dependency-inversion kernel of the application. It defines the
**contracts** (plugin SPI, deprecated per ADR-0014) and **cross-cutting
concerns** (security, observability). `core/` depends on nothing else in the
project; every other package imports it, never the other way around.

- `plugins/` — **DEPRECATED (ADR-0014)**: the plugin API (`Protocol`s,
  `PluginManager`, exceptions). PostgreSQL no longer routes through it.
- `security/` — auth, RBAC, tenant context (ADR-0013, ADR-0003)
- `observability/` — structlog JSON logging, OTel metrics/traces (ADR-0005)
- `procedures/` — procedure knowledge base for the bureaucracy assistant: `models`, `errors`, `parse` (YAML to a validated `Procedure`), `ports` (`ProcedureRepository`) and `service` (`ProcedureService`). The SQL adapter is `src/plugins/relational_db/procedures.py`.
