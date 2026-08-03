# Config

Runtime configuration and plugin registration (ADR-0001).

- `settings.py` — environment-based application configuration
- `plugins.yaml` — protocol → implementation registration, loaded by `PluginManager`
- `.env.example` — documented environment variables (copy to `.env`)
