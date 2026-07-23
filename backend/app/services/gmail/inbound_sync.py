"""
Gmail Inbound Sync (Gmail → SmartMail)
Polls Gmail History API to detect changes and apply them to local DB.
"""
from datetime import datetime, timedelta
from typing import Optional
import httpx
import logging

logger = logging.getLogger(__name__)
GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


async def get_fresh_access_token(account, db) -> Optional[str]:
    """Return a valid access token, refreshing if expired."""
    from app.core.security import decrypt_token, encrypt_token
    from app.core.config import settings

    access_token = decrypt_token(account.encrypted_access_token)
    if not access_token or access_token.startswith("demo_"):
        return None

    if account.token_expiry and account.token_expiry <= datetime.utcnow() + timedelta(minutes=2):
        try:
            refresh_tok = decrypt_token(account.encrypted_refresh_token or "")
            async with httpx.AsyncClient(timeout=10.0) as hc:
                rr = await hc.post("https://oauth2.googleapis.com/token", data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_tok,
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                })
            if rr.status_code == 200:
                new_tok = rr.json().get("access_token", "")
                if new_tok:
                    account.encrypted_access_token = encrypt_token(new_tok)
                    account.token_expiry = datetime.utcnow() + timedelta(seconds=rr.json().get("expires_in", 3600))
                    await db.commit()
                    return new_tok
        except Exception as e:
            logger.warning("Token refresh error: %s", e)

    return access_token


async def poll_inbound_changes(user_id: str, db) -> dict:
    """
    Core Gmail → SmartMail inbound sync logic.
    Uses Gmail History API to detect label changes and new messages.
    Returns a summary dict: {labels_updated, new_messages, errors, note}.
    """
    from sqlalchemy.future import select as sa_select
    from sqlalchemy import not_
    from app.models.entities import Email, GmailAccount, SyncState, Thread

    changes = {"labels_updated": 0, "new_messages": 0, "errors": []}

    # ── 1. Get real GmailAccount ───────────────────────────────────────────────
    result = await db.execute(
        sa_select(GmailAccount)
        .where(GmailAccount.user_id == user_id)
        .where(not_(GmailAccount.encrypted_access_token.like("demo_%")))
    )
    account = result.scalars().first()
    if not account:
        return {**changes, "note": "demo_user"}

    access_token = await get_fresh_access_token(account, db)
    if not access_token:
        return {**changes, "note": "no_token"}

    hdrs = {"Authorization": f"Bearer {access_token}"}

    # ── 2. Load last historyId from SyncState ──────────────────────────────────
    ss_result = await db.execute(sa_select(SyncState).where(SyncState.user_id == user_id))
    sync_state = ss_result.scalars().first()
    start_history_id = sync_state.last_history_id if (sync_state and sync_state.last_history_id) else None

    # ── 3. Get current historyId from Gmail profile ────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=10.0) as hc:
            p = await hc.get(f"{GMAIL_BASE}/profile", headers=hdrs)
        if p.status_code != 200:
            return {**changes, "error": f"profile:HTTP{p.status_code}"}
        current_history_id = p.json().get("historyId")
    except Exception as e:
        return {**changes, "error": str(e)}

    # ── 4. First poll — just record historyId ──────────────────────────────────
    if not start_history_id:
        if sync_state:
            sync_state.last_history_id = current_history_id
            sync_state.last_synced_at = datetime.utcnow()
        else:
            db.add(SyncState(user_id=user_id, last_history_id=current_history_id, status="IDLE"))
        await db.commit()
        return {**changes, "note": "first_poll"}

    # ── 5. No changes ──────────────────────────────────────────────────────────
    if start_history_id == current_history_id:
        return {**changes, "note": "no_changes"}

    # ── 6. Fetch Gmail History ─────────────────────────────────────────────────
    try:
        async with httpx.AsyncClient(timeout=15.0) as hc:
            h = await hc.get(
                f"{GMAIL_BASE}/history",
                params={
                    "startHistoryId": start_history_id,
                    "historyTypes": ["labelAdded", "labelRemoved", "messageAdded"],
                },
                headers=hdrs,
            )
    except Exception as e:
        return {**changes, "error": str(e)}

    if h.status_code == 404:
        # historyId too old: full label resync
        await _full_label_resync(user_id, hdrs, db, changes)
    elif h.status_code == 200:
        for item in h.json().get("history", []):
            await _apply_labels_added(item.get("labelsAdded", []), user_id, db, changes)
            await _apply_labels_removed(item.get("labelsRemoved", []), user_id, db, changes)
            await _apply_new_messages(item.get("messagesAdded", []), user_id, hdrs, db, changes)
        try:
            await db.commit()
        except Exception:
            await db.rollback()
    else:
        changes["errors"].append(f"history:HTTP{h.status_code}")

    # ── 7. Persist updated historyId ───────────────────────────────────────────
    if sync_state:
        sync_state.last_history_id = current_history_id
        sync_state.last_synced_at = datetime.utcnow()
    else:
        db.add(SyncState(user_id=user_id, last_history_id=current_history_id, status="IDLE"))
    try:
        await db.commit()
    except Exception:
        pass

    return {**changes, "historyId": current_history_id}


