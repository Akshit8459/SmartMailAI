import base64
import json
import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db, AsyncSessionLocal
from app.repositories.email_repository import EmailRepository
from app.services.indexing.sync_service import SyncService
from app.models.entities import GmailAccount, User
from sqlalchemy.future import select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

async def _bg_webhook_sync(email_address: str, history_id: Optional[str] = None):
    """Background worker triggered by Google Cloud Pub/Sub push notification."""
    try:
        async with AsyncSessionLocal() as session:
            # Find user linked to email address
            acc = (await session.execute(
                select(GmailAccount).where(GmailAccount.email_address == email_address)
            )).scalars().first()
            
            if not acc:
                # Try finding user by email directly
                user = (await session.execute(
                    select(User).where(User.email == email_address)
                )).scalars().first()
                if user:
                    acc = (await session.execute(
                        select(GmailAccount).where(GmailAccount.user_id == user.id)
                    )).scalars().first()

            if not acc:
                logger.info("Pub/Sub notification received for unlinked email: %s", email_address)
                return

            sync_svc = SyncService(session)
            await sync_svc.sync_user_inbox(acc.user_id, max_results=15)
            logger.info("Real-time Pub/Sub sync completed successfully for user %s (%s)", acc.user_id, email_address)
    except Exception as e:
        logger.error("Error in _bg_webhook_sync for %s: %s", email_address, e)


@router.post("/gmail")
async def gmail_pubsub_webhook(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Endpoint for Google Cloud Pub/Sub Push Notifications.
    Must return 200 OK immediately (< 200ms) to satisfy Google Pub/Sub SLA.
    """
    try:
        body = await request.json()
    except Exception:
        # Accept blank/invalid ping gracefully
        return {"ok": True, "status": "ping_received"}

    message = body.get("message", {})
    data_b64 = message.get("data", "")

    if data_b64:
        try:
            # Decode Pub/Sub notification payload: {"emailAddress": "...", "historyId": 12345}
            decoded_bytes = base64.b64decode(data_b64)
            payload = json.loads(decoded_bytes.decode("utf-8"))
            email_address = payload.get("emailAddress", "")
            history_id = payload.get("historyId")

            if email_address:
                logger.info("Google Pub/Sub notification for %s (historyId: %s)", email_address, history_id)
                background_tasks.add_task(_bg_webhook_sync, email_address, str(history_id) if history_id else None)
                return {"ok": True, "email": email_address, "history_id": history_id, "status": "queued"}
        except Exception as ex:
            logger.warning("Error parsing Pub/Sub message data: %s", ex)

    return {"ok": True, "status": "received"}


@router.post("/simulated-push")
async def simulated_push_notification(
    email_address: str,
    background_tasks: BackgroundTasks
):
    """Local simulation endpoint for testing real-time push events without Google Cloud console."""
    background_tasks.add_task(_bg_webhook_sync, email_address, None)
    return {"ok": True, "message": f"Simulated real-time push event queued for {email_address}"}
