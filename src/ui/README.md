# UI

Streamlit application — the primary user interface (fetch, browse, search,
analysis, knowledge graph, changes, bureaucracy assistant). No public API;
clients interact with the app directly.

- `app.py` — Streamlit entry point
- `pages/` — one page per feature
- `components/` — reusable custom components

All pages are behind the login (streamlit-authenticator cookie); RBAC limits data management to `admin`
(ADR-0013).
