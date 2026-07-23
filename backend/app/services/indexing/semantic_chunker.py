import re
from typing import List, Dict, Any
from app.services.ai.embedding_service import embedding_service

class SemanticChunker:
    """Cleans email HTML/Text (stripping quoted replies & signatures) and creates vector-ready chunks."""
    
    RE_QUOTED_REPLY = re.compile(r'(On\s+.*?\s+wrote:|From:.*?Sent:|>.*$)', re.IGNORECASE | re.MULTILINE)
    RE_SIGNATURE = re.compile(r'(--\s*\n|Best regards,|Thanks,|Sincerely,).*$', re.IGNORECASE | re.DOTALL)

    def clean_email_body(self, raw_text: str) -> str:
        if not raw_text:
            return ""
        
        # 1. Strip quoted reply chains
        text = self.RE_QUOTED_REPLY.split(raw_text)[0]
        
        # 2. Strip standard signature blocks
        text = self.RE_SIGNATURE.split(text)[0]
        
        # 3. Clean extra whitespace
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        return "\n".join(lines)

    def _make_chunks(self, text: str, words_per_chunk: int = 80, overlap: int = 15) -> List[str]:
        """Split text into overlapping word-window chunks."""
        words = text.split()
        chunks: List[str] = []
        step = max(1, words_per_chunk - overlap)
        for i in range(0, len(words), step):
            chunk_words = words[i:i + words_per_chunk]
            if not chunk_words:
                break
            chunks.append(" ".join(chunk_words))
            if i + words_per_chunk >= len(words):
                break
        return chunks

    def chunk_email(self, email_id: str, thread_id: str, user_id: str, sender: str, subject: str, date_str: str, body_text: str, chunk_size: int = 500) -> List[Dict[str, Any]]:
        cleaned_body = self.clean_email_body(body_text)
        if not cleaned_body:
            cleaned_body = body_text or "Empty Email Content"

        words_per_chunk = max(50, chunk_size // 6)
        raw_chunks = self._make_chunks(cleaned_body, words_per_chunk=words_per_chunk, overlap=15)
        
        chunks: List[Dict[str, Any]] = []
        for chunk_str in raw_chunks:
            enriched_content = f"From: {sender}\nSubject: {subject}\nDate: {date_str}\n\n{chunk_str}"
            embedding = embedding_service.generate_embedding(enriched_content)
            chunks.append({
                "email_id": email_id,
                "thread_id": thread_id,
                "user_id": user_id,
                "chunk_index": len(chunks),
                "content": enriched_content,
                "chunk_metadata": {
                    "sender": sender,
                    "subject": subject,
                    "date": date_str,
                    "source_type": "email",
                },
                "embedding": embedding,
            })
        return chunks

    def chunk_attachment(
        self,
        email_id: str,
        thread_id: str,
        user_id: str,
        attachment_id: str,
        filename: str,
        extracted_text: str,
        subject: str = "",
        sender: str = "",
        date_str: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Chunk attachment extracted text into vector-ready dicts.
        Annotated with source_type='attachment' so retrievers can filter by type.
        """
        if not extracted_text or extracted_text.startswith("["):
            # Stub / error content — create a single metadata-only chunk
            content = f"Attachment: {filename}\nEmail Subject: {subject}\nFrom: {sender}\n\n{extracted_text}"
            embedding = embedding_service.generate_embedding(content)
            return [{
                "email_id": email_id,
                "thread_id": thread_id,
                "user_id": user_id,
                "chunk_index": 0,
                "content": content,
                "chunk_metadata": {
                    "attachment_id": attachment_id,
                    "filename": filename,
                    "subject": subject,
                    "sender": sender,
                    "date": date_str,
                    "source_type": "attachment",
                },
                "embedding": embedding,
            }]

        raw_chunks = self._make_chunks(extracted_text, words_per_chunk=100, overlap=20)
        chunks: List[Dict[str, Any]] = []
        for chunk_str in raw_chunks:
            enriched = (
                f"Attachment: {filename}\n"
                f"Email Subject: {subject}\n"
                f"From: {sender} on {date_str}\n\n"
                f"{chunk_str}"
            )
            embedding = embedding_service.generate_embedding(enriched)
            chunks.append({
                "email_id": email_id,
                "thread_id": thread_id,
                "user_id": user_id,
                "chunk_index": len(chunks),
                "content": enriched,
                "chunk_metadata": {
                    "attachment_id": attachment_id,
                    "filename": filename,
                    "subject": subject,
                    "sender": sender,
                    "date": date_str,
                    "source_type": "attachment",
                },
                "embedding": embedding,
            })
        return chunks

semantic_chunker = SemanticChunker()
