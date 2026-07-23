from pydantic import BaseModel
from typing import List, Optional, Any, Dict
from datetime import datetime
from typing import Literal

class UserDTO(BaseModel):
    id: str
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None

    class Config:
        from_attributes = True

class AttachmentDTO(BaseModel):
    id: str
    filename: str
    mime_type: str
    file_size: int
    storage_path: Optional[str] = None
    extracted_text: Optional[str] = None

    class Config:
        from_attributes = True

class EmailDTO(BaseModel):
    id: str
    thread_id: str
    sender_name: str
    sender_email: str
    recipient_list: str
    subject: str
    snippet: str
    body_html: str
    body_text: str
    received_at: datetime
    is_unread: bool
    is_starred: bool
    is_important: bool
    labels: List[str] = []
    attachments: List[AttachmentDTO] = []
    match_type: Optional[str] = None
    match_snippet: Optional[str] = None
    relevance_score: Optional[int] = None

    class Config:
        from_attributes = True

class ThreadDTO(BaseModel):
    id: str
    subject: str
    snippet: str
    last_message_at: datetime
    unread_count: int
    has_attachments: bool
    emails: List[EmailDTO] = []

    class Config:
        from_attributes = True

class ComposeEmailRequest(BaseModel):
    to: List[str]
    cc: Optional[List[str]] = []
    bcc: Optional[List[str]] = []
    subject: str
    body_html: str
    thread_id: Optional[str] = None

class RAGQueryRequest(BaseModel):
    session_id: Optional[str] = None
    query: str

class RAGSourceDTO(BaseModel):
    email_id: str
    thread_id: str
    subject: str
    sender: str
    date: str
    snippet: str

class RAGQueryResponse(BaseModel):
    session_id: str
    answer: str
    sources: List[RAGSourceDTO] = []

class ToggleReadRequest(BaseModel):
    is_unread: bool

class ToggleStarRequest(BaseModel):
    is_starred: bool

class BulkActionRequest(BaseModel):
    email_ids: List[str]
    action: str  # 'mark_read', 'mark_unread', 'star', 'unstar', 'archive', 'delete', 'add_label', 'remove_label'
    label: Optional[str] = None

class LabelCreateRequest(BaseModel):
    name: str
    color: Optional[str] = "#6366f1"

class ReplyEmailRequest(BaseModel):
    email_id: str
    to: List[str]
    subject: str
    body_html: str
    action_type: str = "reply" # 'reply', 'reply_all', 'forward'

class DraftAutosaveRequest(BaseModel):
    draft_id: Optional[str] = None
    to: List[str] = []
    subject: str = ""
    body_html: str = ""


# ─── Phase 3 DTOs ─────────────────────────────────────────────────────────────

class SmartInboxEmailDTO(EmailDTO):
    """EmailDTO extended with AI-generated priority metadata."""
    priority_score: int = 0
    priority_label: Literal["HIGH", "MEDIUM", "LOW"] = "LOW"
    priority_reason: str = ""


class AttachmentQueryRequest(BaseModel):
    """Request body for asking a question about an attachment's content."""
    attachment_id: str
    question: str
    email_id: Optional[str] = None  # for context enrichment


class SearchSuggestionsRequest(BaseModel):
    """Request body for AI-powered search autocomplete."""
    partial_query: str
    limit: int = 5


class ThreadSummaryRequest(BaseModel):
    """Request body for streaming thread timeline summarization."""
    thread_id: str
