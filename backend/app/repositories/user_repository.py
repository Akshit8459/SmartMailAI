from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.repositories.base import BaseRepository
from app.models.entities import User, GmailAccount, SyncState

class UserRepository(BaseRepository[User]):
    def __init__(self, session: AsyncSession):
        super().__init__(User, session)

    async def get_by_email(self, email: str) -> Optional[User]:
        stmt = select(User).where(User.email == email)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_gmail_account(self, user_id: str) -> Optional[GmailAccount]:
        stmt = select(GmailAccount).where(GmailAccount.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_sync_state(self, user_id: str) -> Optional[SyncState]:
        stmt = select(SyncState).where(SyncState.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalars().first()
