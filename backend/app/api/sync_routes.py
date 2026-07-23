from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.services.indexing.sync_service import SyncService

router = APIRouter(prefix="/sync", tags=["Synchronization & Webhooks"])

DEMO_USER_ID = "demo-user-id"

@router.post("/trigger")
async def trigger_sync(db: AsyncSession = Depends(get_db)):
    sync_svc = SyncService(db)
    synced_count = await sync_svc.sync_sample_inbox_data(DEMO_USER_ID)
    return {"status": "SUCCESS", "synced_emails": synced_count}

@router.post("/webhook")
async def google_pubsub_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Receives real-time Pub/Sub push notifications from Google Cloud for Gmail history changes."""
    body = await request.json()
    # Execute delta sync
    sync_svc = SyncService(db)
    await sync_svc.sync_sample_inbox_data(DEMO_USER_ID)
    return {"status": "ACK"}
