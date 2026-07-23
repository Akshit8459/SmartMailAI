"""
Gmail Outbound Sync Service
Handles bidirectional synchronisation — pushes local label mutations,
archive, star, read/unread, trash, and send actions back to the Gmail API.

Design notes
─────────────
• Every public function is a *standalone async function* (not a class method)
  so FastAPI BackgroundTasks can call them directly without holding a
  request-scoped SQLAlchemy session (which is already closed by the time
  background tasks run).
• Each function opens its OWN AsyncSessionLocal session, refreshes the
  access token if needed, calls Gmail, then closes the session.  This
  mirrors the pattern used by _bg_sync in auth_routes.py.
"""

import logging
import httpx
from datetime import datetime, timedelta
from typing import List, Optional

logger = logging.getLogger(__name__)

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _get_fresh_token(user_id: str) -> Optional[str]:
    """
    Open an independent DB session, load the GmailAccount, auto-refresh the
    access token if it has expired (or will expire in the next 5 minutes),
    and return a usable bearer token.

    Returns None for demo users or when credentials are unavailable.
    """
    from app.core.database import AsyncSessionLocal
    from app.core.security import decrypt_token, encrypt_token
    from app.core.config import settings
    from app.models.entities import GmailAccount
    from sqlalchemy.future import select
    from sqlalchemy import not_

    async with AsyncSessionLocal() as session:
        # Prefer real (non-demo) account for this user
        result = await session.execute(
            select(GmailAccount)
            .where(GmailAccount.user_id == user_id)
            .where(not_(GmailAccount.encrypted_access_token.like("demo_%")))
        )
        account: Optional[GmailAccount] = result.scalars().first()

        if not account:
            logger.debug("No real GmailAccount for user %s (demo user or missing)", user_id)
            return None

        access_token = decrypt_token(account.encrypted_access_token)

        # Double-check: skip demo tokens even if SQL filter missed them
        if not access_token or access_token.startswith("demo_"):
            logger.debug("Skipping outbound sync for demo user %s", user_id)
            return None

        # ── Auto-refresh if token expired or expiring within 5 minutes ──────
        needs_refresh = (
            account.token_expiry is None
            or account.token_expiry <= datetime.utcnow() + timedelta(minutes=5)
        )

        if needs_refresh:
            refresh_token = decrypt_token(account.encrypted_refresh_token or "")
            if not refresh_token or refresh_token.startswith("demo_"):
                logger.warning("No valid refresh token for user %s; using existing (possibly expired) token", user_id)
                return access_token

            if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
                logger.warning("GOOGLE_CLIENT_ID/SECRET not configured; cannot refresh token for user %s", user_id)
                return access_token

            try:
                logger.info("Refreshing Gmail access token for user %s (expired: %s)", user_id, account.token_expiry)
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(GOOGLE_TOKEN_URL, data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": settings.GOOGLE_CLIENT_ID,
                        "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    })

                if resp.status_code == 200:
                    data = resp.json()
                    new_access_token = data.get("access_token", "")
                    expires_in = data.get("expires_in", 3600)
                    if new_access_token:
                        account.encrypted_access_token = encrypt_token(new_access_token)
                        account.token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)
                        await session.commit()
                        logger.info("Gmail access token refreshed for user %s; new expiry: %s", user_id, account.token_expiry)
                        return new_access_token
                    else:
                        logger.warning("Token refresh response missing access_token for user %s: %s", user_id, data)
                else:
                    logger.warning(
                        "Token refresh HTTP %s for user %s: %s",
                        resp.status_code, user_id, resp.text[:400]
                    )
            except Exception as exc:
                logger.warning("Token refresh exception for user %s: %s", user_id, exc)

        return access_token


async def _post_modify(token: str, message_id: str,
                       add_labels: List[str], remove_labels: List[str]) -> bool:
    """Call Gmail messages.modify — add/remove label IDs on a single message."""
    url = f"{GMAIL_API_BASE}/messages/{message_id}/modify"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                json={"addLabelIds": add_labels, "removeLabelIds": remove_labels},
                headers={"Authorization": f"Bearer {token}"},
            )
        if resp.status_code == 200:
            logger.info("Gmail modify OK: %s add=%s remove=%s", message_id, add_labels, remove_labels)
            return True
        logger.warning(
            "Gmail modify non-200 for %s: HTTP %s — %s",
            message_id, resp.status_code, resp.text[:300]
        )
        return False
    except Exception as exc:
        logger.warning("Gmail modify exception for %s: %s", message_id, exc)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Public standalone outbound-sync functions
