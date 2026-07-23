import base64
import logging
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.core.config import settings
from app.core.security import decrypt_token, encrypt_token
from app.repositories.email_repository import EmailRepository
from app.repositories.user_repository import UserRepository
from app.models.entities import User, Email, Thread, EmailChunk, SyncState, GmailAccount, Attachment
from app.services.indexing.semantic_chunker import semantic_chunker

logger = logging.getLogger(__name__)

GMAIL_MESSAGES_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"

class SyncService:
    """Synchronizes Gmail messages into relational database and vector chunk database."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.email_repo = EmailRepository(session)
        self.user_repo = UserRepository(session)

    async def sync_user_inbox(self, user_id: str) -> int:
        """
        Attempts to fetch real Gmail messages for the user.
        If Gmail account exists, purges demo sample emails and syncs real Gmail messages.
        """
        from sqlalchemy import delete
        account = await self.user_repo.get_gmail_account(user_id)
        if account and account.encrypted_access_token:
            access_token = decrypt_token(account.encrypted_access_token)
            if access_token and not access_token.startswith("demo_"):
                # Clean out pre-seeded demo sample emails & chunks for this real Gmail user
                try:
                    await self.session.execute(delete(EmailChunk).where(EmailChunk.user_id == user_id, EmailChunk.email_id.like(f"{user_id}_msg_%")))
                    await self.session.execute(delete(Email).where(Email.user_id == user_id, Email.id.like(f"{user_id}_msg_%")))
                    await self.session.execute(delete(Thread).where(Thread.user_id == user_id, Thread.id.like(f"{user_id}_thread_%")))
                    await self.session.commit()
                except Exception:
                    pass

                try:
                    count = await self._fetch_real_gmail_messages(user_id, access_token)
                    if count > 0:
                        logger.info("Successfully synced %d real Gmail messages for user %s", count, user_id)
                        return count
                except Exception as e:
                    logger.warning("Failed to fetch real Gmail messages for user %s: %s.", user_id, e)

        # Check if real Gmail messages exist in DB before defaulting to sample data
        from sqlalchemy import select
        existing_real = (await self.session.execute(
            select(Email).where(Email.user_id == user_id, ~Email.id.like(f"{user_id}_msg_%"))
        )).scalars().all()
        if existing_real:
            return len(existing_real)

        # Fallback to sample data only for demo user
        return await self.sync_sample_inbox_data(user_id)

    async def _fetch_real_gmail_messages(self, user_id: str, access_token: str) -> int:
        account = await self.user_repo.get_gmail_account(user_id)
        headers = {"Authorization": f"Bearer {access_token}"}
        async with httpx.AsyncClient(timeout=20.0) as client:
            # Check token validity and auto-refresh if expired
            test_resp = await client.get(f"{GMAIL_MESSAGES_URL}?q=in:inbox&maxResults=1", headers=headers)
            if test_resp.status_code == 401 and account and account.encrypted_refresh_token:
                refresh_tok = decrypt_token(account.encrypted_refresh_token)
                if refresh_tok and not refresh_tok.startswith("demo_"):
                    rf_resp = await client.post("https://oauth2.googleapis.com/token", data={
                        "client_id": settings.GOOGLE_CLIENT_ID,
                        "client_secret": settings.GOOGLE_CLIENT_SECRET,
                        "refresh_token": refresh_tok,
                        "grant_type": "refresh_token"
                    })
                    if rf_resp.status_code == 200:
                        new_access = rf_resp.json().get("access_token")
                        if new_access:
                            access_token = new_access
                            account.encrypted_access_token = encrypt_token(new_access)
                            account.token_expiry = datetime.utcnow() + timedelta(seconds=rf_resp.json().get("expires_in", 3600))
                            await self.session.commit()
                            headers = {"Authorization": f"Bearer {access_token}"}
                            logger.info("Successfully auto-refreshed Google access token for user %s", user_id)

            message_ids_to_fetch = []
            seen_ids = set()
            # Query Gmail by labelIds and fallback to ensure 100% of all emails populate
            query_urls = [
                f"{GMAIL_MESSAGES_URL}?labelIds=INBOX&maxResults=100",
                f"{GMAIL_MESSAGES_URL}?labelIds=SENT&maxResults=100",
                f"{GMAIL_MESSAGES_URL}?labelIds=STARRED&maxResults=100",
                f"{GMAIL_MESSAGES_URL}?labelIds=IMPORTANT&maxResults=100",
                f"{GMAIL_MESSAGES_URL}?maxResults=100"
            ]
            for base_url in query_urls:
                try:
                    page_token = None
                    while True:
                        url = base_url
                        if page_token:
                            url += f"&pageToken={page_token}"
                        resp = await client.get(url, headers=headers)
                        if resp.status_code == 200:
                            data = resp.json()
                            for item in data.get("messages", []):
                                m_id = item["id"]
                                if m_id not in seen_ids:
                                    seen_ids.add(m_id)
                                    message_ids_to_fetch.append(m_id)
                            page_token = data.get("nextPageToken")
                            if not page_token or len(message_ids_to_fetch) >= 500:
                                break
                        else:
                            logger.warning("Gmail URL '%s' status %d: %s", base_url, resp.status_code, resp.text)
                            break
                except Exception as e:
                    logger.warning("Error fetching Gmail URL '%s': %s", base_url, e)

            if not message_ids_to_fetch:
                return 0

            import asyncio
            count = 0
            processed_thread_ids = set()
            processed_email_ids = set()

            # Filter out existing DB emails first so fg_ids and bg_ids strictly contain UNSAVED emails
            unfetched_ids = []
            for m_id in message_ids_to_fetch:
                with self.session.no_autoflush:
                    existing = await self.session.get(Email, m_id)
                if not existing:
                    unfetched_ids.append(m_id)
                else:
                    count += 1
                    processed_email_ids.add(m_id)

            fg_ids = unfetched_ids[:20]
            bg_ids = unfetched_ids[20:]

            batch_size = 10
            for i in range(0, len(fg_ids), batch_size):
                batch_ids = fg_ids[i:i+batch_size]
                to_fetch_ids = []
                for msg_id in batch_ids:
                    with self.session.no_autoflush:
                        existing = await self.session.get(Email, msg_id)
                    if existing:
                        count += 1
                        processed_email_ids.add(msg_id)
                    else:
                        to_fetch_ids.append(msg_id)

                if not to_fetch_ids:
                    continue

                tasks = [client.get(f"{GMAIL_MESSAGES_URL}/{m_id}?format=full", headers=headers) for m_id in to_fetch_ids]
                responses = await asyncio.gather(*tasks, return_exceptions=True)

                for msg_resp in responses:
                    if isinstance(msg_resp, Exception) or msg_resp.status_code != 200:
                        continue

                    parsed = self._parse_gmail_message(msg_resp.json(), user_id)
                    msg_id = parsed["id"]
                    thread_id = parsed["thread_id"]

                    if msg_id in processed_email_ids:
                        continue

                    with self.session.no_autoflush:
                        existing_email = await self.session.get(Email, msg_id)
                    if existing_email:
                        processed_email_ids.add(msg_id)
                        continue

                    if thread_id not in processed_thread_ids:
                        with self.session.no_autoflush:
                            thread = await self.session.get(Thread, thread_id)
                        if not thread:
                            thread = Thread(
                                id=thread_id,
                                user_id=user_id,
                                subject=parsed["subject"],
                                snippet=parsed["snippet"],
                                last_message_at=parsed["received_at"],
                                unread_count=1 if parsed["is_unread"] else 0
                            )
                            self.session.add(thread)
                        processed_thread_ids.add(thread_id)

                    email_entity = Email(
                        id=parsed["id"],
                        thread_id=parsed["thread_id"],
                        user_id=user_id,
                        sender_name=parsed["sender_name"],
                        sender_email=parsed["sender_email"],
                        recipient_list=parsed["recipient_list"],
                        subject=parsed["subject"],
                        snippet=parsed["snippet"],
                        body_html=parsed["body_html"] or f"<div><p>{parsed['body_text']}</p></div>",
                        body_text=parsed["body_text"],
                        received_at=parsed["received_at"],
                        is_unread=parsed["is_unread"],
                        is_starred=parsed["is_starred"],
                        is_important=parsed["is_important"],
                        labels=parsed["labels"]
                    )
                    self.session.add(email_entity)
                    processed_email_ids.add(msg_id)
                    count += 1

                try:
                    await self.session.commit()
                except Exception as ex:
                    logger.warning("Foreground commit warning: %s", ex)
                    await self.session.rollback()

            # Trigger non-blocking background task for remaining 250+ emails
            if bg_ids:
                asyncio.create_task(run_background_gmail_sync(user_id, access_token, bg_ids))

            return count


async def run_background_gmail_sync(user_id: str, access_token: str, message_ids: list):
    """Background task that continuously syncs remaining 250+ Gmail emails in background batches."""
    if not message_ids:
        return
    try:
        from app.core.database import AsyncSessionLocal
        async with AsyncSessionLocal() as session:
            svc = SyncService(session)
            headers = {"Authorization": f"Bearer {access_token}"}
            async with httpx.AsyncClient(timeout=60.0) as client:
                processed_thread_ids = set()
                processed_email_ids = set()
                batch_size = 15
                for i in range(0, len(message_ids), batch_size):
                    batch_ids = message_ids[i:i+batch_size]
                    to_fetch = []
                    for msg_id in batch_ids:
                        with session.no_autoflush:
                            existing = await session.get(Email, msg_id)
                        if existing:
                            processed_email_ids.add(msg_id)
                        else:
                            to_fetch.append(msg_id)

                    if not to_fetch:
                        continue

                    tasks = [client.get(f"{GMAIL_MESSAGES_URL}/{m_id}?format=full", headers=headers) for m_id in to_fetch]
                    responses = await asyncio.gather(*tasks, return_exceptions=True)

                    for msg_resp in responses:
                        if isinstance(msg_resp, Exception) or msg_resp.status_code != 200:
                            continue

                        parsed = svc._parse_gmail_message(msg_resp.json(), user_id)
                        msg_id = parsed["id"]
                        thread_id = parsed["thread_id"]

                        if msg_id in processed_email_ids:
                            continue

                        with session.no_autoflush:
                            existing_email = await session.get(Email, msg_id)
                        if existing_email:
                            processed_email_ids.add(msg_id)
                            continue

                        if thread_id not in processed_thread_ids:
                            with session.no_autoflush:
                                thread = await session.get(Thread, thread_id)
                            if not thread:
                                thread = Thread(
                                    id=thread_id,
                                    user_id=user_id,
                                    subject=parsed["subject"],
                                    snippet=parsed["snippet"],
                                    last_message_at=parsed["received_at"],
                                    unread_count=1 if parsed["is_unread"] else 0
                                )
                                session.add(thread)
                            processed_thread_ids.add(thread_id)

                        email_entity = Email(
                            id=parsed["id"],
                            thread_id=parsed["thread_id"],
                            user_id=user_id,
                            sender_name=parsed["sender_name"],
                            sender_email=parsed["sender_email"],
                            recipient_list=parsed["recipient_list"],
                            subject=parsed["subject"],
                            snippet=parsed["snippet"],
                            body_html=parsed["body_html"] or f"<div><p>{parsed['body_text']}</p></div>",
                            body_text=parsed["body_text"],
                            received_at=parsed["received_at"],
                            is_unread=parsed["is_unread"],
                            is_starred=parsed["is_starred"],
                            is_important=parsed["is_important"],
                            labels=parsed["labels"]
                        )
                        session.add(email_entity)
                        processed_email_ids.add(msg_id)

                    try:
                        await session.commit()
                    except Exception as ex:
                        logger.warning("Background session commit warning: %s", ex)
                        await session.rollback()
    except Exception as ex:
        logger.warning("Background sync error for user %s: %s", user_id, ex)

    def _parse_gmail_message(self, msg_data: dict, user_id: str) -> dict:
        msg_id = msg_data.get("id")
        thread_id = msg_data.get("threadId", msg_id)
        snippet = msg_data.get("snippet", "")
        raw_labels = msg_data.get("labelIds", ["INBOX"])
        label_ids = [l.upper() for l in raw_labels]

        payload = msg_data.get("payload", {})
        headers_list = payload.get("headers", [])
        headers = {h["name"].lower(): h["value"] for h in headers_list}

        subject = headers.get("subject", "No Subject")
        sender = headers.get("from", "Unknown")
        if "<" in sender and ">" in sender:
            sender_name = sender.split("<")[0].strip().strip('"')
            sender_email = sender.split("<")[1].split(">")[0].strip()
        else:
            sender_name = sender
            sender_email = sender

        recipient_list = headers.get("to", "")
        date_header = headers.get("date")

        received_at = datetime.utcnow()
        if date_header:
            try:
                from email.utils import parsedate_to_datetime
                received_at = parsedate_to_datetime(date_header).replace(tzinfo=None)
            except Exception:
                pass

        body_text = ""
        body_html = ""
        attachments = []

        def extract_parts(parts):
            nonlocal body_text, body_html
            for part in parts:
                mime_type = part.get("mimeType", "")
                filename = part.get("filename", "")
                body = part.get("body", {})
                data = body.get("data", "")
                attachment_id = body.get("attachmentId", "")

                if filename or attachment_id:
                    attachments.append({
                        "filename": filename or "Attachment",
                        "mime_type": mime_type or "application/octet-stream",
                        "file_size": body.get("size", 0),
                        "attachment_id": attachment_id,
                        "data": data
                    })
                elif data:
                    try:
                        decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                        if mime_type == "text/plain" and not body_text:
                            body_text = decoded
                        elif mime_type == "text/html" and not body_html:
                            body_html = decoded
                    except Exception:
                        pass
                if "parts" in part:
                    extract_parts(part["parts"])

        if "parts" in payload:
            extract_parts(payload["parts"])
        else:
            data = payload.get("body", {}).get("data", "")
            if data:
                try:
                    decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
                    mime_type = payload.get("mimeType", "")
                    if mime_type == "text/html":
                        body_html = decoded
                    else:
                        body_text = decoded
                except Exception:
                    pass

        if not body_text and body_html:
            try:
                from bs4 import BeautifulSoup
                body_text = BeautifulSoup(body_html, "html.parser").get_text()
            except Exception:
                body_text = snippet

        return {
            "id": msg_id,
            "thread_id": thread_id,
            "sender_name": sender_name,
            "sender_email": sender_email,
            "recipient_list": recipient_list,
            "subject": subject,
            "snippet": snippet,
            "body_html": body_html,
            "body_text": body_text or snippet,
            "received_at": received_at,
            "is_unread": "UNREAD" in label_ids,
            "is_starred": "STARRED" in label_ids,
            "is_important": "IMPORTANT" in label_ids,
            "labels": label_ids,
            "attachments": attachments
        }

    async def sync_sample_inbox_data(self, user_id: str) -> int:
        """Populates high-quality sample emails scoped to user_id if inbox is empty."""
        user = await self.session.get(User, user_id)
        if not user:
            try:
                user = User(
                    id=user_id,
                    email="user@example.com",
                    name="User",
                )
                self.session.add(user)
                await self.session.flush()
            except Exception:
                await self.session.rollback()
                user = await self.session.get(User, user_id)

        now = datetime.utcnow()
        sample_emails_data = [
            {
                "id": f"{user_id}_msg_001",
                "thread_id": f"{user_id}_thread_101",
                "sender_name": "Microsoft Recruiting",
                "sender_email": "careers@microsoft.com",
                "recipient_list": user.email,
                "subject": "Interview Invitation: Senior Software Engineer at Microsoft",
                "snippet": "We are excited to invite you for a virtual interview round on July 28 at 10:00 AM PST...",
                "body_text": """Hi,

