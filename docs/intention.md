---
status: completed
---

# Project Intention

> **Status:** Completed — all clarification questions answered.
> This document now serves as the project charter.
> Rev. 2 — incorporates the revised architecture plan (ADRs 1–11).

---

## 👁️ Vision & Purpose

**1.** *Elevator pitch* – A self-hosted AI lawyer that helps protect citizens' rights and assists with local bureaucracy.

**2.** *Pain point* – Civil-human-rights, family and private law, and daily routine tasks that require legal assistance.

**3.** *Primary target user* – EU (Poland) citizens and expats.

**4.** *Project type* – Open-source community tool **plus** a personal research project.

**5.** *North-star metric* – **Time and money saved per user** while tracking legal changes and protecting rights.

**6.** *Scope boundary* – The system will **not bypass or trick the law**.

**7.** *Efficiency mandate* – The application must run **fast on ~4–6 GB RAM with a small local model (SLM)**. Efficiency is a hard requirement, not a nice-to-have. Every architectural choice (plugin type, model size, task queue) is made with this budget in mind.

---

## ⚖️ Legal Domain Scope

**8.** *Jurisdictions* – Poland (EU).

**9.** *Areas of law* – Family, child care, taxes, anti-xenophobic law.

**10.** *Source material* – **All** legal material (legislation, case law, commentaries, contracts, procedural documents, etc.).

**11.** *Legal-updates handling* – **Manual fetching** at the beginning.

**12.** *Supported formats* – **All** (PDF, DOCX, HTML, scanned images → OCR, plain text).

**13.** *Cross-reference tracking* – **Yes** – a graph database is required.

**14.** *OCR model* – Selected by **evaluation on Polish documents** (e.g., Tesseract, EasyOCR, PaddleOCR candidates). The chosen model must fit the 4–6 GB RAM budget.

**15.** *Citations* – **MUST be in the MVP** — every search/analysis result must include exact law article citations with confidence scores and direct source links.

---

## 📐 Architecture & Technology

**16.** *Deployment model* – **Docker-Compose** (self-hosted).

**17.** *Vector database* – **In-memory Chroma** for the MVP, later **Qdrant**.

**18.** *Graph database* – **Memgraph** for the MVP, **Neo4j** for production. (ADR-0002)

**19.** *LLM provider* – **Multi-provider** via your liteLLM proxy, targeting **open-source lite models** (e.g., Gemma 4, Mistral Nano, Ministral) to satisfy the RAM/SLM budget.

**20.** *Embedding model* – **Mistral embed** or **Gemini-mini embed 2** (local) candidates; **final model selected by evaluation on Polish legal texts**. (ADR-0009)

**21.** *Multi-tenant isolation* – **Yes**, from day 1. Documents are **shared storage**; per-tenant data (notes, states, chats, annotations) is isolated. (ADR-0003)

**22.** *Expected data volume* – **All Polish law**, including tax and foreign statutes (tens of thousands of documents).

**23.** *Processing model* – **Celery + Redis** (asynchronous batch processing) with **efficient tasks**, retry policies, and in-DB task monitoring so users can re-run failed tasks. (ADR-0006)

**24.** *Plugin approach* – **Protocol-based** (not ABC), registered via a **YAML config** and loaded by `PluginManager`. (ADR-0001)

**25.** *Observability* – **MUST in the MVP**: `structlog` (JSON logs) + metrics + traces via **OpenTelemetry**, shipped through **Grafana Alloy → Grafana Cloud**. **All telemetry must be anonymized** (no PII). (ADR-0005)

**26.** *Health checks* – Every container exposes a **health check** endpoint for monitoring and orchestration. (ADR-0010)

**27.** *Security* – **JWT auth (MUST)** + **RBAC**: an **admin** manages data, a **user** can only read it. Multi-tenant isolation is enforced and tested with **leak tests**. (ADR-0004)

**28.** *SLAs* – Basic **SLA standards** are defined and tracked (search latency, processing time, availability). (ADR-0011)

---

## 🔍 Search & Retrieval

**29.** *Search modes* – Keyword, semantic, and hybrid (all three).

