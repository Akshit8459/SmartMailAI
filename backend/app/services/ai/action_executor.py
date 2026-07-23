import json
import logging
import re
from typing import Dict, Any, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.email_repository import EmailRepository
from app.models.entities import Email
from sqlalchemy.future import select

logger = logging.getLogger(__name__)

class ActionExecutor:
    """
    AI Action Execution Engine for SmartMail AI.
    Executes structural inbox commands (archive, star, read/unread, delete)
    triggered by AI Chat or natural language intent.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = EmailRepository(session)

    async def execute_intent(self, user_id: str, prompt: str) -> Dict[str, Any]:
        """
        Parses intent from user prompt and executes matching inbox actions safely.
        Returns execution result summary.
        """
        prompt_lower = prompt.lower()
        
        # 1. Action: Archive emails
        if any(w in prompt_lower for w in ["archive", "file away"]):
            return await self._action_archive(user_id, prompt_lower)

        # 2. Action: Star / Flag emails
        if any(w in prompt_lower for w in ["star", "flag", "mark important"]):
            return await self._action_star(user_id, prompt_lower)

        # 3. Action: Mark as read
        if "mark as read" in prompt_lower or "read all" in prompt_lower:
            return await self._action_mark_read(user_id, prompt_lower)

        # 4. Action: Delete emails
        if "delete" in prompt_lower or "trash" in prompt_lower:
            return await self._action_delete(user_id, prompt_lower)

        return {"executed": False, "action": None, "message": "No actionable inbox command detected."}

    async def _action_archive(self, user_id: str, prompt: str) -> Dict[str, Any]:
        target_emails = await self._find_target_emails(user_id, prompt)
        if not target_emails:
            return {"executed": False, "action": "archive", "count": 0, "message": "No matching emails found to archive."}

        count = 0
        for email in target_emails:
            await self.repo.archive_email(email.id, user_id)
            count += 1

        return {
            "executed": True,
            "action": "archive",
            "count": count,
            "message": f"Successfully archived {count} email(s).",
            "email_ids": [e.id for e in target_emails]
        }

    async def _action_star(self, user_id: str, prompt: str) -> Dict[str, Any]:
        target_emails = await self._find_target_emails(user_id, prompt)
        if not target_emails:
            return {"executed": False, "action": "star", "count": 0, "message": "No matching emails found to star."}

        count = 0
        for email in target_emails:
            await self.repo.toggle_star(email.id, user_id, is_starred=True)
            count += 1

        return {
            "executed": True,
            "action": "star",
            "count": count,
            "message": f"Successfully starred {count} email(s).",
            "email_ids": [e.id for e in target_emails]
        }

    async def _action_mark_read(self, user_id: str, prompt: str) -> Dict[str, Any]:
        target_emails = await self._find_target_emails(user_id, prompt)
        if not target_emails:
            return {"executed": False, "action": "mark_read", "count": 0, "message": "No matching unread emails found."}

        count = 0
        for email in target_emails:
            await self.repo.toggle_read(email.id, user_id, is_unread=False)
            count += 1

        return {
            "executed": True,
            "action": "mark_read",
            "count": count,
            "message": f"Successfully marked {count} email(s) as read.",
            "email_ids": [e.id for e in target_emails]
        }

    async def _action_delete(self, user_id: str, prompt: str) -> Dict[str, Any]:
        target_emails = await self._find_target_emails(user_id, prompt)
        if not target_emails:
            return {"executed": False, "action": "delete", "count": 0, "message": "No matching emails found to delete."}

        count = 0
        for email in target_emails:
            await self.repo.delete_email(email.id, user_id)
            count += 1

        return {
            "executed": True,
            "action": "delete",
            "count": count,
            "message": f"Successfully deleted {count} email(s).",
            "email_ids": [e.id for e in target_emails]
        }

    async def _find_target_emails(self, user_id: str, prompt: str) -> List[Email]:
        """Finds emails matching natural language filters in prompt."""
        stmt = select(Email).where(Email.user_id == user_id)

        if "unread" in prompt:
            stmt = stmt.where(Email.is_unread == True)
        if "starred" in prompt or "important" in prompt:
            stmt = stmt.where(Email.is_starred == True)
        
        # Keyword filter extraction (e.g. "receipts", "invoices", "stripe", "github")
        keywords = []
        for kw in ["receipt", "invoice", "payment", "github", "stripe", "amazon", "newsletter", "promotions"]:
            if kw in prompt:
                keywords.append(kw)
        
        if keywords:
            from sqlalchemy import or_
            conditions = []
            for kw in keywords:
                conditions.append(Email.subject.ilike(f"%{kw}%"))
                conditions.append(Email.snippet.ilike(f"%{kw}%"))
                conditions.append(Email.sender_email.ilike(f"%{kw}%"))
            stmt = stmt.where(or_(*conditions))

        stmt = stmt.limit(20)
        res = await self.session.execute(stmt)
        return res.scalars().all()
