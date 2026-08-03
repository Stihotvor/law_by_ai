---
status: proposed
---

# ADR-0012: MIT license and contribution model

## Context

The project charter already states **MIT** and **invite-only** contributions
([Intention](../intention.md) #58–59), a MIT `LICENSE` file and `pyproject.toml`
metadata exist, but the decision was never formally recorded and the
contribution model was never fully specified. Issue
[#5](https://github.com/Stihotvor/law_by_ai/issues/5) asks to decide between
MIT, Apache 2.0, and AGPL and to define how people contribute.

The platform is a **self-hosted, open-source community tool** for protecting
citizens' rights (EU/Poland) plus a personal research project. Its success
depends on **wide adoption and trust**, and it must stay runnable on the
4–6 GB + SLM efficiency budget with freely swappable open-source backends.

## Decision

1. **License: MIT** — keep the existing MIT License (`LICENSE`, SPDX `MIT` in
   `pyproject.toml`). MIT maximizes adoption, is simple for community
   contributors to understand, and does not constrain self-hosting or backend
   swapping.
2. **Contribution model**:
   - **Access**: invite-only during the early implementation phase
     (Phases 1–4). The project opens to public contributions once v1 is
     stable, at the maintainer's discretion.
- **DCO, not CLA**: every commit must carry a `Signed-off-by` trailer per the
  [Developer Certificate of Origin](https://github.com/Stihotvor/law_by_ai/blob/main/DCO).
  No separate CLA is required — DCO keeps friction low and works for
  individual contributors.
- **License grant**: by contributing, contributors agree their
  contributions are licensed under MIT (recorded in
  [CONTRIBUTING.md](https://github.com/Stihotvor/law_by_ai/blob/main/CONTRIBUTING.md)).
- **Process**: branches named `feature/`, `fix/`, or `docs/` referencing the
  issue; PRs must reference the issue (`Closes #N` / `Refs #N`) and pass the
  `ci` (ruff lint + format, pytest) and `docs` (mkdocs strict) workflows.
  Architecture-impacting changes require an ADR.
- **Maintainership**: single-maintainer review for now; significant
  decisions are recorded as ADRs.
- **Code of Conduct**: Contributor Covenant 2.1
  ([CODE_OF_CONDUCT.md](https://github.com/Stihotvor/law_by_ai/blob/main/CODE_OF_CONDUCT.md)).

## Consequences

- MIT maximizes adoption and contribution ease; anyone may fork, redistribute,
  or reuse the code, including commercially.
- Risk: a commercial party could offer a hosted version without contributing
  changes back. This is an acceptable trade-off for a self-hosted
  citizens'-rights tool where reach matters more than protection; it should be
  revisited if a hosted service is ever planned.
- DCO is lightweight and auditable via commit trailers; no per-contributor
  legal agreement overhead.
- The invite-only phase keeps early design churn inside the trusted core while
  the public onboarding path is documented for later.

## Alternatives Considered

- **Apache 2.0** — permissive with an explicit patent grant; friendlier to
  corporate contributors. Rejected for now: it adds a legal appendix and the
  project has no corporate contributor needs yet. Can be revisited later.
- **AGPL-3.0** — strongest copyleft; would prevent closed SaaS exploitation.
  Rejected: it raises adoption and contribution friction, can conflict with
  permissively-licensed dependencies and the personal-research goal, and MIT
  is already chosen in the charter.
- **CLA** — rejected in favor of DCO (less friction, no separate signing step,
  better fit for an invite-only community project).

## Related

- [Intention](../intention.md) #58, #59
- [CONTRIBUTING.md](https://github.com/Stihotvor/law_by_ai/blob/main/CONTRIBUTING.md)
- [CODE_OF_CONDUCT.md](https://github.com/Stihotvor/law_by_ai/blob/main/CODE_OF_CONDUCT.md)
- [DCO](https://github.com/Stihotvor/law_by_ai/blob/main/DCO)
- [LICENSE](https://github.com/Stihotvor/law_by_ai/blob/main/LICENSE)
- Issue [#5](https://github.com/Stihotvor/law_by_ai/issues/5)