Thank you for applying for the Senior Software Engineer position at Microsoft.
We were very impressed with your application and would like to invite you for a 45-minute technical interview.

Interview Date: July 28, 2026
Time: 10:00 AM PST
Platform: Microsoft Teams

Please confirm your availability by replying to this email.

Best regards,
Microsoft Talent Acquisition""",
                "received_at": now - timedelta(hours=2),
                "is_unread": True,
                "is_starred": True,
                "is_important": True,
                "labels": ["INBOX", "IMPORTANT", "WORK"],
                "sample_attachments": [
                    {
                        "filename": "Microsoft_Interview_Preparation_Guide.pdf",
                        "mime_type": "application/pdf",
                        "file_size": 245760,
                        "extracted_text": """MICROSOFT SENIOR SOFTWARE ENGINEER VIRTUAL INTERVIEW GUIDE
Candidate: Developer
Date & Time: July 28, 2026 at 10:00 AM PST
Platform: Microsoft Teams

INTERVIEW ROUND BREAKDOWN:
1. System Design (45 mins): Distributed Caching, Microservices, Event-Driven Architecture with Kafka/PubSub.
2. Data Structures & Algorithms (45 mins): Graph Traversal, Tree Algorithms, Dynamic Programming.
3. Behavioral & Leadership Principles (30 mins): Collaboration, Ownership, System Failure Recovery.

