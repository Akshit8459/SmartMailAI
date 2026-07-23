"""
Prompt builder — isolated templates for RAG Q&A, Summarization, AI Reply, Thread Summary, and Smart Compose.
"""
from typing import List, Dict, Any


class PromptBuilder:
    """Isolated prompt templates — no business logic, pure string construction."""

    # ─── System prompts ───────────────────────────────────────────────────────

    SYSTEM_RAG_PROMPT = (
        "You are SmartMail AI, an intelligent, fast Gmail assistant.\n"
        "Answer the user's question directly, concisely, and accurately using ONLY the provided email context chunks.\n"
        "Rules:\n"
        "1. Be direct and concise — get straight to the answer without conversational filler.\n"
        "2. When summarizing emails (unread, recent, or overview), process them strictly from LATEST to OLDEST (newest date/time first down to oldest date/time). Summarize ALL distinct emails provided in the context.\n"
        "3. Use clean markdown formatting (bolding, bullet points).\n"
        "4. Explicitly cite the Email Subject, Sender, and Date when referencing information.\n"
        "5. If no relevant email is found in the context, explicitly state that no matching email was found."
    )

    SYSTEM_SUMMARY_PROMPT = (
        "You are SmartMail AI's Executive Summarizer.\n"
        "Provide a crisp, high-value summary of the email and attached documents.\n\n"
        "Output Structure:\n"
        "1. **Key Takeaways** — 2-3 concise bullet points capturing the main message.\n"
        "2. **Document Findings** — Important details, figures, or metrics from attachments (if any).\n"
        "3. **Action Items & Deadlines** — Clear bullet list of next steps, dates, or financial figures."
    )

    SYSTEM_THREAD_SUMMARY_PROMPT = (
        "You are SmartMail AI's Executive Thread Summarizer.\n"
        "Provide a fast, structured summary of the email thread.\n\n"
        "Output Structure:\n"
        "1. **Overview** — What this discussion is about.\n"
        "2. **Key Points** — Bullet list of core points per sender.\n"
        "3. **Action Items & Next Steps** — Tasks, commitments, or deadlines."
    )

    SYSTEM_REPLY_PROMPT = (
        "You are SmartMail AI, an intelligent, professional email assistant.\n"
        "Draft a clear, polite, and effective reply based on the original email context and user intent."
    )

    def build_rag_prompt(self, query: str, context_chunks: List[Dict[str, Any]], chat_history: List[Dict[str, str]] = None) -> str:
        ctx_str = ""
        for i, chunk in enumerate(context_chunks, 1):
            meta = chunk.get("chunk_metadata", {})
            sender = chunk.get("sender") or meta.get("sender") or "Unknown"
            subject = chunk.get("subject") or meta.get("subject") or "No Subject"
            date = chunk.get("date") or meta.get("date") or ""
            text = chunk.get("content") or chunk.get("text") or ""
            ctx_str += f"[Chunk {i}]\nFrom: {sender}\nDate: {date}\nSubject: {subject}\nContent: {text}\n\n"
        
        hist_str = ""
        if chat_history:
            for item in chat_history[-4:]:
                role = item.get("role", "user").capitalize()
                content = item.get("content", "")
                hist_str += f"{role}: {content}\n"
        
        history_block = f"Previous Conversation History:\n{hist_str}\n" if hist_str else ""
        return (
            f"{history_block}"
            f"Context Email Chunks:\n{ctx_str}\n"
            f"User Question: {query}\n"
        )

    def build_summary_prompt(self, email_text: str, subject: str = "", attachments_text: str = "") -> str:
        att_section = f"\n\n--- ATTACHED DOCUMENTS CONTENT ---\n{attachments_text}" if attachments_text else "\n\n(No attached documents for this email)"
        return (
            f"Subject: {subject}\n\n"
            f"Email Body Content:\n{email_text}\n"
            f"{att_section}\n\n"
            f"Provide a deep, context-grounded summary covering both the email content and all attached document details."
        )

    def build_reply_prompt(self, original_email: str, user_intent: str) -> str:
        return (
            f"Original Email:\n{original_email}\n\n"
            f"User Response Intent:\n{user_intent}\n\n"
            f"Draft a professional email response:"
        )

    def build_thread_summary_prompt(self, thread_messages: List[Dict[str, Any]]) -> str:
        """
        Build a chronological thread timeline prompt.
        thread_messages: list of dicts with keys: sender, date, subject, body_text, attachments_text
        """
        timeline = ""
        for i, msg in enumerate(thread_messages, 1):
            sender = msg.get("sender_name") or msg.get("sender_email", "Unknown")
            date = msg.get("date_str", "")
            body = (msg.get("body_text") or msg.get("snippet", ""))[:600]
            att_text = msg.get("attachments_text", "")
            att_block = f"\n  [Attached Document Content:\n  {att_text[:500]}]" if att_text else ""
            timeline += (
                f"--- Message {i} of {len(thread_messages)} ---\n"
                f"From: {sender}  |  Date: {date}\n"
                f"{body}{att_block}\n\n"
            )

        return (
            f"The following is an email thread with {len(thread_messages)} messages and attached documents. "
            f"Summarize the full conversation:\n\n"
            f"{timeline}"
            f"Provide a structured summary following the system instructions."
        )

    def build_search_suggestions_prompt(self, partial_query: str, email_subjects: List[str]) -> str:
        subject_sample = "\n".join(f"- {s}" for s in email_subjects[:10])
        return (
            f"User is searching their inbox. Partial query: \"{partial_query}\"\n\n"
            f"Recent email subjects in their inbox:\n{subject_sample}\n\n"
            f"Suggest 5 smart search completions. Return only a JSON array of 5 strings."
        )


prompt_builder = PromptBuilder()
