---
status: proposed
---

# ADR-0007: Git-backed document-level diffs

## Context

The ChangeTrackerAgent must track version changes of legal documents
(document-level granularity per the Intention doc). Legal updates (e.g., an
amendment to a statute) need reliable diffing and version history.

## Decision

- **Document-level diffs**, most likely backed by **Git** for versioning and
  comparison:
  - Raw text/parsed versions of each document are stored in a Git repository
    (one branch/namespace per document or a flat versioned store).
  - `ChangeTrackerAgent` generates diffs via Git history (`git diff`) between
    versions.
  - The UI presents version comparison (changes page) from these diffs.
- Where Git is impractical (binary/OCR-heavy sources), a structured version
  table in PostgreSQL stores per-version metadata + precomputed diffs, with
  Git as the canonical source for text documents.

## Consequences

- Reliable, auditable version history with cheap diffs.
- Reuses well-tested tooling instead of custom diff logic.
- Adds a Git store container/volume to the deployment.
- Document-level granularity (not section-level) keeps MVP scope tight.

## Alternatives Considered

- **Pure PostgreSQL JSONB version snapshots** — no diff tooling; diffs would be
  custom and fragile.
- **Section/paragraph-level diffs** — more granular but out of MVP scope.

## Related

- [Architecture](../architecture.md) — ChangeTrackerAgent, Changes Tracking UI
- [Intention](../intention.md) #38
