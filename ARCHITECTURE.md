# 🏗️ SmartMail AI — Architecture Deep Dive

This document details the architectural design, data models, hybrid RAG pipeline, and system sequence interactions of **SmartMail AI**.

---

## 📐 1. System Class Diagram

Below is the complete UML Class Diagram illustrating SmartMail AI's entity models, repositories, AI services, and vector database interactions:

```mermaid
classDiagram
    class User {
        +String id
        +String email
        +String full_name
        +DateTime created_at
    }

    class GmailAccount {
        +String id
        +String user_id
        +String email_address
        +String encrypted_access_token
        +String encrypted_refresh_token
        +DateTime token_expiry
        +String history_id
    }

    class Thread {
        +String id
        +String user_id
        +String subject
        +String snippet
        +DateTime last_message_at
        +Integer unread_count
    }

    class Email {
        +String id
        +String thread_id
        +String user_id
        +String sender_name
        +String sender_email
        +String recipient_list
        +String subject
        +String body_text
        +String body_html
        +DateTime received_at
        +Boolean is_unread
        +Boolean is_starred
        +Boolean is_important
        +List~String~ labels
    }

    class Attachment {
        +String id
        +String email_id
        +String filename
        +String mime_type
        +Integer file_size
        +String storage_path
        +String extracted_text
    }

    class EmailChunk {
        +String id
        +String email_id
        +String thread_id
        +String user_id
        +Integer chunk_index
        +String content
        +List~Float~ embedding
    }

    class SyncService {
        +sync_user_inbox(user_id, max_results)
        +_fetch_real_gmail_messages(user, headers)
        +_parse_gmail_message(msg_data, user_id)
    }

    class RAGService {
        +answer_question(user_id, query)
        +answer_question_stream(user_id, query)
        +get_sources_for_query(user_id, query)
        +summarize_thread(user_id, thread_id)
    }

    class ActionExecutor {
        +execute_intent(user_id, prompt)
        +_action_archive(user_id, prompt)
        +_action_star(user_id, prompt)
        +_action_mark_read(user_id, prompt)
        +_action_delete(user_id, prompt)
    }

    class QdrantVectorService {
        +is_available()
        +ensure_collection()
        +upsert_chunks(points)
        +search_vectors(query_vector, user_id)
    }

    class NvidiaNIMClient {
        +generate_text(prompt, system_prompt)
        +generate_stream(prompt, system_prompt)
        +get_embedding(text)
    }

    User "1" -- "1" GmailAccount : owns
    User "1" -- "n" Thread : owns
    User "1" -- "n" Email : owns
    Thread "1" -- "n" Email : contains
    Email "1" -- "n" Attachment : has
    Email "1" -- "n" EmailChunk : chunked_into
    SyncService ..> Email : indexes
    SyncService ..> Attachment : parses
    RAGService ..> EmailChunk : retrieves
    RAGService ..> NvidiaNIMClient : invokes
    RAGService ..> QdrantVectorService : queries
    ActionExecutor ..> Email : mutates
```

---

## 🧠 2. Hybrid RAG Search & Vector Retrieval Pipeline

SmartMail AI implements **Reciprocal Rank Fusion (RRF)** to combine exact keyword matching with deep semantic similarity:

```
                  ┌──────────────────────────────┐
                  │      User Search Query       │
                  └──────────────┬───────────────┘
                                 │
                 ┌───────────────┴───────────────┐
                 │                               │
                 ▼                               ▼
       ┌──────────────────┐            ┌──────────────────┐
       │   BM25 Lexical   │            │ NVIDIA Nemotron  │
       │  Keyword Search  │            │ 4096-dim Vector  │
       └─────────┬────────┘            └─────────┬────────┘
                 │                               │
                 │ Rank Lists                    │ Rank Lists
                 ▼                               ▼
      ┌─────────────────────────────────────────────────────┐
      │          Reciprocal Rank Fusion (RRF)               │
      │        Score = 1/(60 + Rank_BM25) + 1/(60 + Rank_Vec)│
      └──────────────────────────┬──────────────────────────┘
                                 │
                                 ▼
                      ┌─────────────────────┐
                      │ Cross-Encoder       │
                      │ Reranking & Context │
                      └──────────┬──────────┘
                                 │
                                 ▼
                      ┌─────────────────────┐
                      │ NVIDIA NIM LLM      │
                      │ (Llama 3.3 70B)     │
                      └─────────────────────┘
```

---

## ⚡ 3. Concurrency & Database Protections

1. **SQLite WAL Mode (`PRAGMA journal_mode=WAL`)**: Configured to permit concurrent read operations while background async indexing processes write to disk.
2. **`NullPool` Async Engine (`database.py`)**: Eliminates connection pool overflow errors (`sqlalchemy.exc.TimeoutError: QueuePool limit size 5 overflow 10 reached`) during asynchronous batch workloads.
3. **Qdrant Vector Database HNSW Indexing (`qdrant_service.py`)**: Stores 4096-dimensional vectors with Cosine distance indexing and payload filtering by `user_id`. Automatically degrades gracefully to SQLite vector search if the Qdrant container is unreachable.
