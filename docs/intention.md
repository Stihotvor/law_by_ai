---
status: draft
---

# Project Intention

> **Status:** Draft — questions open for discussion.
> Once all answers are collected, this document becomes the project charter.

> **Note to reviewers:** Please answer the 43 questions below. Every answer
> shapes the architecture and scope. If a question doesn't apply, explain why.
> If something is missing, add it.

---

## 👁️ Vision & Purpose

**1.** What is the single-sentence elevator pitch for "Law by AI"?

**2.** What specific pain point in the legal domain does this project solve?

**3.** Who is the **primary target user** — lawyers, paralegals, legal firms,
    pro-se litigants, researchers, or the general public?

**4.** Is this a **commercial product**, an **open-source community tool**, or a
    **personal portfolio / research project**?

**5.** What is the **north star metric** — what one thing tells us we've
    succeeded (e.g., "hours saved per case", "documents indexed")?

**6.** What is the **scope boundary** — what will this project explicitly
    **not** do?

---

## ⚖️ Legal Domain Scope

**7.** Which **jurisdictions** will be supported initially (e.g., Ukraine, EU,
    US federal, UK)?

**8.** Which **areas of law** are in scope (e.g., contract law, criminal code,
    tax law, constitutional law)?

**9.** Will the system work with **legislation only**, or also with **case law,
    commentaries, contracts, and procedural documents**?

**10.** How will **legal updates** be handled — automatic re-fetching of changed
     laws, manual triggers, or periodic?

**11.** What **document formats** must be supported (PDF, DOCX, HTML, scanned
     images via OCR, plain text)?

**12.** Does the system need to track **cross-references and amendments** between
     legal documents?

---

## 📐 Architecture & Technology

**13.** What is the **deployment model** — self-hosted Docker, cloud SaaS,
     desktop app, or all of the above?

**14.** Which **vector database** should we use — Qdrant (as listed in issues),
     Pinecone, Weaviate, or pgvector?

**15.** Should the **graph database** be kept — is tracking citation /
     cross-reference graphs a core feature or a nice-to-have?

**16.** What **LLM provider** will be used — OpenAI, Azure OpenAI, local models
     (Llama / Mistral via Ollama), or a mix?

**17.** What **embedding model** is preferred — `text-embedding-3-small`,
     `multilingual-e5`, or sentence-transformers for local inference?

**18.** Should the system support **multi-tenant isolation** (different law firms
     with separate data) from day one?

**19.** What is the **expected data volume** — thousands, millions, or billions
     of documents?

**20.** Do we need **real-time** document processing, or is batch / async
     (Celery) sufficient?

---

## 🔍 Search & Retrieval

**21.** What **search modes** are required — keyword (full-text), semantic
     (vector), hybrid, or all three?

**22.** Should we support **cross-language search** (e.g., query in English,
     find Ukrainian legal documents)?

**23.** What **retrieval strategy** — simple top-K, RAG with re-ranking, or
     multi-hop retrieval over a graph?

**24.** Should search results include **confidence scores** and **citation
     references** back to source documents?

**25.** Are **faceted filters** needed (by jurisdiction, document type, date,
     court, etc.)?

**26.** Should the system offer **"Find similar documents"** for any given legal
     text?

---

## 🤖 Agents & Automation

**27.** What **types of agents** are prioritized — DocumentFetcher,
     DocumentProcessor, LegalResearch, ChangeTracker, KnowledgeGraph, Analysis?

**28.** Should agents operate **autonomously** (scheduled, unsupervised) or
     **human-in-the-loop** (review before action)?

**29.** Do we need a **change-tracking agent** that monitors legal databases for
     new / amended laws and alerts users?

**30.** Should the **analysis agent** produce structured outputs (e.g., "this
     clause contradicts Article 14.3") or free-text summaries?

**31.** What is the **granularity of change tracking** — document-level,
     section-level, or line-by-line diff?

**32.** Can users **create custom agents / workflows** via a DSL or UI, or are
     agents pre-defined?

---

## 🖥️ User Interface

**33.** What is the **primary UI** — Streamlit (as in issues), a React SPA, or a
     CLI / API-first approach?

**34.** Should there be a **public API** (REST / GraphQL) for third-party
     integrations?

**35.** What **visualizations** are needed — knowledge graphs, citation
     networks, timeline of legal changes?

**36.** Should users be able to **annotate and comment** on documents within the
     system?

**37.** Is **collaboration** required — shared workspaces, comments, document
     sharing between users?

---

## 🚀 Delivery & Timeline

**38.** What is the **minimum viable product (MVP)** — the smallest thing we can
     ship that provides value?

**39.** What is the **target timeline** for MVP, beta, and v1.0?

**40.** What is the **long-term vision** — a comprehensive legal AI platform, or
     a focused tool for one specific task?

---

## 🛠️ Meta

**41.** What **license** should the project use (MIT, Apache 2.0, AGPL, or
     proprietary)?

**42.** How will **contributions** be managed — open for all, invite-only, or
     solo?

**43.** Should documentation be in **English only**, or **multi-language**
     (English + Ukrainian / other languages for local users)?
