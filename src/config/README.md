# Config

Runtime configuration.

- `settings.py` — environment-based application configuration
- `plugins.py` — **DEPRECATED** plugin registration facade (ADR-0014); no
  `relational_db` entry is routed here anymore
- `plugins.yaml` — **DEPRECATED** protocol → implementation registry; no active
  entries (ADR-0014)
- `.env.example` — documented environment variables (copy to `.env`)
