---
status: proposed
---

# ADR-0016: Registry and strategy design for the document fetcher

## Context

The Document Fetcher agent gets legal documents from several sources. Each
source has its own base URL and its own transport. Some sources offer a REST
API. Some sources have only web pages. Some documents arrive as files in object
storage. The documents come in many formats, and some are scans.

The code needs a clear way to add a source, to choose a transport, and to read
a format. ADR-0014 deprecated the plugin system, so the design must not bring
it back. The project has one maintainer. The design must stay small, typed, and
easy to review.

OCR raises a privacy question. A scanned document has no text layer. A
hosted OCR service reads the document content. That content then leaves the
self-hosted deployment.

## Decision

1. **Strategy pattern for transport.** A `FetchStrategy` Protocol defines the
   transport: list references, read metadata, read bytes. Three strategies
   implement it: REST API, Tavily, and MinIO bucket. A Protocol fits
   because the strategies share no state.
2. **One hardcoded class per legal source.** Each source class declares its
   `name`, its `base_url` (HTTPS only), and its `strategy_name` in code. The
   class returns raw bytes. It does not parse them.
3. **Decorator registry.** A generic `Registry[T]` lives in a module that
   imports nothing from the project. A source registers itself with
   `@SOURCES.register("name")`. A strategy does the same with `STRATEGIES`. A
   new source needs no edit to a central list.
   - The registered name equals the module file name.
   - A duplicate name fails at import time.
   - A validation hook checks each source class when it registers.
4. **Module-level instances.** The registries (`SOURCES`, `STRATEGIES`) sit
   next to their base classes. They are plain module-level objects. They are not
   class-level singletons.
5. **Autoload.** Each package imports its own modules with `pkgutil`, so the
   decorators run. The loader skips `base` and names that start with `_`. It
   fails if a module does not register its own file name.
6. **Format parsers.** Parsers for each file format register in the same way.
   They follow in a later change. They turn raw bytes into text.
7. **OCR through `OcrManager`.** All OCR goes through one `OcrManager`. It has
   one provider: Mistral Document AI. OCR is **off by default**. When OCR is
   off, an image or a scanned input raises a typed `OcrDisabledError`. It is an
   error, not a result. The system parses nothing locally, and nothing leaves
   the host. The `ocr/` package is a leaf package: it imports nothing from the
   other fetcher packages. A later ADR may add
   another provider (a local model or a gateway) without a change in the
   callers.
8. **No local folder strategy.** The fetcher does not read paths from the local
   file system.
9. **REST mapping.** A source registers a small mapper in a `REST_MAPPERS`
   registry, keyed by source name. The REST strategy stays generic. The mapper
   turns the payload into the fetch contracts. It can declare id safety, an id
   pattern, and alternative content paths.
10. **Tavily policy.** Tavily uses `map` to list and `extract` to read. It does
    not use `crawl`. Each call has a cap on pages. An empty key is an error.
11. **MinIO and `base_url`.** MinIO ignores the `https://` rule on `base_url`.
    The endpoint, the bucket, and the credentials come from `Settings`. Only the
    path of `base_url` is the key prefix.

## Privacy consequence

When OCR is on, the document content goes to a third-party service outside the
self-hosted deployment. This breaks the "no document content leaves the host"
property that the stack has otherwise.

- The operator must opt in. The default stays off.
- The operator must check the legal basis for the transfer before enabling
  OCR. This includes personal data in the documents.
- The setting must be visible to the operator in the configuration and in the
  UI.
- Document content must not appear in logs, with OCR on or off.

This ADR does not give legal certainty. The owner may need a legal review of the
transfer before release.

## Relation to ADR-0014

The registry is a direct, internal pattern for fetch sources. It is not the
plugin system that ADR-0014 deprecated.

- There is no YAML registration and no Protocol validation of backends.
- `PluginManager` is unchanged. It gains no types.
- The new code does not import `core.plugins` or `plugins`.
- The fetcher does not import `PostgreSQLStore`. Persistence is a separate step.

## Consequences

- To add a source, a developer adds one file and one test.
- A source module that fails to import breaks the start of the agent. This is
  intended. A broken source must not stay hidden.
- The sources are reviewed in code and typed. The registry check at import time
  catches wrong names, non-HTTPS URLs, and unknown strategies early.
- Source configuration is not editable at run time. A change needs a code
  release. This is an accepted trade-off for a single maintainer.
- OCR is limited to one provider at first. Users who turn it off cannot read
  scanned documents.
- Tavily has a cost and a rate limit. The page cap limits the cost per call.
- Open point: the Tavily daily credit budget.
- Open point: the retention rule for rejected documents.
- Open point: the review of the Mistral data-retention terms.
- Open point: the OCR model pin.

## Alternatives Considered

- **Local folder strategy** - rejected as unsafe. A path from a source or from
  a user can reach files outside the intended folder. It adds a path-traversal
  risk for little value.
- **Per-source YAML configuration** - rejected. The sources are few, reviewed
  in code, and typed. YAML brings back the registration layer that ADR-0014
  removed, and it moves errors from import time to run time.
- **Class-level singleton registry** - rejected. Hidden global state makes
  tests depend on each other. Module-level instances next to the base classes
  are simple, and tests can use a private `Registry`.
- **Inheritance for strategies** - rejected. The strategies share no state, so
  a Protocol is enough.
