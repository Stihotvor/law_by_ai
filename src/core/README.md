# Core (application kernel)

`core/` is the dependency-inversion kernel of the application. It defines the
**contracts** (plugin SPI) and **cross-cutting concerns** (security,
observability). `core/` depends on nothing else in the project; every other
package imports it, never the other way around.

- `plugins/` — the plugin API: `Protocol`s, `PluginManager`, exceptions (ADR-0001)
- `security/` — JWT auth, RBAC, tenant context (ADR-0004, ADR-0003)
- `observability/` — structlog JSON logging, OTel metrics/traces (ADR-0005)
