# Observability

Structured, anonymized telemetry (ADR-0005).

- `logging.py` — structlog JSON configuration (PII stripped at the source)
- `metrics.py` — OpenTelemetry metrics
- `tracing.py` — OpenTelemetry distributed tracing (UI → Celery → agents → plugins)

Export path: OTel → Grafana Alloy → Grafana Cloud.
