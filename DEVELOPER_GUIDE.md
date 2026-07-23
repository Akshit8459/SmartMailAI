# 💻 SmartMail AI — Developer Guide

This guide provides technical instructions for setting up, contributing to, and deploying **SmartMail AI**.

---

## 🛠️ 1. Local Development Setup

### **Prerequisites**
- Python 3.12+
- Node.js (optional, for utility tools)
- Docker & Docker Compose (for Qdrant vector database)

### **Environment Setup**
```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r backend/requirements.txt
```

### **Environment Variables (`.env`)**
Create a `.env` file in the root directory:
```env
HOST=0.0.0.0
PORT=8000
SECRET_KEY=smartmail-super-secret-key-change-in-production-aes256
DATABASE_URL=sqlite+aiosqlite:///./smartmail.db

# Pluggable LLM Settings (nvidia, openai, ollama)
LLM_PROVIDER=nvidia
NVIDIA_API_KEY=nvapi-your-key-here
NVIDIA_MODEL=meta/llama-3.3-70b-instruct
NVIDIA_EMBED_MODEL=nvidia/nemotron-3-embed-1b

# Qdrant Vector Database
QDRANT_HOST=localhost
QDRANT_PORT=6333
QDRANT_COLLECTION=smartmail_email_chunks

# Google OAuth Settings
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/auth/callback
```

### **Run Development Server**
```bash
python backend/main.py
```

---

## 📂 2. Repository & Project Structure

```
SmartMail/
├── backend/
│   ├── main.py                        # FastAPI entry point, lifespan, CORS, static file mounting
│   ├── app/
│   │   ├── api/                       # REST API route handlers
│   │   │   ├── router.py              # Main router aggregator
│   │   │   ├── auth_routes.py         # Google OAuth & session status endpoints
│   │   │   ├── email_routes.py        # Email lists, folder filters, and binary attachment streaming
│   │   │   ├── ai_routes.py           # RAG Q&A streaming, document Q&A, and thread summaries
│   │   │   ├── sync_routes.py         # Manual & auto inbox sync endpoints
│   │   │   ├── eval_routes.py         # Telemetry and developer evaluation dashboard
│   │   │   └── webhook_routes.py      # Google Cloud Pub/Sub real-time push webhooks
│   │   ├── core/                      # Application core (config, database, security)
│   │   │   ├── config.py              # Environment variable loader settings
│   │   │   ├── database.py            # Async SQLAlchemy engine (NullPool & WAL mode)
│   │   │   └── security.py            # JWT token management & AES-256 Fernet token encryption
│   │   ├── domain/
│   │   │   └── dtos.py                # Pydantic request/response schemas
│   │   ├── models/
│   │   │   └── entities.py            # SQLAlchemy database models (User, Email, Attachment, Chunk)
│   │   ├── repositories/
│   │   │   └── email_repository.py    # Database repository for email CRUD and bulk actions
│   │   └── services/
│   │       ├── gmail/
│   │       │   └── gmail_service.py   # Gmail API v1 client & OAuth token refresher
│   │       ├── indexing/
│   │       │   ├── sync_service.py    # Inbox sync engine, message parser, & binary disk writer
│   │       │   └── semantic_chunker.py # Overlapping text chunker for emails and multi-page files
│   │       └── ai/
│   │           ├── prompt_builder.py  # System prompts & executive summary templates
│   │           ├── rag_service.py     # Hybrid RAG engine (BM25 + Cosine RRF + Reranking)
│   │           ├── action_executor.py # AI natural language tool-calling execution engine
│   │           ├── qdrant_service.py  # Qdrant vector database client & collection manager
│   │           └── llm/               # Pluggable LLM provider implementations (NVIDIA, OpenAI, Ollama)
```

---

## ⚡ 3. Key Backend Services

- **`SyncService` (`sync_service.py`)**: Fetches raw Gmail messages, parses MIME body structures, extracts text from attachments (`.pdf`, `.pptx`, `.docx`, images), writes raw binary files to `./storage/attachments/`, and generates text chunks for vector indexing.
- **`RAGService` (`rag_service.py`)**: Executes hybrid search using **BM25 keyword matching** and **4096-dim NVIDIA Nemotron vector embeddings** via Reciprocal Rank Fusion (RRF).
- **`ActionExecutor` (`action_executor.py`)**: Translates natural language chat prompts into structured database mutations (*archive*, *star*, *mark read*, *delete*).
- **`QdrantVectorService` (`qdrant_service.py`)**: Interfaces with the Qdrant vector database container for 4096-dim vector storage with payload filtering and HNSW Cosine indexing.

---

## 🧪 4. Testing & Verification

Run endpoint verification scripts:
```bash
# Test RAG evaluation stats
python -c "import httpx; r = httpx.get('http://localhost:8000/api/v1/eval/stats'); print(r.json())"

# Test AI Action Execution
python -c "import httpx; r = httpx.post('http://localhost:8000/api/v1/ai/execute-action', json={'prompt': 'archive all receipts'}); print(r.json())"
```

---

## 🔮 5. Future Development Roadmap

### **Short-Term Roadmap**
1. 🔄 **Bidirectional Gmail Synchronization**: Sync actions taken in SmartMail AI back to Google's servers (`users.messages.modify`).
2. 🎨 **Light/Dark Mode Theme Switcher**: CSS variable refactoring for theme switching.
3. 🚀 **Product Landing Page**: Interactive landing page (`landing.html`) for new visitors.
4. 🍔 **Hamburger Drawer Navigation**: Responsive collapsible sidebar toggle.

### **Long-Term Roadmap**
1. ⏰ **Email Scheduling**: Queue delayed dispatches (*"Send tomorrow at 9 AM"*).
2. ↩️ **Undo Send Buffer**: 10-second safety buffer to cancel email transmission.
3. 📅 **Calendar & Outlook Integration**: Multi-provider email and calendar sync.