PANELISTS:
- Sarah Jenkins (Principal Systems Architect)
- David Miller (Director of Engineering)

PREPARATION RESOURCES:
- Review Azure System Architecture whitepapers.
- Be prepared to walk through your hybrid RAG email client project."""
                    }
                ]
            },
            {
                "id": f"{user_id}_msg_002",
                "thread_id": f"{user_id}_thread_102",
                "sender_name": "Stripe Billing",
                "sender_email": "invoices@stripe.com",
                "recipient_list": user.email,
                "subject": "Receipt for Your NVIDIA NIM Developer Subscription (#INV-2026-0891)",
                "snippet": "Your payment of $49.00 to NVIDIA Developer Services was successful...",
                "body_text": """Hello,

This is a receipt for your recent purchase.

Amount Paid: $49.00 USD
Description: NVIDIA NIM Microservices Pro Tier (Monthly)
Payment Method: Visa ending in 4242
Invoice ID: INV-2026-0891

View your full tax invoice and usage history on your Stripe billing portal.

Thank you,
Stripe Billing Team""",
                "received_at": now - timedelta(hours=8),
                "is_unread": True,
                "is_starred": False,
                "is_important": True,
                "labels": ["INBOX", "IMPORTANT", "INVOICES"],
                "sample_attachments": [
                    {
                        "filename": "Tax_Invoice_INV-2026-0891.pdf",
                        "mime_type": "application/pdf",
                        "file_size": 184320,
                        "extracted_text": """STRIPE BILLING TAX INVOICE
