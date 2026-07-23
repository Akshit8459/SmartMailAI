# 🏛️ SmartMail AI — Architecture Decision Records (ADRs)

This document records the architectural decisions, design rationale, trade-offs, and consequences made during the development of **SmartMail AI**.

---

## 📋 Table of Contents
- [ADR-001: Backend Framework Choice — FastAPI vs. Django/Flask](#adr-001-backend-framework-choice--fastapi-vs-djangoflask)
- [ADR-002: Storage Decoupling — Relational SQLite (WAL) + Qdrant Vector DB](#adr-002-storage-decoupling--relational-sqlite-wal--qdrant-vector-db)
- [ADR-003: Hybrid Retrieval — BM25 + Dense Vectors via Reciprocal Rank Fusion (RRF)](#adr-003-hybrid-retrieval--bm25--dense-vectors-via-reciprocal-rank-fusion-rrf)
- [ADR-004: Architecture Pattern — Repository Pattern & Clean Layering](#adr-004-architecture-pattern--repository-pattern--clean-layering)
- [ADR-005: Synchronization Model — Asynchronous Non-Blocking Sync (< 100ms SLA)](#adr-005-synchronization-model--asynchronous-non-blocking-sync--100ms-sla)
- [ADR-006: Attachment Strategy — Full Text Extraction & Raw Binary Streaming](#adr-006-attachment-strategy--full-text-extraction--raw-binary-streaming)

---

## ADR-001: Backend Framework Choice — FastAPI vs. Django/Flask

### **Context**
SmartMail AI requires high-throughput asynchronous execution to handle real-time OAuth token refreshing, background Gmail inbox synchronization, vector embedding generation, and Server-Sent Events (SSE) streaming for AI responses.

### **Alternatives Considered**
- **Django**: Full-featured framework, but heavy synchronous legacy ORM layer and overhead for real-time SSE streaming.
- **Flask**: Lightweight, but lacks native ASGI async/await execution out of the box and requires external libraries for Pydantic validation.

### **Chosen Solution**
Selected **FastAPI 0.115+** running on Uvicorn ASGI server.

### **Advantages**
- Native Python `async/await` execution for non-blocking I/O.
- Automatic Pydantic schema validation and OpenAPI specification generation.
- High-performance SSE streaming support.

### **Disadvantages**
- Requires explicit repository layering and custom configuration compared to Django's batteries-included ORM.

### **Consequences**
- All database queries and external HTTP API requests must use async libraries (`aiosqlite`, `httpx`).

---

## ADR-002: Storage Decoupling — Relational SQLite (WAL) + Qdrant Vector DB

### **Context**
Email messages contain structured relational metadata (senders, timestamps, folder labels, read status) alongside high-dimensional vector embeddings generated from body text and attachment chunks.

### **Alternatives Considered**
- **Monolithic Relational Database Only**: Storing vectors inside SQLite/PostgreSQL `pgvector`. Poor scalability for 4096-dim vectors.
- **Pure Vector DB Only**: Storing all transactional state in Qdrant. Poor performance for SQL filtering and relational joins.

### **Chosen Solution**
Decoupled relational storage from vector storage:
- **Relational Metadata**: Stored in **SQLite (WAL Mode)** using SQLAlchemy 2.0 Async with `NullPool` connection handling.
- **Vector Embeddings**: Stored in **Qdrant Vector Database** hosting 4096-dimensional NVIDIA Nemotron embeddings with HNSW Cosine indexing.

### **Advantages**
- Fast vector similarity search inside Qdrant's specialized HNSW graph indexes.
- Relational queries remain fast in SQLite without vector bloating.

### **Disadvantages**
- Requires dual-write management during inbox synchronization.
- Additional infrastructure container to manage in production.

### **Consequences**
- System must implement graceful fallback to SQLite vector search if the Qdrant container is unreachable.

---

## ADR-003: Hybrid Retrieval — BM25 + Dense Vectors via Reciprocal Rank Fusion (RRF)

### **Context**
Pure vector search often suffers from false negatives on exact keyword terms (order IDs, chemical codes, names). Pure keyword search fails on semantic natural language queries.

### **Alternatives Considered**
- **Dense Vector Search Alone**: Misses specific alphanumeric codes and exact names.
- **BM25 Keyword Search Alone**: Fails to capture natural language intent and semantic synonyms.

### **Chosen Solution**
Implemented **Hybrid Search with Reciprocal Rank Fusion (RRF)**:
$$RRF(d) = \sum_{m \in M} \frac{1}{k + r_m(d)}$$
where $k=60$, combining BM25 keyword matching with 4096-dim NVIDIA Nemotron vector cosine search.

### **Advantages**
- Dramatically higher retrieval recall on both exact strings and natural language questions.

### **Disadvantages**
- Slightly higher search latency (~15ms per query).

### **Consequences**
- Search pipeline must run BM25 and vector queries in parallel to minimize latency.

---

## ADR-004: Architecture Pattern — Repository Pattern & Clean Layering

### **Context**
To avoid tight coupling between database logic, external Gmail API clients, LLM providers, and FastAPI route handlers.

### **Alternatives Considered**
- **Inline Database Queries in Route Handlers**: Rapid prototyping, but difficult to test and maintain.

### **Chosen Solution**
Adopted the **Repository Pattern** and **Service Layer Architecture**:
- `EmailRepository`: Abstracted database CRUD operations.
- `SyncService` & `RAGService`: Domain logic encapsulation.
- `NvidiaNIMClient`: Pluggable LLM provider factory.

### **Advantages**
- Highly testable codebase with clear separation of concerns.
- Switching LLM providers or database engines requires zero changes to route handlers.

### **Disadvantages**
- Requires maintaining explicit DTO interface mapping (`dtos.py`).

### **Consequences**
- Domain logic must never import database drivers directly; all access flows through repositories.

---

## ADR-005: Synchronization Model — Asynchronous Non-Blocking Sync (< 100ms SLA)

### **Context**
Fetching hundreds of Gmail messages and multi-page attachments over network requests takes several seconds. Blocking user login on complete synchronization creates an unacceptable user experience.

### **Alternatives Considered**
- **Synchronous Blocking Login**: User waits 10–30 seconds for full sync before entering inbox.

### **Chosen Solution**
Implemented **Asynchronous Background Synchronization**:
- Google OAuth callback stores encrypted tokens and returns HTTP `200 OK` in **< 100ms**.
- Gmail synchronization is offloaded to FastAPI `BackgroundTasks`.

### **Advantages**
- Instant user authentication and page load.

### **Disadvantages**
- Frontend must handle progressive inbox rendering.

### **Consequences**
- Frontend includes an auto-polling loading spinner (`⚡ Syncing your Gmail inbox...`) updating every 3 seconds.

---

## ADR-006: Attachment Strategy — Full Text Extraction & Raw Binary Streaming

### **Context**
Attached documents contain critical information for AI RAG, but users expect to download the original binary file when clicking "Open".

### **Alternatives Considered**
- **Text-Only Storage**: Storing only extracted text text fallback chunks. Users cannot download original PDF/PPTX files.

### **Chosen Solution**
- **Text Extraction**: Parsed up to 12,000 characters per document across all slides/pages for vector indexing and structured AI summarization.
- **Binary File Streaming**: Decoded raw binary bytes are written to `./storage/attachments/{att_id}_{filename}` and streamed via `FileResponse`.

### **Advantages**
- Full-document AI coverage while guaranteeing native original binary file downloads.

### **Disadvantages**
- Requires local disk storage allocation for binary files.

### **Consequences**
- Sync worker must decode base64 attachment data and write binary bytes to storage directory.

---

## ADR-007: Inbound Synchronization — Gmail History API vs. Full Resync

### **Context**
Users expect actions taken directly inside Gmail (e.g. marking emails read on mobile, archiving, receiving new messages) to reflect in SmartMail without manually refreshing. Full resyncing on every poll is expensive and hits Gmail API quota limits.

### **Chosen Solution**
Implemented incremental inbound sync (`inbound_sync.py`) using Gmail's **History API** (`users.messages.history.list?startHistoryId=...`).
- Background worker polls every 25 seconds for history events (`labelsAdded`, `labelsRemoved`, `messagesAdded`).
- Directly updates local SQLite database state and indexes new message chunks instantly.

### **Advantages**
- Extremely fast incremental updates with low network payload.
- Zero quota strain on Gmail API.

---

## ADR-008: Intent-Aware SQL Retrieval & Deduplicated RAG Summarization

### **Context**
Pure BM25/Vector search for intent queries like *"Summarize unread emails"* penalized actual unread emails whose body text lacked the literal word `"unread"`, resulting in biased summaries.

### **Chosen Solution**
- **SQL Intent Routing**: Detects query intent (`"unread"`, `"recent"`, `"starred"`) in `email_repository.py` and queries relational `Email` tables directly.
- **Sender Deduplication & Sorting**: `_deduplicate_chunks_by_email()` selects 1 representative chunk per email across senders and orders context strictly **Latest to Oldest** (`Email.received_at.desc()`).
- **Synchronized Citations**: `get_sources_for_query()` uses identical intent routing, guaranteeing `REFERENCED EMAIL:` cards match the AI text summary.

### **Advantages**
- 100% accurate inbox summaries covering all distinct senders in exact chronological order.
