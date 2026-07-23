import uuid
from datetime import datetime

try:
    from sqlalchemy import Column, String, Boolean, DateTime, Integer, Text, ForeignKey, JSON
    from sqlalchemy.orm import relationship
    from app.core.database import Base

    def generate_uuid():
        return str(uuid.uuid4())

    class User(Base):
        __tablename__ = "users"

        id = Column(String, primary_key=True, default=generate_uuid)
        email = Column(String, unique=True, index=True, nullable=False)
        name = Column(String, nullable=True)
        picture = Column(String, nullable=True)
        google_id = Column(String, unique=True, nullable=True)
        created_at = Column(DateTime, default=datetime.utcnow)

        accounts = relationship("GmailAccount", back_populates="user", cascade="all, delete-orphan")
        emails = relationship("Email", back_populates="user", cascade="all, delete-orphan")
        threads = relationship("Thread", back_populates="user", cascade="all, delete-orphan")
        chat_sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")

    class GmailAccount(Base):
        __tablename__ = "gmail_accounts"

        id = Column(String, primary_key=True, default=generate_uuid)
        user_id = Column(String, ForeignKey("users.id"), nullable=False)
        email_address = Column(String, nullable=False)
        encrypted_access_token = Column(Text, nullable=False)
        encrypted_refresh_token = Column(Text, nullable=False)
        token_expiry = Column(DateTime, nullable=True)
        created_at = Column(DateTime, default=datetime.utcnow)

        user = relationship("User", back_populates="accounts")

    class SyncState(Base):
        __tablename__ = "sync_state"

        id = Column(String, primary_key=True, default=generate_uuid)
        user_id = Column(String, ForeignKey("users.id"), unique=True, nullable=False)
        last_history_id = Column(String, nullable=True)
        watch_expiration = Column(DateTime, nullable=True)
        status = Column(String, default="IDLE")
        last_synced_at = Column(DateTime, default=datetime.utcnow)

    class Thread(Base):
        __tablename__ = "threads"

        id = Column(String, primary_key=True)
        user_id = Column(String, ForeignKey("users.id"), nullable=False)
        subject = Column(String, default="No Subject")
        snippet = Column(Text, default="")
        last_message_at = Column(DateTime, default=datetime.utcnow)
        unread_count = Column(Integer, default=0)
        has_attachments = Column(Boolean, default=False)

        user = relationship("User", back_populates="threads")
        emails = relationship("Email", back_populates="thread", cascade="all, delete-orphan")

    class Email(Base):
        __tablename__ = "emails"

        id = Column(String, primary_key=True)
        thread_id = Column(String, ForeignKey("threads.id"), index=True, nullable=False)
        user_id = Column(String, ForeignKey("users.id"), index=True, nullable=False)
        sender_name = Column(String, default="")
        sender_email = Column(String, index=True, nullable=False)
        recipient_list = Column(Text, default="")
        subject = Column(String, default="No Subject")
        snippet = Column(Text, default="")
        body_html = Column(Text, default="")
        body_text = Column(Text, default="")
        received_at = Column(DateTime, index=True, default=datetime.utcnow)
        is_unread = Column(Boolean, index=True, default=True)
        is_starred = Column(Boolean, index=True, default=False)
        is_important = Column(Boolean, index=True, default=False)
        labels = Column(JSON, default=list)

        user = relationship("User", back_populates="emails")
        thread = relationship("Thread", back_populates="emails")
        attachments = relationship("Attachment", back_populates="email", cascade="all, delete-orphan")
        chunks = relationship("EmailChunk", back_populates="email", cascade="all, delete-orphan")

    class Attachment(Base):
        __tablename__ = "attachments"

        id = Column(String, primary_key=True, default=generate_uuid)
        email_id = Column(String, ForeignKey("emails.id"), nullable=False)
        filename = Column(String, nullable=False)
        mime_type = Column(String, default="application/octet-stream")
        file_size = Column(Integer, default=0)
        storage_path = Column(Text, default="")
        extracted_text = Column(Text, default="")

        email = relationship("Email", back_populates="attachments")

    class EmailChunk(Base):
        __tablename__ = "email_chunks"

        id = Column(String, primary_key=True, default=generate_uuid)
        email_id = Column(String, ForeignKey("emails.id"), nullable=False)
        thread_id = Column(String, ForeignKey("threads.id"), nullable=False)
        user_id = Column(String, ForeignKey("users.id"), index=True, nullable=False)
        chunk_index = Column(Integer, default=0)
        content = Column(Text, nullable=False)
        chunk_metadata = Column(JSON, default=dict)
        embedding = Column(JSON, default=list)

        email = relationship("Email", back_populates="chunks")

    class ChatSession(Base):
        __tablename__ = "chat_sessions"

        id = Column(String, primary_key=True, default=generate_uuid)
        user_id = Column(String, ForeignKey("users.id"), nullable=False)
        title = Column(String, default="New Conversation")
        created_at = Column(DateTime, default=datetime.utcnow)

        user = relationship("User", back_populates="chat_sessions")
        messages = relationship("ChatMessage", back_populates="session", cascade="all, delete-orphan")

    class ChatMessage(Base):
        __tablename__ = "chat_messages"

        id = Column(String, primary_key=True, default=generate_uuid)
        session_id = Column(String, ForeignKey("chat_sessions.id"), nullable=False)
        role = Column(String, nullable=False)
        content = Column(Text, nullable=False)
        sources = Column(JSON, default=list)
        created_at = Column(DateTime, default=datetime.utcnow)

        session = relationship("ChatSession", back_populates="messages")

except ImportError:
    # Pure Python dataclass fallbacks
    from dataclasses import dataclass, field

    @dataclass
    class EmailChunk:
        id: str
        email_id: str
        thread_id: str
        user_id: str
        content: str
        chunk_index: int = 0
        chunk_metadata: dict = field(default_factory=dict)
        embedding: list = field(default_factory=list)