# (Called by BackgroundTasks — each opens its own DB session)
# ─────────────────────────────────────────────────────────────────────────────

async def sync_mark_read(user_id: str, message_id: str, is_unread: bool) -> None:
    """Push read/unread state to Gmail servers."""
    token = await _get_fresh_token(user_id)
    if not token:
        return
    if is_unread:
        await _post_modify(token, message_id, ["UNREAD"], [])
    else:
        await _post_modify(token, message_id, [], ["UNREAD"])


async def sync_star(user_id: str, message_id: str, is_starred: bool) -> None:
    """Add or remove the STARRED label on Gmail servers."""
    token = await _get_fresh_token(user_id)
    if not token:
        return
    if is_starred:
        await _post_modify(token, message_id, ["STARRED"], [])
    else:
        await _post_modify(token, message_id, [], ["STARRED"])


async def sync_archive(user_id: str, message_id: str) -> None:
    """Remove the INBOX label (archive) on Gmail servers."""
    token = await _get_fresh_token(user_id)
    if not token:
        return
    await _post_modify(token, message_id, [], ["INBOX"])


async def sync_trash(user_id: str, message_id: str) -> None:
    """Move a message to Trash on Gmail servers."""
    token = await _get_fresh_token(user_id)
    if not token:
        return
    url = f"{GMAIL_API_BASE}/messages/{message_id}/trash"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {token}"},
            )
        if resp.status_code == 200:
            logger.info("Gmail trash sync OK: %s", message_id)
        else:
            logger.warning(
                "Gmail trash non-200 for %s: HTTP %s — %s",
                message_id, resp.status_code, resp.text[:200]
            )
    except Exception as exc:
        logger.warning("Gmail trash exception for %s: %s", message_id, exc)


async def send_email(user_id: str, raw_message_b64: str) -> Optional[str]:
    """
    Send an email via Gmail API.
    raw_message_b64: RFC-2822 message encoded as URL-safe base64.
    Returns the new Gmail message ID on success, None on failure.
    """
    token = await _get_fresh_token(user_id)
    if not token:
        return None
    url = f"{GMAIL_API_BASE}/messages/send"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(
                url,
                json={"raw": raw_message_b64},
                headers={"Authorization": f"Bearer {token}"},
            )
        if resp.status_code == 200:
            msg_id = resp.json().get("id")
            logger.info("Gmail send OK: message_id=%s", msg_id)
            return msg_id
        logger.warning(
            "Gmail send non-200 for user %s: HTTP %s — %s",
            user_id, resp.status_code, resp.text[:300]
        )
        return None
    except Exception as exc:
        logger.warning("Gmail send exception for user %s: %s", user_id, exc)
        return None


async def sync_bulk_labels(user_id: str, message_ids: List[str],
                           add_labels: List[str], remove_labels: List[str]) -> int:
    """
    Batch label modification for multiple messages.
    Returns the number of successfully modified messages.
    """
    token = await _get_fresh_token(user_id)
    if not token:
        return 0
    success = 0
    for mid in message_ids:
        ok = await _post_modify(token, mid, add_labels, remove_labels)
        if ok:
            success += 1
    return success


# ─────────────────────────────────────────────────────────────────────────────
# Backward-compat class wrapper (kept so existing imports don't break)
# ─────────────────────────────────────────────────────────────────────────────

class GmailSyncService:
    """
    Thin class wrapper kept for backward compatibility.
    All methods delegate to the standalone module-level functions above
    which correctly open their own independent DB sessions.
    """

    def __init__(self, session=None):
        # session parameter accepted but intentionally ignored —
        # standalone functions manage their own sessions
        pass

    async def sync_mark_read(self, user_id: str, message_id: str, is_unread: bool):
        return await sync_mark_read(user_id, message_id, is_unread)

    async def sync_star(self, user_id: str, message_id: str, is_starred: bool):
        return await sync_star(user_id, message_id, is_starred)

    async def sync_archive(self, user_id: str, message_id: str):
        return await sync_archive(user_id, message_id)

    async def sync_trash(self, user_id: str, message_id: str):
        return await sync_trash(user_id, message_id)

    async def send_email(self, user_id: str, raw_message_b64: str):
        return await send_email(user_id, raw_message_b64)

    async def sync_bulk_labels(self, user_id: str, message_ids: List[str],
                               add_labels: List[str], remove_labels: List[str]):
        return await sync_bulk_labels(user_id, message_ids, add_labels, remove_labels)