**30.** *Cross-language search* – Supported (e.g., English queries against Polish legal texts).

**31.** *Retrieval strategy* – Hybrid RAG with re-ranking, graph-guided multi-hop retrieval.

**32.** *Citation & confidence* – **MUST in the MVP** — confidence scores and exact law article citations with direct source links.

**33.** *Faceted filters* – **MUST in the MVP** — by jurisdiction, **document type**, **dates**, court, etc.

**34.** *Find similar documents* – Feature will be available.

**35.** *Hybrid search precision* – Validated with an **evaluation on Polish legal queries**; precision/recall targets are defined and measured. (ADR-0005 / ADR-0009)

---

## 🤖 Agents & Automation

**36.** *Priority agents* – DocumentFetcher (code + OCR), DocumentProcessor (graph manager), LegalResearch, KnowledgeGraph, plus others later.

**37.** *Execution style* – **Human-in-the-loop** (user triggers/approves steps).

**38.** *Change-tracker granularity* – **Document-level diffs**, most likely backed by **Git** for versioning and comparison. (ADR-0007)

**39.** *Analysis output* – **Free-text** for now.

**40.** *Workflow customization* – **Pre-configured** pipelines (MVP).

**41.** *Bureaucracy/Form Assistant* – **MUST be in the MVP** — a dedicated agent that guides users through administrative procedures step by step.

**42.** *Celery task reliability* – Tasks are efficient, failures are persisted in-DB, and the UI lets users **re-run failed tasks**. (ADR-0006)

---

## 🖥️ User Interface

**43.** *Primary UI* – **Streamlit** (as used in existing issues).

**44.** *Public API* – No built-in API server; **API clients** will fetch data from the UI/backend directly.

**45.** *Visualizations* – Knowledge-graph, citation network, and timeline visualizations (planned, not in MVP).

**46.** *Annotation & comments* – Not needed now; may be added in future versions.

**47.** *Collaboration* – Not required at present.

---

## 🔐 Security

**48.** *Authentication* – **JWT-based auth (MUST)** for all users.

**49.** *Authorization* – **RBAC (MUST)**: `admin` role can manage data (ingest, edit, delete); `user` role is **read-only**.

**50.** *Multi-tenant isolation* – Enforced at every layer:
- PostgreSQL — row-level isolation with `tenant_id` (shared document store, per-tenant notes/states/chats).
- Chroma/Qdrant — collection or partition per tenant.
- Memgraph/Neo4j — subgraph per tenant.

**51.** *Tenant leak tests* – Automated tests assert that no tenant can access another tenant's data. (ADR-0003)

---

## 📈 SLA Standards (basic)

**52.** *Search latency* – Hybrid search responds within **target latency** (e.g., < 3 s for MVP on the 4–6 GB budget); measured and reported via OTel.

**53.** *Document processing* – Ingest → chunk → embed → graph completes within a defined **processing budget**; tracked per task.

**54.** *Availability* – Docker-Compose with health checks; service health is visible via the OTel/Grafana stack.

Detailed targets live in ADR-0011.

---

## 🚀 Delivery & Timeline

**55.** *Minimum Viable Product* – Data collection, processing, annotation, push to PostgreSQL, vector store, graph store, **citations with confidence**, **filters**, **document diffs**, **bureaucracy assistant**, and answering complex questions / internal data research — all on the **4–6 GB RAM + SLM** budget.

**56.** *Target timeline* – **MVP**: end of **next month**. **v1**: end of **this year**.

**57.** *Long-term vision* – A **legal-AI platform** for personal and family use, with the possibility of a free online service or bot for answering questions and a legal-tracker component.

---

## 🛠️ Meta

**58.** *License* – **MIT**.

**59.** *Contributions* – **Invite-only** (initially).

**60.** *Documentation language* – **English** now; later **Ukrainian** and **Polish**.

**61.** *ADR tracking* – All significant architecture decisions are tracked as **ADRs** in [Architecture & ADRs](architecture.md#adr-register).

---

*The charter above defines the scope, technology stack, and roadmap for "Law by AI". All subsequent design, implementation, and testing decisions should be aligned with these constraints and goals.*
