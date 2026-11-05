---
status: proposed
---

# ADR-0017: SeaweedFS as the S3 object store

## Context

The document fetcher (ADR-0016) has a MinIO strategy. It reads documents from
an S3 bucket through the Python `minio` SDK. The first-start init also needs an
S3 store. The compose stack has no S3 service yet. The first plan was to run
the MinIO community image.

MinIO community edition is no longer a safe base:

- MinIO stopped publishing community images on Docker Hub and Quay in October
  2025.
- The upstream repository shows "no longer maintained" and is read-only. The
  repository banner gives 2026-04-25 as the archive date. One aggregator says
  February 2026. This conflict is not resolved.
- The last upstream release is `RELEASE.2025-10-15`.
- A tutorial dated 2026-01-28 confirms that the images do not get updates. It
  says that the old Quay examples still run.
- On 2026-11-05, an anonymous pull of `minio/minio` from Docker Hub failed
  (repository missing or needs authorization). Quay returned 401.

The stack must fit in 4-6 GB RAM. The data is a few GB of legal PDFs on a
single node.

### Spike

The maintainer ran one spike on 2026-11-05 on the dev host (Docker 28.5.1).
Each candidate got the same test:

- Six `minio` SDK calls: `bucket_exists`, `make_bucket`, `put_object`,
  `stat_object`, `get_object`, `list_objects`.
- A hardened container: read-only root, `cap_drop: ALL`, and
  `no-new-privileges`.
- Idle RAM from `docker stats`.
- A crash test: write 200 objects of 4 KiB and one 20 MB multipart object, send
  `docker kill -s KILL`, restart, and verify all bytes.

Four candidates passed all tests.

| Candidate | License | Idle RAM | User | Notes |
|-----------|---------|----------|------|-------|
| SeaweedFS 4.52 (`chrislusf/seaweedfs:4.52`) | Apache-2.0 | 38 MiB | UID 1000 | Image is 780 MB. Entrypoint override needed. Telemetry on by default. |
| Silo (`pgsty/minio` fork) | AGPL | 69 MiB | root, caps dropped | Docker Hub image lags the GitHub release. One company controls the fork. |
| Chainguard MinIO (`cgr.dev/chainguard/minio`) | not checked | 60 MiB | UID 65532 | Free tier shows only `latest`. Terms not verified. |
| Garage 2.5.0 | AGPL | 7 MiB | root, caps dropped | Single node is not an intended use case. |

SeaweedFS details from the spike:

- The `seaweed` user owns `/data` in the image, so a fresh named volume works.
- The default entrypoint fails when all capabilities are dropped
  (`su-exec: setgroups`). Compose must set the entrypoint to `/usr/bin/weed`.
- SeaweedFS sends anonymous statistics to `telemetry.seaweedfs.com` by
  default. The flag `-master.telemetry=false` turns this off.
- The S3 keys come from a JSON file (`-s3.config`). The bucket comes from
  `-bucket`.
- The spike did not test a healthcheck.

### Engineer opinion

This evidence is weak. It comes from Hacker News threads (about spring and
September 2026) and from blogs. SeaweedFS had the most positive single-node
reports. One blog (2026-07-30) reports 30-50 MB idle RAM. Engineers also warn
about sparse docs, and one report describes a failure under concurrent writes.
The maintainer could not reach or find Reddit, lobste.rs, or conference talks
on this topic.

## Decision

1. **SeaweedFS in `weed mini` mode is the S3 object store.** It serves the
   fetch MinIO strategy and the first-start init. The license is Apache-2.0.
2. **The client stays.** The Python `minio` SDK stays as the client. It uses
   the S3 API, so the strategy code does not change.
3. **Only the compose service changes.** `weed mini` runs master, volume,
   filer, and S3 in one process, so the stack has one container for the store.

## Not verified

The spike does not prove these points. Treat them as open risks.

- Power-loss durability for every candidate. `kill -9` keeps the OS page
  cache, so the crash test does not simulate a power loss.
- Behaviour under concurrent writes.
- A vulnerability scan of the image.
- The SeaweedFS healthcheck command.
- How Dependabot handles an image pinned by tag and digest.
- How SeaweedFS ages with several GB of data.
- The effect of the 780 MB SeaweedFS image on small hosts.

## Consequences

- Pin the image by tag and by digest.
- Override the entrypoint to `/usr/bin/weed`.
- Turn telemetry off with `-master.telemetry=false`.
- Supply the S3 keys from a mounted file or from env that the init renders. The
  infra change makes this choice, not this ADR.
- Add a restore test and a backup note to the infra change.
- The MinIO class and the `MINIO_*` settings keep their names for now. A rename
  is a separate decision.
- The store is a single process on a single node. It has no replication.
- Revisit this decision if SeaweedFS fails a power-loss test or a CVE scan.
  Silo is the first fallback. Chainguard MinIO is the second fallback.

## Alternatives Considered

- **Silo (`pgsty/minio` fork)** - fallback 1. It passed the spike with 69 MiB
  idle RAM, and a `curl` health check returned 200. It runs as root with all
  capabilities dropped. The newest Docker Hub tag is from 2026-08-04, but
  GitHub shows a release from 2026-10-26, so the Hub image lags. One company
  controls the fork. The license is AGPL.
- **Chainguard MinIO (`cgr.dev/chainguard/minio`)** - fallback 2. It passed the
  spike with 60 MiB idle RAM and runs as UID 65532. Its version string
  `RELEASE.2026-10-23` differs from the last upstream release. Chainguard
  probably patches the archived source, but this is an inference and is not
  verified. The free tier shows only the `latest` tag. The maintainer did not
  verify the terms from an official page.
- **Garage 2.5.0** - rejected. It passed the spike with 7 MiB idle RAM. It runs
  as root with all capabilities dropped. It needs `s3_region = us-east-1`, or
  the SDK fails with `AuthorizationHeaderMalformed`. The Garage docs and a blog
  post (2026-04-18) say that a single node (replication factor 1) is not an
  intended use case. The default LMDB metadata database can corrupt after an
  unclean shutdown, and fsync is off by default. The license is AGPL.
- **RustFS** - rejected. It has several CVEs from 2026, one rated 9.8. Users
  report data loss with a single replica. Its maturity claims conflict.
- **Ceph RGW** - rejected. It needs about 4 GiB of RAM per OSD, so it does not
  fit the 4-6 GB budget.
- **Keep MinIO, built from source** - rejected. The project must build and
  maintain the image, and the upstream is archived, so no security fixes
  arrive.
