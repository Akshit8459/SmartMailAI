import httpx
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.security import encrypt_token, decrypt_token, create_access_token
from app.repositories.user_repository import UserRepository
from app.models.entities import User, GmailAccount

logger = logging.getLogger(__name__)

GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


class OAuthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)

    def get_google_auth_url(self) -> str:
        scopes = [
            "https://www.googleapis.com/auth/userinfo.email",
            "https://www.googleapis.com/auth/userinfo.profile",
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/gmail.send"
        ]
        scope_str = "%20".join(scopes)
        return (
            f"https://accounts.google.com/o/oauth2/v2/auth?"
            f"client_id={settings.GOOGLE_CLIENT_ID}&"
            f"redirect_uri={settings.GOOGLE_REDIRECT_URI}&"
            f"response_type=code&"
            f"scope={scope_str}&"
            f"access_type=offline&"
            f"prompt=consent"
        )

    async def handle_google_callback(self, code: str) -> Dict[str, Any]:
        """Exchange authorization code for tokens, upsert user in DB."""
        async with httpx.AsyncClient() as client:
            # 1. Exchange code for tokens
            token_resp = await client.post(GOOGLE_TOKEN_URL, data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": settings.GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            })
            try:
                token_resp.raise_for_status()
            except httpx.HTTPStatusError as e:
                logger.error("Google token exchange status %d: %s", token_resp.status_code, token_resp.text)
                raise ValueError("Google session expired or authorization code was already used. Please try logging in again.")

            tokens = token_resp.json()
            access_token = tokens.get("access_token", "")
            refresh_token = tokens.get("refresh_token", "")
            expires_in = tokens.get("expires_in", 3600)

            # 2. Fetch Google profile
            info_resp = await client.get(
                GOOGLE_USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            info_resp.raise_for_status()
            info = info_resp.json()

        google_id = info.get("sub", "")
        email = info.get("email", "")
        name = info.get("name", "")
        picture = info.get("picture", "")

        # 3. Upsert user
        user = await self.user_repo.get_by_email(email)
        if not user:
            user = User(email=email, name=name, picture=picture, google_id=google_id)
            await self.user_repo.create(user)
        else:
            user.name = name
            user.picture = picture
            user.google_id = google_id
            await self.session.flush()

        # 4. Upsert GmailAccount
        from sqlalchemy import select
        from app.models.entities import GmailAccount
        existing_account = (await self.session.execute(
            select(GmailAccount).where(GmailAccount.user_id == user.id)
        )).scalars().first()

        token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)
        if not existing_account:
            account = GmailAccount(
                user_id=user.id,
                email_address=email,
                encrypted_access_token=encrypt_token(access_token),
                encrypted_refresh_token=encrypt_token(refresh_token),
                token_expiry=token_expiry,
            )
            self.session.add(account)
        else:
            existing_account.encrypted_access_token = encrypt_token(access_token)
            if refresh_token:
                existing_account.encrypted_refresh_token = encrypt_token(refresh_token)
            existing_account.token_expiry = token_expiry

        try:
            await self.session.commit()
        except Exception as ex:
            logger.warning("Error committing GmailAccount in callback: %s", ex)
            await self.session.rollback()

        jwt_token = create_access_token(user.id)
        return {
            "access_token": jwt_token,
            "token_type": "bearer",
            "user": {"id": user.id, "email": user.email, "name": user.name, "picture": user.picture}
        }

    async def handle_demo_user(self) -> Dict[str, Any]:
        """Creates or returns a default demo user for local testing without OAuth setup."""
        demo_email = "alex.developer@gmail.com"
        user = await self.user_repo.get_by_email(demo_email)
        if not user:
            user = User(
                email=demo_email,
                name="Alex Developer",
                picture="https://lh3.googleusercontent.com/a/default-user=s96-c",
                google_id="google-100921"
            )
            await self.user_repo.create(user)

            account = GmailAccount(
                user_id=user.id,
                email_address=demo_email,
                encrypted_access_token=encrypt_token("demo_access_token"),
                encrypted_refresh_token=encrypt_token("demo_refresh_token"),
                token_expiry=datetime.utcnow() + timedelta(days=30)
            )
            self.session.add(account)
            await self.session.commit()

        access_token = create_access_token(user.id)
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "picture": user.picture
            }
        }