# ── Private helpers ────────────────────────────────────────────────────────────

async def _apply_labels_added(events, user_id, db, changes):
    from app.models.entities import Email
    for ev in events:
        msg_id = ev.get("message", {}).get("id")
        added = ev.get("labelIds", [])
        if not msg_id:
            continue
        email = await db.get(Email, msg_id)
        if not email or email.user_id != user_id:
            continue
        changed = False
        if "UNREAD" in added and not email.is_unread:
            email.is_unread = True
            changed = True
        if "STARRED" in added and not email.is_starred:
            email.is_starred = True
            changed = True
        if changed:
            changes["labels_updated"] += 1


async def _apply_labels_removed(events, user_id, db, changes):
    from app.models.entities import Email
    for ev in events:
        msg_id = ev.get("message", {}).get("id")
        removed = ev.get("labelIds", [])
        if not msg_id:
            continue
        email = await db.get(Email, msg_id)
        if not email or email.user_id != user_id:
            continue
        changed = False
        if "UNREAD" in removed and email.is_unread:
            email.is_unread = False
            changed = True
        if "STARRED" in removed and email.is_starred:
            email.is_starred = False
            changed = True
        if "INBOX" in removed:
            lbs = list(email.labels or [])
            if "INBOX" in lbs:
                lbs.remove("INBOX")
            if "ARCHIVE" not in lbs:
                lbs.append("ARCHIVE")
            email.labels = lbs
            changed = True
        if changed:
            changes["labels_updated"] += 1


async def _apply_new_messages(events, user_id, hdrs, db, changes):
    from app.models.entities import Email, Thread
    for ev in events:
        msg_id = ev.get("message", {}).get("id")
        if not msg_id or await db.get(Email, msg_id):
            continue
        try:
            async with httpx.AsyncClient(timeout=15.0) as hc:
                r = await hc.get(f"{GMAIL_BASE}/messages/{msg_id}?format=full", headers=hdrs)
            if r.status_code != 200:
                continue
            from app.services.indexing.sync_service import SyncService
            svc = SyncService(db)
            parsed = svc._parse_gmail_message(r.json(), user_id)
            thread = await db.get(Thread, parsed["thread_id"])
            if not thread:
                thread = Thread(
                    id=parsed["thread_id"], user_id=user_id,
                    subject=parsed["subject"], snippet=parsed["snippet"],
                    last_message_at=parsed["received_at"],
                    unread_count=1 if parsed["is_unread"] else 0,
                )
                db.add(thread)
            db.add(Email(
                id=parsed["id"], thread_id=parsed["thread_id"], user_id=user_id,
                sender_name=parsed["sender_name"], sender_email=parsed["sender_email"],
                recipient_list=parsed["recipient_list"], subject=parsed["subject"],
                snippet=parsed["snippet"],
                body_html=parsed["body_html"] or f"<div><p>{parsed['body_text']}</p></div>",
                body_text=parsed["body_text"], received_at=parsed["received_at"],
                is_unread=parsed["is_unread"], is_starred=parsed["is_starred"],
                is_important=parsed["is_important"], labels=parsed["labels"],
            ))
            # Instantly index new message chunks for AI Assistant context
            from app.services.indexing.semantic_chunker import semantic_chunker
            from app.models.entities import EmailChunk
            date_str = parsed["received_at"].strftime("%Y-%m-%d") if parsed.get("received_at") else ""
            chunks_data = semantic_chunker.chunk_email(
                email_id=parsed["id"],
                thread_id=parsed["thread_id"],
                user_id=user_id,
                sender=parsed["sender_name"] or parsed["sender_email"],
                subject=parsed["subject"],
                date_str=date_str,
                body_text=parsed["body_text"] or parsed["snippet"] or ""
            )
            for c_data in chunks_data:
                db.add(EmailChunk(
                    email_id=c_data["email_id"],
                    thread_id=c_data["thread_id"],
                    user_id=c_data["user_id"],
                    chunk_index=c_data["chunk_index"],
                    content=c_data["content"],
                    chunk_metadata=c_data["chunk_metadata"],
                    embedding=c_data["embedding"]
                ))
            changes["new_messages"] += 1
        except Exception as ex:
            changes["errors"].append(f"new_msg:{msg_id}:{ex}")


async def _full_label_resync(user_id, hdrs, db, changes):
    """Full label resync when historyId is too stale."""
    from sqlalchemy.future import select as sa_select
    from app.models.entities import Email
    result = await db.execute(sa_select(Email).where(Email.user_id == user_id))
    emails = result.scalars().all()
    for email in emails:
        try:
            async with httpx.AsyncClient(timeout=8.0) as hc:
                r = await hc.get(f"{GMAIL_BASE}/messages/{email.id}?format=minimal", headers=hdrs)
            if r.status_code == 200:
                lids = r.json().get("labelIds", [])
                email.is_unread = "UNREAD" in lids
                email.is_starred = "STARRED" in lids
                email.is_important = "IMPORTANT" in lids
                changes["labels_updated"] += 1
        except Exception:
            pass
    try:
        await db.commit()
    except Exception:
        await db.rollback()
