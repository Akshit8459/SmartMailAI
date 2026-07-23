"""
Smart Hybrid Search Engine — Exact & Semantic Relevance Search for SmartMail.

Features:
1. Exact matching on Subject / Title, Sender Name & Email, Body Text, and Attachments.
2. Semantic vector RAG retrieval via Hybrid Retriever (BM25 + Dense Cosine).
3. Relevance-based multi-factor scoring (Subject > Sender > Body > Attachment > Semantic).
4. Text snippet extraction (surrounding matched query terms with context window).
"""
import re
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import desc

from app.models.entities import Email, Attachment, EmailChunk
from app.domain.dtos import EmailDTO, AttachmentDTO
from app.services.ai.hybrid_retrieval import hybrid_retriever
from app.utils.sanitizer import sanitize_html, resolve_cid_images


def extract_context_snippet(text: str, query: str, window: int = 120) -> str:
    """Extract a text snippet around the first occurrence of query term."""
    if not text or not query:
        return (text or "")[:140]
    
    # Try exact match first
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    match = pattern.search(text)
    
    if not match:
        # Try individual words
        words = [w for w in query.split() if len(w) > 2]
        for w in words:
            pattern = re.compile(re.escape(w), re.IGNORECASE)
            match = pattern.search(text)
            if match:
                break
                
    if match:
        start_idx = max(0, match.start() - window // 2)
        end_idx = min(len(text), match.end() + window // 2)
        snippet = text[start_idx:end_idx].strip()
        if start_idx > 0:
            snippet = "..." + snippet
        if end_idx < len(text):
            snippet = snippet + "..."
        return snippet
    
    return text[:140] + ("..." if len(text) > 140 else "")


class SmartSearchEngine:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def search(self, user_id: str, query: str, limit: int = 40) -> List[Dict[str, Any]]:
        if not query or not query.strip():
            return []

        q_clean = query.strip()
        q_lower = q_clean.lower()
        q_words = set(q_lower.split())

        # ── 1. Fetch all user emails with attachments ───────────────────────────
        stmt = select(Email).where(Email.user_id == user_id).options(selectinload(Email.attachments))
        res = await self.session.execute(stmt)
        all_emails = res.scalars().all()

        if not all_emails:
            return []

        email_map: Dict[str, Email] = {e.id: e for e in all_emails}
        scores: Dict[str, Dict[str, Any]] = {}

        # Initialize tracking dict for every email
        for e in all_emails:
            scores[e.id] = {
                "email": e,
                "score": 0,
                "match_type": None,
                "match_snippet": None,
            }

        # ── 2. Exact Metadata & Keyword Matching ──────────────────────────────
        for e in all_emails:
            entry = scores[e.id]
            subject_lower = (e.subject or "").lower()
            sender_name_lower = (e.sender_name or "").lower()
            sender_email_lower = (e.sender_email or "").lower()
            body_lower = (e.body_text or e.snippet or "").lower()

            # A. Title / Subject match (Highest Priority)
            if q_lower == subject_lower:
                entry["score"] += 120
                entry["match_type"] = "Subject Exact Match"
                entry["match_snippet"] = e.subject
            elif q_lower in subject_lower:
                entry["score"] += 90
                if not entry["match_type"]:
                    entry["match_type"] = "Subject Match"
                    entry["match_snippet"] = extract_context_snippet(e.subject, q_clean, window=80)
            elif any(w in subject_lower for w in q_words if len(w) > 2):
                entry["score"] += 40
                if not entry["match_type"]:
                    entry["match_type"] = "Subject Keyword"
                    entry["match_snippet"] = e.subject

            # B. Sender Name / Email match
            if q_lower in sender_name_lower or q_lower in sender_email_lower:
                entry["score"] += 85
                if not entry["match_type"]:
                    entry["match_type"] = "Sender Match"
                    entry["match_snippet"] = f"From: {e.sender_name or e.sender_email}"
            elif any(w in sender_name_lower or w in sender_email_lower for w in q_words if len(w) > 2):
                entry["score"] += 35
                if not entry["match_type"]:
                    entry["match_type"] = "Sender Keyword"
                    entry["match_snippet"] = f"From: {e.sender_name or e.sender_email}"

            # C. Body / Content match
            if q_lower in body_lower:
                entry["score"] += 60
                if not entry["match_type"]:
                    entry["match_type"] = "Body Match"
                    entry["match_snippet"] = extract_context_snippet(e.body_text or e.snippet, q_clean)
            elif any(w in body_lower for w in q_words if len(w) > 2):
                entry["score"] += 25
                if not entry["match_type"]:
                    entry["match_type"] = "Content Match"
                    entry["match_snippet"] = extract_context_snippet(e.body_text or e.snippet, q_clean)

            # D. Attachment Match
            for att in (e.attachments or []):
                fname = (att.filename or "").lower()
                atext = (att.extracted_text or "").lower()
                if q_lower in fname or any(w in fname for w in q_words if len(w) > 2):
                    entry["score"] += 50
                    if not entry["match_type"]:
                        entry["match_type"] = "Attachment Match"
                        entry["match_snippet"] = f"Attachment: {att.filename}"
                elif q_lower in atext or any(w in atext for w in q_words if len(w) > 2):
                    entry["score"] += 45
                    if not entry["match_type"]:
                        entry["match_type"] = "Attachment Content Match"
                        entry["match_snippet"] = f"In {att.filename}: " + extract_context_snippet(att.extracted_text, q_clean)

        # ── 3. Hybrid RAG Vector Retrieval (Semantic Matches) ─────────────────
        try:
            chunk_stmt = select(EmailChunk).where(EmailChunk.user_id == user_id)
            chunk_res = await self.session.execute(chunk_stmt)
            chunks = chunk_res.scalars().all()

            if chunks:
                retrieved = hybrid_retriever.retrieve(q_clean, chunks, top_k=25)
                for item in retrieved:
                    eid = item.get("email_id")
                    if eid and eid in scores:
                        rrf = item.get("rrf_score", 0)
                        dense = item.get("dense_score", 0)
                        sparse = item.get("sparse_score", 0)
                        
                        # Add semantic vector boost
                        semantic_boost = int((rrf * 1500) + (dense * 30))
                        scores[eid]["score"] += semantic_boost

                        if not scores[eid]["match_type"]:
                            scores[eid]["match_type"] = "Suggested (Semantic AI Match)"
                            scores[eid]["match_snippet"] = extract_context_snippet(item.get("content", ""), q_clean)
        except Exception:
            pass  # Fall back gracefully to SQL match scores if chunk search fails

        # ── 4. Filter and Sort Results by Relevance ───────────────────────────
        matching_results = [v for v in scores.values() if v["score"] > 0]

        # Recency small tie-breaker bonus (up to 10 pts)
        for item in matching_results:
            e = item["email"]
            if e.received_at:
                try:
                    ts = e.received_at.timestamp()
                    item["score"] += min(10, ts / 1e9)
                except Exception:
                    pass

        matching_results.sort(key=lambda x: x["score"], reverse=True)
        matching_results = matching_results[:limit]

        # ── 5. Format to DTO dicts ─────────────────────────────────────────────
        final_list = []
        for item in matching_results:
            e = item["email"]
            dto = EmailDTO.model_validate(e)
            dto.body_html = resolve_cid_images(sanitize_html(dto.body_html))
            dto.match_type = item["match_type"] or "Search Match"
            dto.match_snippet = item["match_snippet"] or (e.snippet or "")[:120]
            dto.relevance_score = int(item["score"])
            final_list.append(dto.model_dump())

        return final_list


smart_search_engine = SmartSearchEngine
