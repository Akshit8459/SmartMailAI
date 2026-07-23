from typing import AsyncGenerator, Dict, Any, List
import time
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.ai.llm import get_llm_client
from app.services.ai.hybrid_retrieval import hybrid_retriever
from app.services.ai.reranker import reranker
from app.services.ai.prompt_builder import prompt_builder
from app.repositories.email_repository import EmailRepository
from app.models.entities import EmailChunk


class RAGService:
    """Orchestrates Hybrid Retrieval, Reranking, Prompt Building, and Pluggable LLM Generation."""

    def __init__(self, session: AsyncSession):
        self.email_repo = EmailRepository(session)
        self.llm_client = get_llm_client()

    async def _ensure_user_chunks(self, user_id: str) -> List[EmailChunk]:
        """
        Ensures that ALL emails in the user's inbox are chunked and present in the AI context.
        Detects any unchunked emails and dynamically generates embeddings for them.
        """
        from app.services.indexing.semantic_chunker import semantic_chunker

        # Get existing email IDs that have chunks
        all_chunks = await self.email_repo.get_user_chunks(user_id)
        chunked_email_ids = {c.email_id for c in all_chunks if c.email_id}

        # Fetch all emails for this user
        all_user_emails = await self.email_repo.get_user_emails(user_id, label="ALL", limit=300)
        real_email_ids = {e.id for e in all_user_emails}

        # Purge any orphaned demo chunks whose email no longer exists in DB for this user
        orphaned_chunks = [c for c in all_chunks if c.email_id not in real_email_ids]
        if orphaned_chunks:
            for oc in orphaned_chunks:
                await self.email_repo.session.delete(oc)
            try:
                await self.email_repo.session.commit()
            except Exception:
                await self.email_repo.session.rollback()
            all_chunks = await self.email_repo.get_user_chunks(user_id)

        chunked_email_ids = {c.email_id for c in all_chunks if c.email_id}
        unchunked_emails = [e for e in all_user_emails if e.id not in chunked_email_ids]

        if unchunked_emails:
            for email in unchunked_emails:
                date_str = email.received_at.strftime("%Y-%m-%d") if email.received_at else ""
                chunks_data = semantic_chunker.chunk_email(
                    email_id=email.id,
                    thread_id=email.thread_id,
                    user_id=user_id,
                    sender=email.sender_name or email.sender_email,
                    subject=email.subject,
                    date_str=date_str,
                    body_text=email.body_text or email.snippet or ""
                )
                for c_data in chunks_data:
                    chunk_entity = EmailChunk(
                        email_id=c_data["email_id"],
                        thread_id=c_data["thread_id"],
                        user_id=c_data["user_id"],
                        chunk_index=c_data["chunk_index"],
                        content=c_data["content"],
                        chunk_metadata=c_data["chunk_metadata"],
                        embedding=c_data["embedding"]
                    )
                    self.email_repo.session.add(chunk_entity)

                if email.attachments:
                    for att in email.attachments:
                        if att.extracted_text:
                            att_chunks = semantic_chunker.chunk_attachment(
                                email_id=email.id,
                                thread_id=email.thread_id,
                                user_id=user_id,
                                attachment_id=att.id,
                                filename=att.filename,
                                extracted_text=att.extracted_text,
                                subject=email.subject,
                                sender=email.sender_name or email.sender_email,
                                date_str=date_str
                            )
                            for c_data in att_chunks:
                                chunk_entity = EmailChunk(
                                    email_id=c_data["email_id"],
                                    thread_id=c_data["thread_id"],
                                    user_id=c_data["user_id"],
                                    chunk_index=c_data["chunk_index"],
                                    content=c_data["content"],
                                    chunk_metadata=c_data["chunk_metadata"],
                                    embedding=c_data["embedding"]
                                )
                                self.email_repo.session.add(chunk_entity)

            try:
                await self.email_repo.session.commit()
            except Exception:
                await self.email_repo.session.rollback()

            all_chunks = await self.email_repo.get_user_chunks(user_id)

        return all_chunks

    async def get_sources_for_query(self, user_id: str, query: str, top_k: int = 15) -> List[Dict[str, Any]]:
        await self._ensure_user_chunks(user_id)
        
        q_lower = query.lower()
        is_intent_query = any(w in q_lower for w in ["unread", "recent", "latest", "inbox", "summarize", "overview", "starred", "important", "all"])

        if is_intent_query:
            chunks = await self.email_repo.get_relevant_chunks(user_id, query, limit=50)
            top_chunks = self._deduplicate_chunks_by_email(chunks, max_emails=top_k)
        else:
            chunks = await self.email_repo.get_relevant_chunks(user_id, query, limit=80)
            candidates = hybrid_retriever.retrieve(query, chunks, top_k=25)
            top_chunks = reranker.rerank(query, candidates, top_k=top_k)

        sources = []
        seen_emails = set()
        for chunk in top_chunks:
            eid = chunk.get("email_id") if isinstance(chunk, dict) else getattr(chunk, "email_id", None)
            if eid and eid not in seen_emails:
                seen_emails.add(eid)
                meta = chunk.get("chunk_metadata", {}) if isinstance(chunk, dict) else (chunk.chunk_metadata or {})
                content = chunk.get("content", "") if isinstance(chunk, dict) else (chunk.content or "")
                sources.append({
                    "email_id": eid,
                    "thread_id": chunk.get("thread_id", "") if isinstance(chunk, dict) else getattr(chunk, "thread_id", ""),
                    "subject": meta.get("subject", "Email Reference"),
                    "sender": meta.get("sender", "Sender"),
                    "date": meta.get("date", ""),
                    "snippet": content[:120] + "...",
                    "source_type": meta.get("source_type", "email"),
                })
        return sources

    def _deduplicate_chunks_by_email(self, chunks: List[Any], max_emails: int = 30) -> List[Dict[str, Any]]:
        """Takes 1 representative chunk per distinct email to ensure broad coverage across senders, preserving latest-to-oldest order."""
        seen = set()
        deduped = []
        for chunk in chunks:
            eid = getattr(chunk, "email_id", None) or (chunk.get("email_id") if isinstance(chunk, dict) else None)
            if eid and eid not in seen:
                seen.add(eid)
                if isinstance(chunk, dict):
                    deduped.append(chunk)
                else:
                    deduped.append({
                        "id": chunk.id,
                        "email_id": chunk.email_id,
                        "thread_id": chunk.thread_id,
                        "content": chunk.content,
                        "chunk_metadata": chunk.chunk_metadata or {},
                    })
                if len(deduped) >= max_emails:
                    break
        return deduped

    async def answer_question(
        self,
        user_id: str,
        query: str,
        chat_history: List[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        t0 = time.monotonic()
        # Always synchronize any new inbox emails into chunks before processing query
        await self._ensure_user_chunks(user_id)

        q_lower = query.lower()
        is_intent_query = any(w in q_lower for w in ["unread", "recent", "latest", "inbox", "summarize", "overview", "starred", "important", "all"])

        if is_intent_query:
            chunks = await self.email_repo.get_relevant_chunks(user_id, query, limit=50)
            top_chunks = self._deduplicate_chunks_by_email(chunks, max_emails=30)
        else:
            chunks = await self.email_repo.get_relevant_chunks(user_id, query, limit=80)
            candidates = hybrid_retriever.retrieve(query, chunks, top_k=25)
            top_chunks = reranker.rerank(query, candidates, top_k=6)

        prompt = prompt_builder.build_rag_prompt(query, top_chunks, chat_history)
        answer = await self.llm_client.generate_text(prompt, prompt_builder.SYSTEM_RAG_PROMPT)

        # Build sources directly from top_chunks (instant, no extra DB query)
        sources = []
        seen_emails = set()
        for chunk in top_chunks:
            eid = chunk.get("email_id")
            if eid and eid not in seen_emails:
                seen_emails.add(eid)
                meta = chunk.get("chunk_metadata", {})
                sources.append({
                    "email_id": eid,
                    "thread_id": chunk.get("thread_id", ""),
                    "subject": meta.get("subject", "Email Reference"),
                    "sender": meta.get("sender", "Sender"),
                    "date": meta.get("date", ""),
                    "snippet": (chunk.get("content") or "")[:120] + "...",
                    "source_type": meta.get("source_type", "email"),
                })

        try:
            from app.api.eval_routes import record_latency
            record_latency((time.monotonic() - t0) * 1000)
        except Exception:
            pass

        return {"answer": answer, "sources": sources[:10]}

    async def answer_question_stream(
        self,
        user_id: str,
        query: str,
        chat_history: List[Dict[str, str]] = None,
    ) -> AsyncGenerator[str, None]:
        t0 = time.monotonic()
        # Always synchronize any new inbox emails into chunks before processing query
        await self._ensure_user_chunks(user_id)

        q_lower = query.lower()
        is_intent_query = any(w in q_lower for w in ["unread", "recent", "latest", "inbox", "summarize", "overview", "starred", "important", "all"])

        if is_intent_query:
            chunks = await self.email_repo.get_relevant_chunks(user_id, query, limit=50)
            top_chunks = self._deduplicate_chunks_by_email(chunks, max_emails=30)
        else:
            chunks = await self.email_repo.get_relevant_chunks(user_id, query, limit=80)
            candidates = hybrid_retriever.retrieve(query, chunks, top_k=25)
            top_chunks = reranker.rerank(query, candidates, top_k=6)

        prompt = prompt_builder.build_rag_prompt(query, top_chunks, chat_history)

        async for chunk in self.llm_client.generate_stream(prompt, prompt_builder.SYSTEM_RAG_PROMPT):
            yield chunk

        try:
            from app.api.eval_routes import record_latency
            record_latency((time.monotonic() - t0) * 1000)
        except Exception:
            pass

    async def summarize_thread(
        self,
        thread_id: str,
        user_id: str,
    ) -> AsyncGenerator[str, None]:
        """
        Fetch all emails in a thread, build a chronological timeline,
        and stream an LLM-generated structured summary.
        """
        thread_emails = await self.email_repo.get_thread_emails(thread_id)
        if not thread_emails:
            async def _empty():
                yield "No messages found in this thread."
            return _empty()

        # Build timeline messages list for prompt builder
        messages = []
        for email in sorted(thread_emails, key=lambda e: e.received_at or 0):
            date_str = email.received_at.strftime("%Y-%m-%d %H:%M") if email.received_at else ""
            att_text_list = []
            if email.attachments:
                for att in email.attachments:
                    text = (att.extracted_text or "").strip()
                    if text:
                        att_text_list.append(f"Document File '{att.filename}':\n{text[:4000]}")
            messages.append({
                "sender_name": email.sender_name,
                "sender_email": email.sender_email,
                "date_str": date_str,
                "subject": email.subject,
                "body_text": (email.body_text or email.snippet or "")[:800],
                "attachments_text": "\n\n".join(att_text_list),
            })

        prompt = prompt_builder.build_thread_summary_prompt(messages)

        async def _stream():
            async for chunk in self.llm_client.generate_stream(
                prompt, prompt_builder.SYSTEM_THREAD_SUMMARY_PROMPT
            ):
                yield chunk

        return _stream()
