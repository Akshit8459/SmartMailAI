"""
RAG Evaluation Router — exposes system stats for the developer dashboard.
"""
import time
from collections import defaultdict
from typing import Dict, Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from app.core.database import get_db
from app.core.security import decode_access_token
from fastapi import HTTPException
from app.models.entities import EmailChunk, Email
from app.services.ai.llm import get_llm_client

router = APIRouter(prefix="/eval", tags=["RAG Evaluation"])

# In-memory latency ring buffer (last 50 queries)
_latency_log: list = []
_MAX_LOG = 50


def get_user_id(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = decode_access_token(auth.removeprefix("Bearer ").strip())
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user_id


def record_latency(latency_ms: float):
    """Called by RAG service to record query latency for the dashboard."""
    global _latency_log
    _latency_log.append(latency_ms)
    if len(_latency_log) > _MAX_LOG:
        _latency_log = _latency_log[-_MAX_LOG:]


@router.get("/stats")
async def get_rag_stats(request: Request, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """
    Returns live RAG system statistics for the developer dashboard:
    - Total chunks indexed (all users)
    - Avg embedding dimensions
    - LLM provider status
    - Average retrieval latency (from in-memory log)
    - Email vs attachment chunk breakdown
    """
    user_id = get_user_id(request)

    from app.services.ai.qdrant_service import qdrant_svc
    from app.core.config import settings
    qdrant_online = await qdrant_svc.is_available()

    # Count chunks for this user
    chunk_count_result = await db.execute(
        select(func.count(EmailChunk.id)).where(EmailChunk.user_id == user_id)
    )
    total_chunks = chunk_count_result.scalar() or 0

    # Count email rows for this user
    email_count_result = await db.execute(
        select(func.count(Email.id)).where(Email.user_id == user_id)
    )
    total_emails = email_count_result.scalar() or 0

    # Sample one chunk to get embedding dimensions
    sample_chunk_result = await db.execute(
        select(EmailChunk.embedding).where(EmailChunk.user_id == user_id).limit(1)
    )
    sample_row = sample_chunk_result.scalar()
    embedding_dims = len(sample_row) if isinstance(sample_row, list) else 0

    # Source-type breakdown from chunk metadata
    all_chunks_result = await db.execute(
        select(EmailChunk.chunk_metadata).where(EmailChunk.user_id == user_id).limit(500)
    )
    all_meta = all_chunks_result.scalars().all()
    source_breakdown: Dict[str, int] = defaultdict(int)
    for meta in all_meta:
        if isinstance(meta, dict):
            source_type = meta.get("source_type", "email")
            source_breakdown[source_type] += 1

    # Latency stats
    avg_latency = round(sum(_latency_log) / len(_latency_log), 1) if _latency_log else 0
    last_latency = round(_latency_log[-1], 1) if _latency_log else 0

    # LLM provider check
    llm = get_llm_client()
    provider_name = getattr(llm, "_provider_name", type(llm).__name__)

    return {
        "total_chunks": total_chunks,
        "total_emails_indexed": total_emails,
        "embedding_dimensions": embedding_dims,
        "source_breakdown": dict(source_breakdown),
        "avg_retrieval_latency_ms": avg_latency,
        "last_latency_ms": last_latency,
        "queries_tracked": len(_latency_log),
        "llm_provider": provider_name,
        "qdrant_online": qdrant_online,
        "qdrant_host": settings.QDRANT_HOST,
        "qdrant_collection": settings.QDRANT_COLLECTION,
        "status": "healthy",
    }


@router.get("/health")
async def health_check() -> Dict[str, str]:
    """Standard health endpoint."""
    return {"status": "ok", "service": "SmartMail AI Backend"}


@router.get("/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)) -> Dict[str, str]:
    """Readiness probe — checks DB connection."""
    try:
        await db.execute(select(func.now()))
        return {"status": "ready", "db": "connected"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"DB not ready: {e}")
