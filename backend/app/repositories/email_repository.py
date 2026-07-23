from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import or_, and_, desc, String, cast, func
from sqlalchemy.orm import selectinload
from app.repositories.base import BaseRepository
from app.models.entities import Email, Thread, EmailChunk, User

class EmailRepository(BaseRepository[Email]):
    def __init__(self, session: AsyncSession):
        super().__init__(Email, session)

    async def get_user_emails(self, user_id: str, label: str = "INBOX", limit: int = 50, offset: int = 0) -> List[Email]:
        user = await self.session.get(User, user_id)
        user_email = user.email if user else ""

        stmt = select(Email).where(Email.user_id == user_id)
        lbl = label.upper()

        if lbl == "STARRED":
            stmt = stmt.where(Email.is_starred == True)
        elif lbl == "UNREAD":
            stmt = stmt.where(Email.is_unread == True)
        elif lbl == "IMPORTANT":
            stmt = stmt.where(or_(Email.is_important == True, cast(Email.labels, String).like("%IMPORTANT%")))
        elif lbl == "SENT":
            conditions = [cast(Email.labels, String).like("%SENT%")]
            if user_email:
                conditions.append(Email.sender_email == user_email)
            stmt = stmt.where(or_(*conditions))
        elif lbl == "WORK":
            stmt = stmt.where(or_(
                cast(Email.labels, String).like("%WORK%"),
                Email.subject.ilike("%work%"),
                Email.subject.ilike("%interview%"),
                Email.subject.ilike("%meeting%"),
                Email.subject.ilike("%career%"),
                Email.sender_email.ilike("%microsoft%"),
                Email.sender_email.ilike("%google%"),
                Email.sender_email.ilike("%github%")
            ))
        elif lbl == "INVOICES":
            stmt = stmt.where(or_(
                cast(Email.labels, String).like("%INVOICES%"),
                cast(Email.labels, String).like("%PURCHASES%"),
                Email.subject.ilike("%invoice%"),
                Email.subject.ilike("%receipt%"),
                Email.subject.ilike("%payment%"),
                Email.subject.ilike("%order%"),
                Email.subject.ilike("%subscription%"),
                Email.body_text.ilike("%invoice%"),
                Email.body_text.ilike("%receipt%")
            ))
        elif lbl == "ACADEMIC":
            stmt = stmt.where(or_(
                cast(Email.labels, String).like("%ACADEMIC%"),
                Email.subject.ilike("%academic%"),
                Email.subject.ilike("%paper%"),
                Email.subject.ilike("%research%"),
                Email.subject.ilike("%feedback%"),
                Email.sender_email.ilike("%.edu%")
            ))
        elif lbl == "INBOX":
            stmt = stmt.where(or_(
                cast(Email.labels, String).like("%INBOX%"),
                ~cast(Email.labels, String).like("%SENT%"),
                Email.labels == None
            ))
        elif lbl != "ALL":
            stmt = stmt.where(cast(Email.labels, String).like(f"%{lbl}%"))
        
        stmt = stmt.order_by(desc(Email.received_at)).offset(offset).limit(limit).options(selectinload(Email.attachments))
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_user_emails_count(self, user_id: str, label: str = "INBOX") -> int:
        user = await self.session.get(User, user_id)
        user_email = user.email if user else ""

        stmt = select(func.count(Email.id)).where(Email.user_id == user_id)
        lbl = label.upper()

        if lbl == "STARRED":
            stmt = stmt.where(Email.is_starred == True)
        elif lbl == "UNREAD":
            stmt = stmt.where(Email.is_unread == True)
        elif lbl == "IMPORTANT":
            stmt = stmt.where(or_(Email.is_important == True, cast(Email.labels, String).like("%IMPORTANT%")))
        elif lbl == "SENT":
            conditions = [cast(Email.labels, String).like("%SENT%")]
            if user_email:
                conditions.append(Email.sender_email == user_email)
            stmt = stmt.where(or_(*conditions))
        elif lbl == "WORK":
            stmt = stmt.where(or_(
                cast(Email.labels, String).like("%WORK%"),
                Email.subject.ilike("%work%"),
                Email.subject.ilike("%interview%"),
                Email.subject.ilike("%meeting%"),
                Email.subject.ilike("%career%"),
                Email.sender_email.ilike("%microsoft%"),
                Email.sender_email.ilike("%google%"),
                Email.sender_email.ilike("%github%")
            ))
        elif lbl == "INVOICES":
            stmt = stmt.where(or_(
                cast(Email.labels, String).like("%INVOICES%"),
                cast(Email.labels, String).like("%PURCHASES%"),
                Email.subject.ilike("%invoice%"),
                Email.subject.ilike("%receipt%"),
                Email.subject.ilike("%payment%"),
                Email.subject.ilike("%order%"),
                Email.subject.ilike("%subscription%"),
                Email.body_text.ilike("%invoice%"),
                Email.body_text.ilike("%receipt%")
            ))
        elif lbl == "ACADEMIC":
            stmt = stmt.where(or_(
                cast(Email.labels, String).like("%ACADEMIC%"),
                Email.subject.ilike("%academic%"),
                Email.subject.ilike("%paper%"),
                Email.subject.ilike("%research%"),
                Email.subject.ilike("%feedback%"),
                Email.sender_email.ilike("%.edu%")
            ))
        elif lbl == "INBOX":
            stmt = stmt.where(or_(
                cast(Email.labels, String).like("%INBOX%"),
                ~cast(Email.labels, String).like("%SENT%"),
                Email.labels == None
            ))
        elif lbl != "ALL":
            stmt = stmt.where(cast(Email.labels, String).like(f"%{lbl}%"))
        
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def get_email_by_id(self, email_id: str, user_id: str) -> Optional[Email]:
        stmt = select(Email).where(Email.id == email_id, Email.user_id == user_id).options(selectinload(Email.attachments))
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_thread_emails(self, thread_id: str) -> List[Email]:
        stmt = select(Email).where(Email.thread_id == thread_id).order_by(Email.received_at).options(selectinload(Email.attachments))
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def search_emails_metadata(self, user_id: str, query: str) -> List[Email]:
        q = f"%{query}%"
        stmt = select(Email).where(
            Email.user_id == user_id,
            or_(
                Email.subject.ilike(q),
                Email.sender_name.ilike(q),
                Email.sender_email.ilike(q),
                Email.snippet.ilike(q),
                Email.body_text.ilike(q)
            )
        ).order_by(desc(Email.received_at)).limit(30).options(selectinload(Email.attachments))
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_user_chunks(self, user_id: str) -> List[EmailChunk]:
        stmt = select(EmailChunk).where(EmailChunk.user_id == user_id)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_relevant_chunks(self, user_id: str, query: str = "", limit: int = 100) -> List[EmailChunk]:
        """
        Smart intent-aware SQL retrieval of chunks.
        Detects query intent (UNREAD, STARRED/IMPORTANT, RECENT INBOX OVERVIEW, or TARGETED KEYWORD SEARCH)
        and joins with actual Email entities to return accurate context chunks.
        """
        q_lower = query.lower()

        # Intent 1: Unread emails query
        if "unread" in q_lower:
            email_stmt = (
                select(Email.id)
                .where(Email.user_id == user_id, Email.is_unread == True)
                .order_by(desc(Email.received_at))
                .limit(50)
            )
            email_ids = (await self.session.execute(email_stmt)).scalars().all()
            if email_ids:
                chunk_stmt = select(EmailChunk).where(
                    EmailChunk.user_id == user_id,
                    EmailChunk.email_id.in_(email_ids)
                )
                chunks = (await self.session.execute(chunk_stmt)).scalars().all()
                if chunks:
                    # Sort chunks to strictly match the latest-to-oldest order of email_ids
                    email_order = {eid: idx for idx, eid in enumerate(email_ids)}
                    chunks.sort(key=lambda c: email_order.get(c.email_id, 9999))
                    return chunks

        # Intent 2: Starred / Important query
        if "starred" in q_lower or "important" in q_lower:
            email_stmt = (
                select(Email.id)
                .where(
                    Email.user_id == user_id,
                    or_(Email.is_starred == True, Email.is_important == True)
                )
                .order_by(desc(Email.received_at))
                .limit(50)
            )
            email_ids = (await self.session.execute(email_stmt)).scalars().all()
            if email_ids:
                chunk_stmt = select(EmailChunk).where(
                    EmailChunk.user_id == user_id,
                    EmailChunk.email_id.in_(email_ids)
                )
                chunks = (await self.session.execute(chunk_stmt)).scalars().all()
                if chunks:
                    email_order = {eid: idx for idx, eid in enumerate(email_ids)}
                    chunks.sort(key=lambda c: email_order.get(c.email_id, 9999))
                    return chunks

        # Intent 3: General inbox overview / recent emails / summaries
        is_overview = any(k in q_lower for k in ["recent", "latest", "inbox", "summarize", "overview", "all", "show", "list", "top", "whats new", "what's new"])

        words = [
            w.strip() for w in q_lower.split()
            if len(w.strip()) > 2 and w.strip() not in {
                "the", "and", "for", "with", "that", "this", "have", "from",
                "what", "show", "tell", "does", "were", "are", "any", "some",
                "emails", "email", "messages", "search", "find", "get", "summarize",
                "summary", "overview", "list", "recent", "latest", "inbox"
            }
        ]

        if not words or is_overview:
            email_stmt = (
                select(Email.id)
                .where(Email.user_id == user_id)
                .order_by(desc(Email.received_at))
                .limit(50)
            )
            email_ids = (await self.session.execute(email_stmt)).scalars().all()
            if email_ids:
                chunk_stmt = select(EmailChunk).where(
                    EmailChunk.user_id == user_id,
                    EmailChunk.email_id.in_(email_ids)
                )
                chunks = (await self.session.execute(chunk_stmt)).scalars().all()
                if chunks:
                    email_order = {eid: idx for idx, eid in enumerate(email_ids)}
                    chunks.sort(key=lambda c: email_order.get(c.email_id, 9999))
                    return chunks
                chunks = (await self.session.execute(chunk_stmt)).scalars().all()
                if chunks:
                    return chunks

        # Intent 4: Specific keyword search
        stmt = select(EmailChunk).where(EmailChunk.user_id == user_id)
        if words:
            kw_conditions = []
            for w in words[:5]:
                kw_conditions.append(EmailChunk.content.ilike(f"%{w}%"))
                kw_conditions.append(cast(EmailChunk.chunk_metadata, String).ilike(f"%{w}%"))
            stmt = stmt.where(or_(*kw_conditions))

        stmt = stmt.order_by(desc(EmailChunk.id)).limit(limit)
        result = await self.session.execute(stmt)
        chunks = result.scalars().all()

        if len(chunks) < 5:
            email_stmt = (
                select(Email.id)
                .where(Email.user_id == user_id)
                .order_by(desc(Email.received_at))
                .limit(25)
            )
            email_ids = (await self.session.execute(email_stmt)).scalars().all()
            if email_ids:
                chunk_stmt = select(EmailChunk).where(
                    EmailChunk.user_id == user_id,
                    EmailChunk.email_id.in_(email_ids)
                )
                chunks = (await self.session.execute(chunk_stmt)).scalars().all()

        return chunks

    async def toggle_read(self, email_id: str, user_id: str, is_unread: bool) -> Optional[Email]:
        email = await self.get_email_by_id(email_id, user_id)
        if email:
            email.is_unread = is_unread
            # Update labels JSON list if present
            labels = set(email.labels or [])
            if is_unread:
                labels.add("UNREAD")
            else:
                labels.discard("UNREAD")
            email.labels = list(labels)
            await self.session.commit()
            await self.session.refresh(email)
        return email

    async def toggle_star(self, email_id: str, user_id: str, is_starred: bool) -> Optional[Email]:
        email = await self.get_email_by_id(email_id, user_id)
        if email:
            email.is_starred = is_starred
            labels = set(email.labels or [])
            if is_starred:
                labels.add("STARRED")
            else:
                labels.discard("STARRED")
            email.labels = list(labels)
            await self.session.commit()
            await self.session.refresh(email)
        return email

    async def archive_email(self, email_id: str, user_id: str) -> Optional[Email]:
        email = await self.get_email_by_id(email_id, user_id)
        if email:
            labels = set(email.labels or [])
            labels.discard("INBOX")
            labels.add("ARCHIVED")
            email.labels = list(labels)
            await self.session.commit()
            await self.session.refresh(email)
        return email

    async def delete_email(self, email_id: str, user_id: str) -> bool:
        email = await self.get_email_by_id(email_id, user_id)
        if email:
            labels = set(email.labels or [])
            if "TRASH" in labels:
                await self.session.delete(email)
            else:
                labels.discard("INBOX")
                labels.add("TRASH")
                email.labels = list(labels)
            await self.session.commit()
            return True
        return False

    async def bulk_action(self, email_ids: List[str], user_id: str, action: str, label_name: Optional[str] = None) -> int:
        count = 0
        for email_id in email_ids:
            email = await self.get_email_by_id(email_id, user_id)
            if not email:
                continue
            count += 1
            labels = set(email.labels or [])

            if action == "mark_read":
                email.is_unread = False
                labels.discard("UNREAD")
            elif action == "mark_unread":
                email.is_unread = True
                labels.add("UNREAD")
            elif action == "star":
                email.is_starred = True
                labels.add("STARRED")
            elif action == "unstar":
                email.is_starred = False
                labels.discard("STARRED")
            elif action == "archive":
                labels.discard("INBOX")
                labels.add("ARCHIVED")
            elif action == "delete":
                if "TRASH" in labels:
                    await self.session.delete(email)
                else:
                    labels.discard("INBOX")
                    labels.add("TRASH")
            elif action == "add_label" and label_name:
                labels.add(label_name.upper())
            elif action == "remove_label" and label_name:
                labels.discard(label_name.upper())

            if action != "delete" or "TRASH" not in (email.labels or []):
                email.labels = list(labels)
        
        await self.session.commit()
        return count

    # ─── Attachment helpers ───────────────────────────────────────────────────

    async def get_attachment_by_id(self, attachment_id: str):
        """Retrieve a single Attachment record by its primary key."""
        from app.models.entities import Attachment
        return await self.session.get(Attachment, attachment_id)

    async def save_attachment_text(self, attachment_id: str, extracted_text: str) -> bool:
        """Persist extracted text back to the Attachment record."""
        from app.models.entities import Attachment
        attachment = await self.session.get(Attachment, attachment_id)
        if not attachment:
            return False
        attachment.extracted_text = extracted_text
        await self.session.commit()
        return True
