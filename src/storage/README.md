# Storage

Storage module for raw documents and blobs (source files, OCR output, rendered
text) — the durable artifact layer that sits alongside the `DatabasePlugin`
(metadata/chunks). Provides an interface for persisting and retrieving document
files; concrete backends (local filesystem, object store) are added as the
platform evolves.