Invoice Number: INV-2026-0891
Date: July 22, 2026
Seller: NVIDIA Developer Services / Stripe Inc.
Billed To: user@example.com

LINE ITEMS:
1. NVIDIA NIM Microservices Pro Tier (Monthly License) - $49.00 USD
Subtotal: $49.00 USD
Tax Rate (0% VAT): $0.00 USD
Total Amount Paid: $49.00 USD

Payment Method: Visa Credit Card ending in 4242
Transaction ID: tx_8821049210
Status: Paid in Full"""
                    }
                ]
            },
            {
                "id": f"{user_id}_msg_003",
                "thread_id": f"{user_id}_thread_103",
                "sender_name": "Prof. Elena Rostova",
                "sender_email": "erostova@stanford.edu",
                "recipient_list": user.email,
                "subject": "Feedback on AI RAG Architecture Paper Draft",
                "snippet": "I reviewed your draft on Semantic Email Chunking with Vector Search. Great work!...",
                "body_text": """Dear Student,

I reviewed your paper draft on 'Semantic Email Chunking and Vector Search in Email Clients'.
Overall, your hybrid retrieval benchmarks with Llama 3.3 70B look very promising.

A few quick suggestions before camera-ready submission:
1. Elaborate on how you handle HTML content sanitization before embedding.
2. Add a comparison table between HNSW indexing and brute-force cosine similarity.

