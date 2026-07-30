---
status: completed
---

# Project Intention

> **Status:** Completed — all clarification questions answered.
> This document now serves as the project charter.

---

## 👁️ Vision & Purpose

**1.** *Elevator pitch* – A self-hosted AI lawyer that helps protect citizens' rights and assists with local bureaucracy.

**2.** *Pain point* – Civil-human-rights, family and private law, and daily routine tasks that require legal assistance.

**3.** *Primary target user* – EU (Poland) citizens and expats.

**4.** *Project type* – Open-source community tool **plus** a personal research project.

**5.** *North-star metric* – **Time and money saved per user** while tracking legal changes and protecting rights.

**6.** *Scope boundary* – The system will **not bypass or trick the law**.

---

## ⚖️ Legal Domain Scope

**7.** *Jurisdictions* – Poland (EU).

**8.** *Areas of law* – Family, child care, taxes, anti-xenophobic law.

**9.** *Source material* – **All** legal material (legislation, case law, commentaries, contracts, procedural documents, etc.).

**10.** *Legal-updates handling* – **Manual fetching** at the beginning.

**11.** *Supported formats* – **All** (PDF, DOCX, HTML, scanned images → OCR, plain text).

**12.** *Cross-reference tracking* – **Yes** – a graph database is required.

---

## 📐 Architecture & Technology

**13.** *Deployment model* – **Docker-Compose** (self-hosted).

**14.** *Vector database* – **In-memory Chroma** for the MVP, later **Qdrant**.

**15.** *Graph database* – **NetworkX** initially, later **Neo4j** and **Memgraph**.

**16.** *LLM provider* – **Multi-provider** via your liteLLM proxy.

**17.** *Embedding model* – **Mistral embed** or **Gemini-mini embed 2** (local).

**18.** *Multi-tenant isolation* – **Yes**, from day 1.

**19.** *Expected data volume* – **All Polish law**, including tax and foreign statutes (tens of thousands of documents).

**20.** *Processing model* – **Celery + Redis** (asynchronous batch processing).

---

## 🔍 Search & Retrieval

**21.** *Search modes* – Keyword, semantic, and hybrid (all three).

**22.** *Cross-language search* – Supported (e.g., English queries against Polish legal texts).

**23.** *Retrieval strategy* – Hybrid RAG with re-ranking, graph-guided multi-hop retrieval.

**24.** *Citation & confidence* – Search results will include **confidence scores** and **exact law article citations** with direct source links.

**25.** *Faceted filters* – Yes (by jurisdiction, document type, date, court, etc.).

**26.** *Find similar documents* – Feature will be available.

---

## 🤖 Agents & Automation

**27.** *Priority agents* – DocumentFetcher (code + OCR), DocumentProcessor (graph manager), LegalResearch, KnowledgeGraph, plus others later.

**28.** *Execution style* – **Human-in-the-loop** (user triggers/approves steps).

**29.** *Change-tracker granularity* – **Document-level**.

**30.** *Analysis output* – **Free-text** for now.

**31.** *Workflow customization* – **Pre-configured** pipelines (MVP).

**32.** *Bureaucracy/Form Assistant* – **Yes**, a dedicated agent to guide users through administrative procedures.

---

## 🖥️ User Interface

**33.** *Primary UI* – **Streamlit** (as used in existing issues).

**34.** *Public API* – No built-in API server; **API clients** will fetch data from the UI/backend.

**35.** *Visualizations* – Knowledge-graph, citation network, and timeline visualizations (planned, not in MVP).

**36.** *Annotation & comments* – Not needed now; may be added in future versions.

**37.** *Collaboration* – Not required at present.

---

## 🚀 Delivery & Timeline

**38.** *Minimum Viable Product* – Data collection, processing, annotation, push to PostgreSQL, vector store, graph store, and answering complex questions / internal data research.

**39.** *Target timeline* – **MVP**: end of **next month**. **v1**: end of **this year**.

**40.** *Long-term vision* – A **legal-AI platform** for personal and family use, with the possibility of a free online service or bot for answering questions and a legal-tracker component.

---

## 🛠️ Meta

**41.** *License* – **MIT**.

**42.** *Contributions* – **Invite-only** (initially).

**43.** *Documentation language* – **English** now; later **Ukrainian** and **Polish**.

---

*The charter above defines the scope, technology stack, and roadmap for "Law by AI". All subsequent design, implementation, and testing decisions should be aligned with these constraints and goals.*
