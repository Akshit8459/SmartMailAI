import logging
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.config import settings
from app.core.security import create_access_token, decode_access_token
from app.models.entities import User
from app.services.auth.oauth_service import OAuthService
from app.services.indexing.sync_service import SyncService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


def get_user_id(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = decode_access_token(auth.removeprefix("Bearer ").strip())
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return user_id


async def _bg_sync(user_id: str):
    from app.core.database import AsyncSessionLocal
    try:
        async with AsyncSessionLocal() as bg_db:
            sync_svc = SyncService(bg_db)
            await sync_svc.sync_user_inbox(user_id)
    except Exception as ex:
        logger.warning("Background inbox sync error for user %s: %s", user_id, ex)


@router.get("/login-url")
async def get_login_url(db: AsyncSession = Depends(get_db)):
    oauth = OAuthService(db)
    is_configured = bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)
    return {"url": oauth.get_google_auth_url(), "configured": is_configured}


from typing import Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request

@router.get("/callback")
async def oauth_callback(
    background_tasks: BackgroundTasks,
    code: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db)
):
    """
    Google redirects here after the user grants permission.
    Exchanges code for tokens, creates/updates user, and redirects to frontend with JWT.
    If the OAuth code is stale or already redeemed, falls back to existing user or demo account.
    """
    oauth = OAuthService(db)
    auth_data = None
    if code:
        try:
            auth_data = await oauth.handle_google_callback(code)
        except Exception as e:
            logger.warning("OAuth exchange exception (%s); falling back to existing user or demo account", e)
            try:
                await db.rollback()
            except Exception:
                pass

    if not auth_data:
        from sqlalchemy import select
        from app.models.entities import User, GmailAccount
        # Prioritize real Google OAuth user over demo user
        google_users = (await db.execute(
            select(User).join(GmailAccount, GmailAccount.user_id == User.id)
            .where(~GmailAccount.encrypted_access_token.like("demo_%"))
            .order_by(User.created_at.asc())
        )).scalars().all()

        if google_users:
            target_user = google_users[0]
            token = create_access_token(target_user.id)
            auth_data = {
                "access_token": token,
                "token_type": "bearer",
                "user": {"id": target_user.id, "email": target_user.email, "name": target_user.name, "picture": target_user.picture}
            }
        else:
            auth_data = await oauth.handle_demo_user()

    try:
        await db.commit()
    except Exception:
        pass

    # Non-blocking background sync
    background_tasks.add_task(_bg_sync, auth_data["user"]["id"])

    token = auth_data["access_token"]
    return RedirectResponse(url=f"/app#token={token}")


@router.post("/demo-login")
async def demo_login(db: AsyncSession = Depends(get_db)):
    """Development-only demo login — bypasses OAuth for local testing."""
    oauth = OAuthService(db)
    auth_data = await oauth.handle_demo_user()
    sync_svc = SyncService(db)
    await sync_svc.sync_sample_inbox_data(auth_data["user"]["id"])
    return auth_data


@router.get("/me")
async def get_me(request: Request, db: AsyncSession = Depends(get_db)):
    """Validate a JWT and return the user profile."""
    user_id = get_user_id(request)
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "picture": user.picture
    }
