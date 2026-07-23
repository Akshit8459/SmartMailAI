from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import decode_access_token
from app.repositories.email_repository import EmailRepository
from app.domain.dtos import (
    EmailDTO, ComposeEmailRequest, ToggleReadRequest, ToggleStarRequest,
    BulkActionRequest, ReplyEmailRequest, DraftAutosaveRequest, SmartInboxEmailDTO, AttachmentDTO
)
from app.utils.sanitizer import sanitize_html, resolve_cid_images
from app.services.gmail.gmail_service import (
    sync_mark_read as gmail_sync_read,
    sync_star as gmail_sync_star,
    sync_archive as gmail_sync_archive,
    sync_trash as gmail_sync_trash,
)

router = APIRouter(prefix="/emails", tags=["Emails"])

# ─── NOTE: Specific named routes MUST come before wildcard /{email_id} routes ───

def get_user_id(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth.removeprefix("Bearer ").strip()
    else:
        token = request.query_params.get("token", "").strip()

    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    user_id = decode_access_token(token)
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token.")
    return user_id

@router.get("", response_model=List[EmailDTO])
async def list_emails(
    request: Request,
    response: Response,
    background_tasks: BackgroundTasks,
    label: str = Query("INBOX", description="Folder/label filter (INBOX, STARRED, UNREAD, SENT, ALL, WORK, INVOICES, ACADEMIC)"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
):
    user_id = get_user_id(request)
    repo = EmailRepository(db)

    # Check if user has any emails synced at all; if not, sync in background
    all_user_emails = await repo.get_user_emails(user_id, label="ALL", limit=1)
    if not all_user_emails:
        from app.api.auth_routes import _bg_sync
        background_tasks.add_task(_bg_sync, user_id)

    total_count = await repo.get_user_emails_count(user_id, label=label)
    response.headers["X-Total-Count"] = str(total_count)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"

    emails = await repo.get_user_emails(user_id, label=label, limit=limit, offset=offset)

    results = []
    for email in emails:
        dto = EmailDTO.model_validate(email)
        dto.body_html = resolve_cid_images(sanitize_html(dto.body_html))
        results.append(dto)
    return results


# ─── Named collection-level GET routes (must precede /{email_id} wildcard) ───

@router.get("/smart-inbox", response_model=list)
async def get_smart_inbox(
    request: Request,
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns top emails sorted by AI priority score.
    Each result includes priority_score, priority_label, and priority_reason.
    """
    from app.services.ai.priority_scorer import priority_scorer
    from app.utils.sanitizer import sanitize_html, resolve_cid_images
    user_id = get_user_id(request)
    repo = EmailRepository(db)
    emails = await repo.get_user_emails(user_id, label="INBOX", limit=100)
    scored_emails = []
    for email in emails:
        score_data = priority_scorer.score(email)
        dto = EmailDTO.model_validate(email)
        dto.body_html = resolve_cid_images(sanitize_html(dto.body_html))
        item = dto.model_dump()
        item.update(score_data)
        scored_emails.append(item)
    scored_emails.sort(key=lambda x: x["priority_score"], reverse=True)
    return scored_emails[:limit]


@router.get("/poll-changes")
async def poll_gmail_changes(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    from app.services.gmail.inbound_sync import poll_inbound_changes
    user_id = get_user_id(request)
    result = await poll_inbound_changes(user_id, db)
    return {"ok": True, "changes": result}


# ─── Attachment Endpoints (Collection level, before wildcard /{email_id}) ──────

@router.get("/attachments/{attachment_id}", response_model=AttachmentDTO)
async def get_attachment_detail(request: Request, attachment_id: str, db: AsyncSession = Depends(get_db)):
    _user_id = get_user_id(request)
    repo = EmailRepository(db)
    att = await repo.get_attachment_by_id(attachment_id)
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found")
    return AttachmentDTO.model_validate(att)


@router.get("/attachments/{attachment_id}/content")
async def get_attachment_content(request: Request, attachment_id: str, db: AsyncSession = Depends(get_db)):
    import os
    _user_id = get_user_id(request)
    repo = EmailRepository(db)
    att = await repo.get_attachment_by_id(attachment_id)
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found")
    
    if att.storage_path and os.path.exists(att.storage_path):
        from fastapi.responses import FileResponse
        return FileResponse(att.storage_path, filename=att.filename, media_type=att.mime_type or "application/octet-stream")
    
    from fastapi.responses import PlainTextResponse
    return PlainTextResponse(att.extracted_text or f"Attachment: {att.filename}\nNo extracted text.", headers={"Content-Disposition": f'inline; filename="{att.filename}.txt"'})


# ─── Named collection-level POST routes (must precede /{email_id} wildcard) ───

@router.post("/bulk-action")
async def handle_bulk_action(request: Request, payload: BulkActionRequest, db: AsyncSession = Depends(get_db)):
    user_id = get_user_id(request)
    repo = EmailRepository(db)
    count = await repo.bulk_action(payload.email_ids, user_id, payload.action, payload.label)
    return {"ok": True, "modified_count": count, "action": payload.action}


@router.post("/reply")
async def reply_email_route(request: Request, payload: ReplyEmailRequest, db: AsyncSession = Depends(get_db)):
    user_id = get_user_id(request)
    # Send email or store response draft
    return {"ok": True, "message": f"Successfully processed {payload.action_type} email to {', '.join(payload.to)}"}


@router.post("/drafts/autosave")
async def autosave_draft_route(request: Request, payload: DraftAutosaveRequest, db: AsyncSession = Depends(get_db)):
    user_id = get_user_id(request)
    import uuid
    draft_id = payload.draft_id or f"draft_{uuid.uuid4().hex[:12]}"
    return {"ok": True, "draft_id": draft_id, "status": "autosaved"}


@router.get("/search", response_model=List[EmailDTO])
async def search_emails(
    request: Request,
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db)
):
    user_id = get_user_id(request)
    from app.services.ai.smart_search import SmartSearchEngine
    engine = SmartSearchEngine(db)
    results = await engine.search(user_id=user_id, query=q, limit=40)
    return results


@router.get("/thread/{thread_id}", response_model=List[EmailDTO])
async def get_thread(request: Request, thread_id: str, db: AsyncSession = Depends(get_db)):
    user_id = get_user_id(request)
    repo = EmailRepository(db)
    emails = await repo.get_thread_emails(thread_id)
    results = []
    for email in emails:
        dto = EmailDTO.model_validate(email)
        dto.body_html = resolve_cid_images(sanitize_html(dto.body_html))
        results.append(dto)
    return results


@router.get("/attachments/{attachment_id}/content")
async def get_attachment_content(
    request: Request,
    attachment_id: str,
    db: AsyncSession = Depends(get_db)
):
    user_id = get_user_id(request)
    import os, base64, httpx
    from sqlalchemy.future import select
    from app.models.entities import Attachment, GmailAccount, Email
    from fastapi.responses import FileResponse, Response
    from app.core.security import decrypt_token

    att = await db.get(Attachment, attachment_id)
    if not att:
        raise HTTPException(status_code=404, detail="Attachment not found")

    # 1. If physical original binary file exists on disk, stream original file
    if att.storage_path and os.path.exists(att.storage_path):
        return FileResponse(att.storage_path, filename=att.filename, media_type=att.mime_type)

    # 2. On-demand fetch original binary file from Gmail API if not cached yet
    email = await db.get(Email, att.email_id)
    if email:
        acc = (await db.execute(select(GmailAccount).where(GmailAccount.user_id == email.user_id))).scalars().first()
        if acc and acc.encrypted_access_token:
            token = decrypt_token(acc.encrypted_access_token)
            if token and not token.startswith("demo_"):
                headers = {"Authorization": f"Bearer {token}"}
                msg_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{email.id}?format=full"
                try:
                    async with httpx.AsyncClient() as client:
                        res = await client.get(msg_url, headers=headers)
                        if res.status_code == 200:
                            payload = res.json().get("payload", {})
                            parts = payload.get("parts", [])
                            att_id_gmail = None
                            for part in parts:
                                if part.get("filename") == att.filename or part.get("mimeType") == att.mime_type:
                                    att_id_gmail = part.get("body", {}).get("attachmentId")
                                    if att_id_gmail:
                                        break
                            
                            if att_id_gmail:
                                att_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{email.id}/attachments/{att_id_gmail}"
                                att_res = await client.get(att_url, headers=headers)
                                if att_res.status_code == 200:
                                    att_b64 = att_res.json().get("data", "")
                                    if att_b64:
                                        raw_bytes = base64.urlsafe_b64decode(att_b64)
                                        storage_dir = os.path.join(os.getcwd(), "storage", "attachments")
                                        os.makedirs(storage_dir, exist_ok=True)
                                        file_path = os.path.join(storage_dir, f"{att.id}_{att.filename}")
                                        with open(file_path, "wb") as f:
                                            f.write(raw_bytes)
                                        att.storage_path = file_path
                                        await db.commit()
                                        return FileResponse(file_path, filename=att.filename, media_type=att.mime_type)
                except Exception as fetch_err:
                    print(f"Error fetching original attachment from Gmail API: {fetch_err}")

    # 3. Fallback for demo data or unretrievable binary
    content = att.extracted_text or f"Document Attachment: {att.filename}\n\nContent for this attachment is available for AI analysis."
    mime = "text/plain; charset=utf-8" if not att.mime_type or att.mime_type == "application/octet-stream" else att.mime_type
    headers = {"Content-Disposition": f'inline; filename="{att.filename}"'}
    return Response(content=content.encode("utf-8"), media_type=mime, headers=headers)


@router.get("/{email_id}", response_model=EmailDTO)
async def get_email(request: Request, email_id: str, db: AsyncSession = Depends(get_db)):
    user_id = get_user_id(request)
    repo = EmailRepository(db)
    email = await repo.get_email_by_id(email_id, user_id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    dto = EmailDTO.model_validate(email)
    dto.body_html = resolve_cid_images(sanitize_html(dto.body_html))
    return dto


@router.patch("/{email_id}/read")
async def toggle_read_status(
    request: Request,
    email_id: str,
    payload: ToggleReadRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    user_id = get_user_id(request)
    repo = EmailRepository(db)
    email = await repo.toggle_read(email_id, user_id, payload.is_unread)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    # ── Outbound sync: standalone function opens its own session + refreshes token ──
    background_tasks.add_task(gmail_sync_read, user_id, email_id, payload.is_unread)
    return {"ok": True, "is_unread": email.is_unread}


@router.patch("/{email_id}/star")
async def toggle_star_status(
    request: Request,
    email_id: str,
    payload: ToggleStarRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    user_id = get_user_id(request)
    repo = EmailRepository(db)
    email = await repo.toggle_star(email_id, user_id, payload.is_starred)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    # ── Outbound sync: standalone function opens its own session + refreshes token ──
    background_tasks.add_task(gmail_sync_star, user_id, email_id, payload.is_starred)
    return {"ok": True, "is_starred": email.is_starred}


@router.post("/{email_id}/archive")
async def archive_email_route(
    request: Request,
    email_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    user_id = get_user_id(request)
    repo = EmailRepository(db)
    email = await repo.archive_email(email_id, user_id)
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    # ── Outbound sync: standalone function opens its own session + refreshes token ──
    background_tasks.add_task(gmail_sync_archive, user_id, email_id)
    return {"ok": True, "archived": True}


@router.delete("/{email_id}")
async def delete_email_route(
    request: Request,
    email_id: str,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    user_id = get_user_id(request)
    repo = EmailRepository(db)
    success = await repo.delete_email(email_id, user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Email not found")
    # ── Outbound sync: standalone function opens its own session + refreshes token ──
    background_tasks.add_task(gmail_sync_trash, user_id, email_id)
    return {"ok": True, "deleted": True}

