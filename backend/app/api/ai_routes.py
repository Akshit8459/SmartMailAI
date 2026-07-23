"""
AI & RAG routes — query, streaming query, summarization, thread summary,
attachment Q&A, search suggestions, and AI reply generation.
"""
import json
import time
from fastapi import APIRouter, Depends, HTTPException, Body, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import decode_access_token
from app.domain.dtos import (
    RAGQueryRequest, RAGQueryResponse,
    AttachmentQueryRequest, SearchSuggestionsRequest, ThreadSummaryRequest,
)
from app.services.ai.rag_service import RAGService
from app.services.ai.llm import get_llm_client
from app.services.ai.prompt_builder import prompt_builder
from app.repositories.email_repository import EmailRepository

router = APIRouter(prefix="/ai", tags=["AI & RAG Assistant"])


def get_user_id(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = decode_access_token(auth.removeprefix("Bearer ").strip())
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_id


# ─── Standard RAG Q&A ─────────────────────────────────────────────────────────

@router.post("/query", response_model=RAGQueryResponse)
async def query_rag(request: Request, req: RAGQueryRequest, db: AsyncSession = Depends(get_db)):
    user_id = get_user_id(request)
    rag_svc = RAGService(db)
    res = await rag_svc.answer_question(user_id=user_id, query=req.query)
    return RAGQueryResponse(
        session_id=req.session_id or "default-session",
        answer=res["answer"],
        sources=res["sources"]
    )


# ─── Streaming RAG Q&A ────────────────────────────────────────────────────────

@router.post("/query-stream")
async def query_rag_stream(request: Request, req: RAGQueryRequest, db: AsyncSession = Depends(get_db)):
    user_id = get_user_id(request)
    rag_svc = RAGService(db)

    async def event_generator():
        try:
            sources = await rag_svc.get_sources_for_query(user_id=user_id, query=req.query)
            yield f"data: {json.dumps({'type': 'sources', 'sources': sources})}\n\n"

            async for chunk in rag_svc.answer_question_stream(user_id=user_id, query=req.query):
                yield f"data: {json.dumps({'type': 'text', 'text': chunk})}\n\n"
        except Exception as ex:
            yield f"data: {json.dumps({'type': 'text', 'text': f'An error occurred while analyzing emails: {str(ex)}'})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ─── AI Action Execution ──────────────────────────────────────────────────────

class ActionExecutionRequest(BaseModel):
    prompt: str

@router.post("/execute-action")
async def execute_action_route(
    request: Request,
    req: ActionExecutionRequest,
    db: AsyncSession = Depends(get_db)
):
    user_id = get_user_id(request)
    from app.services.ai.action_executor import ActionExecutor
    executor = ActionExecutor(db)
    result = await executor.execute_intent(user_id, req.prompt)
    return result


# ─── Email Summarization ──────────────────────────────────────────────────────

@router.post("/summarize-email")
async def summarize_email(
    request: Request,
    email_id: str = Body(..., embed=True),
    db: AsyncSession = Depends(get_db),
):
    _user_id = get_user_id(request)
    repo = EmailRepository(db)
    email = await repo.get_email_by_id(email_id, _user_id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    llm = get_llm_client()
    att_summaries = []
    if email.attachments:
        for att in email.attachments:
            text = (att.extracted_text or "").strip()
            if len(text) > 30:
                doc_ctx = text if len(text) <= 12000 else f"{text[:6000]}\n\n[... Middle content ...]\n\n{text[-6000:]}"
                doc_prompt = (
                    f"Document Filename: {att.filename}\n\n"
                    f"Extracted Document Content:\n{doc_ctx}\n\n"
                    f"Provide a comprehensive, high-impact document summary. "
                    f"Detail:\n"
                    f"- Core Purpose & Problem Statement\n"
                    f"- Key Findings, Quantitative Metrics, & Technical Figures\n"
                    f"- Preprocessing Rules, Modeling Actions & Milestones\n"
                    f"- Action Items, Deadlines & Financial Amounts"
                )
                try:
                    att_sum = await llm.generate_text(doc_prompt, "You are a senior data & document analysis AI. Output structured Markdown.")
                    att_summaries.append(f"📄 **Attachment '{att.filename}' Deep AI Analysis**:\n{att_sum}")
                except Exception:
                    att_summaries.append(f"📄 **Attachment '{att.filename}'**:\n• Document indexed ({len(text)} chars)")
            else:
                att_summaries.append(f"📄 **Attachment '{att.filename}'**: (No readable text)")

    attachments_combined = "\n\n".join(att_summaries)

    prompt = prompt_builder.build_summary_prompt(
        email.body_text or email.snippet, email.subject, attachments_text=attachments_combined
    )
    summary = await llm.generate_text(prompt, prompt_builder.SYSTEM_SUMMARY_PROMPT)
    date_str = email.received_at.strftime("%Y-%m-%d %H:%M") if email.received_at else ""
    return {
        "email_id": email_id,
        "summary": summary,
        "subject": email.subject,
        "sender": email.sender_name or email.sender_email,
        "date": date_str,
    }


# ─── Thread Timeline Summarization (streaming) ────────────────────────────────

@router.post("/summarize-thread")
async def summarize_thread(
    request: Request,
    req: ThreadSummaryRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Stream a structured AI summary of an entire email thread.
    Response is Server-Sent Events: { type: 'text', text: '...' } chunks.
    """
    _user_id = get_user_id(request)
    rag_svc = RAGService(db)

    async def event_generator():
        stream = await rag_svc.summarize_thread(
            thread_id=req.thread_id,
            user_id=_user_id,
        )
        async for chunk in stream:
            yield f"data: {json.dumps({'type': 'text', 'text': chunk})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


# ─── Attachment Q&A ───────────────────────────────────────────────────────────

@router.post("/ask-attachment")
async def ask_attachment(
    request: Request,
    req: AttachmentQueryRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Answer a question about an attachment's content using its extracted text chunks.
    """
    _user_id = get_user_id(request)
    repo = EmailRepository(db)

    # Retrieve the attachment record
    attachment = await repo.get_attachment_by_id(req.attachment_id)
    if not attachment and req.email_id:
        email = await repo.get_email_by_id(req.email_id, _user_id)
        if email and email.attachments:
            attachment = email.attachments[0]

    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    extracted_text = attachment.extracted_text or ""
    if not extracted_text or extracted_text.startswith("["):
        return {
            "answer": f"The attachment '{attachment.filename}' could not be parsed for text content. "
                      f"It may be a scanned image or binary file.",
            "attachment_id": req.attachment_id,
            "filename": attachment.filename,
        }

    # Build context from the extracted text across all pages/slides
    if len(extracted_text) <= 12000:
        context = extracted_text
    else:
        head = extracted_text[:6000]
        tail = extracted_text[-6000:]
        context = f"{head}\n\n[... Document middle content ...]\n\n{tail}"

    prompt = (
        f"Attachment filename: {attachment.filename}\n\n"
        f"Extracted document content:\n{context}\n\n"
        f"User question: {req.question}\n\n"
        f"Please analyze the document content above and answer the question thoroughly. "
        f"Explicitly extract all action items, preprocessing rules, milestones, dates, and quantitative metrics mentioned."
    )
    llm = get_llm_client()
    system_prompt = (
        "You are a document analysis assistant. Answer questions accurately and concisely "
        "based only on the provided attachment content."
    )
    answer = await llm.generate_text(prompt, system_prompt)

    return {
        "answer": answer,
        "attachment_id": req.attachment_id,
        "filename": attachment.filename,
    }


# ─── AI Search Suggestions ────────────────────────────────────────────────────

@router.post("/search-suggestions")
async def get_search_suggestions(
    request: Request,
    req: SearchSuggestionsRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Return 5 AI-generated search query completions based on the user's partial input
    and their email corpus.
    """
    user_id = get_user_id(request)

    if len(req.partial_query.strip()) < 2:
        return {"suggestions": []}

    repo = EmailRepository(db)

    # Get a sample of recent email subjects for context
    recent_emails = await repo.get_user_emails(user_id, label="INBOX", limit=20)
    subjects = [e.subject for e in recent_emails if e.subject]

    prompt = prompt_builder.build_search_suggestions_prompt(req.partial_query, subjects)
    llm = get_llm_client()

    try:
        raw = await llm.generate_text(prompt, prompt_builder.SYSTEM_SUGGESTIONS_PROMPT)
        # Parse JSON array from response
        # Strip markdown code fences if present
        clean = raw.strip().strip("```json").strip("```").strip()
        suggestions = json.loads(clean)
        if not isinstance(suggestions, list):
            suggestions = []
        suggestions = [str(s) for s in suggestions[:req.limit]]
    except Exception:
        # Graceful fallback — common intent completions
        q = req.partial_query.lower()
        suggestions = [
            f"{req.partial_query} from last week",
            f"{req.partial_query} with attachments",
            f"unread {req.partial_query}",
            f"{req.partial_query} invoice",
            f"{req.partial_query} important",
        ][:req.limit]

    return {"suggestions": suggestions, "query": req.partial_query}


# ─── AI Reply Generation ──────────────────────────────────────────────────────

@router.post("/generate-reply")
async def generate_reply(
    request: Request,
    email_id: str = Body(...),
    user_intent: str = Body("Thank the sender and confirm my availability."),
    db: AsyncSession = Depends(get_db),
):
    _user_id = get_user_id(request)
    repo = EmailRepository(db)
    email = await repo.get_by_id(email_id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")

    llm = get_llm_client()
    prompt = prompt_builder.build_reply_prompt(email.body_text or email.snippet, user_intent)
    draft_reply = await llm.generate_text(prompt, prompt_builder.SYSTEM_REPLY_PROMPT)
    return {
        "email_id": email_id,
        "recipient": email.sender_email,
        "subject": f"Re: {email.subject}",
        "draft_reply": draft_reply,
    }