Let's discuss this during lab office hours tomorrow at 3 PM.

Best,
Prof. Elena Rostova""",
                "received_at": now - timedelta(days=1),
                "is_unread": True,
                "is_starred": True,
                "is_important": True,
                "labels": ["INBOX", "IMPORTANT", "ACADEMIC"],
                "sample_attachments": [
                    {
                        "filename": "RAG_Architecture_Paper_Draft_v2.docx",
                        "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        "file_size": 512000,
                        "extracted_text": """RESEARCH DRAFT: HYBRID RETRIEVAL & VECTOR CHUNKING FOR EMAIL CLIENTS
Author: SmartMail AI Research Team
Advisor: Prof. Elena Rostova (Stanford University)

ABSTRACT:
Personal email clients process large volumes of unstructured communication. We propose a hybrid retrieval architecture combining BM25 keyword matching and dense vector embeddings (nomic-embed-text) evaluated with NVIDIA NIM (Llama 3.3 70B).

EXPERIMENTAL BENCHMARKS:
- Dense Cosine Similarity Recall@5: 84.1%
- BM25 Lexical Search Recall@5: 71.8%
- Hybrid RRF (Reciprocal Rank Fusion) Recall@5: 95.4%
- Average Inference Latency: 142 ms per query

KEY FINDINGS & RECOMMENDATIONS:
HTML body sanitization and CID inline image resolution are critical preprocessing steps before chunking email text for vector embeddings."""
                    }
                ]
            },
            {
                "id": f"{user_id}_msg_004",
                "thread_id": f"{user_id}_thread_104",
                "sender_name": "Amazon Web Services",
                "sender_email": "no-reply@amazon.com",
                "recipient_list": user.email,
                "subject": "Order Confirmation: Your Amazon Tech Order #114-9821",
                "snippet": "Thank you for your order! Your delivery of 1x Wireless Mechanical Keyboard is scheduled...",
                "body_text": """Hi Customer,

