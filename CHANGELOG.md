# 📜 SmartMail AI — Changelog

All notable changes to **SmartMail AI** will be documented in this file.

---

## [1.1.0] - 2026-07-23

### Added
- **Bidirectional Inbound Gmail Sync (`inbound_sync.py`)**: Automatic background polling every 25s using Gmail's History API (`users.messages.history.list`) to track live label changes, unread updates, and new incoming emails.
- **Opened Email Action Toolbar**: Complete top control bar for open email view featuring **Back to Inbox**, **Mark Unread/Read**, **Star/Unstar**, **Archive**, **Delete/Trash**, **Reply**, and **✨ Summarize Email**.
- **Intent-Aware SQL RAG Retrieval (`email_repository.py`)**: Smart SQL intent routing for queries containing *"unread"*, *"recent"*, *"starred"*, or *"overview"*, joining directly with actual database records.
- **Multi-Sender Latest-to-Oldest Summarizer (`rag_service.py`)**: Extracted 1 representative chunk per distinct email across senders, ordering summaries and `REFERENCED EMAIL:` cards strictly from **Latest to Oldest**.
- **Date + Time Inbox Display (`app.js`)**: Updated email list rendering to display both Date and Time (`Jul 23, 04:32 PM`).
- **Auto Mark-as-Read & Live Unread Counter (`app.js`)**: Opening unread emails automatically updates local state, database records, and Gmail, instantly updating the sidebar unread counter badge (`#unreadBadge`).
- **Orphaned Sample Data Purging**: Automated background cleanup of pre-seeded demo sample chunks for authenticated Gmail users.

## [1.0.0] - 2026-07-23

### Added
- **Google OAuth2 Sign-In**: Sub-100ms non-blocking login response with automatic token refresh.
- **Background Gmail Inbox Sync**: Asynchronous synchronization across `INBOX`, `SENT`, `STARRED`, and `IMPORTANT` folders.
- **Multi-Format Attachment Parsing**: Text extraction pipeline for `.pdf`, `.pptx`, `.docx`, `.txt`, and images.
- **Original Binary Streaming**: Serve exact original binary files directly from disk (`./storage/attachments/`) or Gmail API using `FileResponse`.
- **Hybrid RAG Search**: Combination of BM25 lexical search and **4096-dimensional NVIDIA Nemotron dense vector embeddings** via Reciprocal Rank Fusion (RRF).
- **Full 22-Slide Document Analysis**: 12,000-character multi-slide document AI summarization engine (**Summarize Email** & **Summarize Thread**).
- **AI Action Executor**: Natural language tool-calling engine for executing inbox commands (*archive*, *star*, *mark read*, *delete*) via AI Chat.
- **Qdrant Vector DB Scaling**: Qdrant vector database integration (`qdrant_service.py`) with HNSW Cosine indexing and automatic SQLite fallback.
- **RAG Telemetry Dashboard**: Real-time evaluation stats endpoint (`/api/v1/eval/stats`).
- **Production Containerization**: Multi-stage `Dockerfile` and `docker-compose.yml`.
- **Modular Documentation Suite**: Separated project docs into `README.md`, `USER_GUIDE.md`, `DEVELOPER_GUIDE.md`, `ARCHITECTURE.md`, `LICENSE`, `CONTRIBUTING.md`, and `CHANGELOG.md`.