Your order #114-9821 has been confirmed.

Item: Wireless Mechanical Keyboard (RGB, Hot-swappable)
Price: $89.99
Estimated Delivery: Friday, July 24, 2026

You can track your package anytime from your Amazon dashboard.

Thanks,
Amazon.com""",
                "received_at": now - timedelta(days=2),
                "is_unread": False,
                "is_starred": False,
                "is_important": False,
                "labels": ["INBOX", "PURCHASES"],
                "sample_attachments": [
                    {
                        "filename": "Amazon_Order_Summary_114-9821.pdf",
                        "mime_type": "application/pdf",
                        "file_size": 122880,
                        "extracted_text": """AMAZON.COM ORDER SUMMARY & SLIP
Order Number: 114-9821401
Order Date: July 20, 2026
Carrier: Amazon Logistics (Tracking: TBA982104921)

ITEM ORDERED:
1x Keychron K2 Wireless Mechanical Keyboard (Tactile Brown Switches, RGB Backlit)
Item Total: $89.99 USD
Shipping & Handling: $0.00 USD
Grand Total: $89.99 USD

SHIPPING ADDRESS:
Customer
123 Tech Campus Way, Suite 400"""
                    }
                ]
            },
            {
                "id": f"{user_id}_msg_005",
                "thread_id": f"{user_id}_thread_101",
                "sender_name": user.name or "Me",
                "sender_email": user.email,
                "recipient_list": "careers@microsoft.com",
                "subject": "Re: Interview Invitation: Senior Software Engineer at Microsoft",
                "snippet": "Thank you for the invitation! I confirm my availability for July 28 at 10:00 AM PST...",
                "body_text": f"Hi Microsoft Talent Acquisition Team,\n\nThank you for the invitation! I confirm my availability for the technical interview round on July 28 at 10:00 AM PST via Microsoft Teams.\n\nLooking forward to speaking with the team.\n\nBest regards,\n{user.name or 'Developer'}",
                "received_at": now - timedelta(hours=1),
                "is_unread": False,
                "is_starred": True,
                "is_important": True,
                "labels": ["SENT", "STARRED", "IMPORTANT"]
            }
        ]

        count = 0
        for item in sample_emails_data:
            thread = await self.session.get(Thread, item["thread_id"])
            if not thread:
                thread = Thread(
                    id=item["thread_id"],
                    user_id=user_id,
                    subject=item["subject"],
                    snippet=item["snippet"],
                    last_message_at=item["received_at"],
                    unread_count=1 if item["is_unread"] else 0
                )
                self.session.add(thread)

            existing_email = await self.session.get(Email, item["id"])
            if existing_email:
                count += 1
                continue

            email_entity = Email(
                id=item["id"],
                thread_id=item["thread_id"],
                user_id=user_id,
                sender_name=item["sender_name"],
                sender_email=item["sender_email"],
                recipient_list=item["recipient_list"],
                subject=item["subject"],
                snippet=item["snippet"],
                body_html=f"<div><p>{item['body_text'].replace(chr(10), '<br>')}</p></div>",
                body_text=item["body_text"],
                received_at=item["received_at"],
                is_unread=item["is_unread"],
                is_starred=item["is_starred"],
                is_important=item["is_important"],
                labels=item["labels"]
            )
            self.session.add(email_entity)

            date_str = item["received_at"].strftime("%Y-%m-%d")

            # Save attachments & chunk attachment text
            for att_info in item.get("sample_attachments", []):
                import uuid
                att_id = f"att_{uuid.uuid4().hex[:12]}"
                att_entity = Attachment(
                    id=att_id,
                    email_id=item["id"],
                    filename=att_info["filename"],
                    mime_type=att_info["mime_type"],
                    file_size=att_info["file_size"],
                    extracted_text=att_info["extracted_text"]
                )
                self.session.add(att_entity)

                # Vector chunk the attachment for AI RAG & Summarization
                att_chunks = semantic_chunker.chunk_attachment(
                    email_id=item["id"],
                    thread_id=item["thread_id"],
                    user_id=user_id,
                    attachment_id=att_id,
                    filename=att_info["filename"],
                    extracted_text=att_info["extracted_text"],
                    subject=item["subject"],
                    sender=item["sender_name"],
                    date_str=date_str
                )
                for c_data in att_chunks:
                    chunk_entity = EmailChunk(
                        email_id=c_data["email_id"],
                        thread_id=c_data["thread_id"],
                        user_id=c_data["user_id"],
                        chunk_index=c_data["chunk_index"],
                        content=c_data["content"],
                        chunk_metadata=c_data["chunk_metadata"],
                        embedding=c_data["embedding"]
                    )
                    self.session.add(chunk_entity)

            # Chunk email body
            chunks_data = semantic_chunker.chunk_email(
                email_id=item["id"],
                thread_id=item["thread_id"],
                user_id=user_id,
                sender=item["sender_name"],
                subject=item["subject"],
                date_str=date_str,
                body_text=item["body_text"]
            )

            for c_data in chunks_data:
                chunk_entity = EmailChunk(
                    email_id=c_data["email_id"],
                    thread_id=c_data["thread_id"],
                    user_id=c_data["user_id"],
                    chunk_index=c_data["chunk_index"],
                    content=c_data["content"],
                    chunk_metadata=c_data["chunk_metadata"],
                    embedding=c_data["embedding"]
                )
                self.session.add(chunk_entity)
            
            count += 1

        sync_state = await self.user_repo.get_sync_state(user_id)
        if not sync_state:
            sync_state = SyncState(user_id=user_id, last_history_id="1000921", status="IDLE")
            self.session.add(sync_state)
        else:
            sync_state.last_history_id = "1000921"
            sync_state.status = "IDLE"
            sync_state.last_synced_at = datetime.utcnow()

        await self.session.commit()
        return count
