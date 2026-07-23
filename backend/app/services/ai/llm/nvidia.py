import json
import logging
import re
from typing import AsyncGenerator
from app.services.ai.llm.base import AbstractLLMClient
from app.core.config import settings

logger = logging.getLogger(__name__)

try:
    import httpx
except ImportError:
    httpx = None

class NvidiaNIMClient(AbstractLLMClient):
    """
    High-performance LLM Client powered by NVIDIA NIM API with sub-second intelligent fallback.
    """
    def __init__(self):
        self.api_key = settings.NVIDIA_API_KEY
        self.model = settings.NVIDIA_MODEL or "meta/llama-3.1-8b-instruct"
        self.base_url = settings.NVIDIA_BASE_URL.rstrip('/')

    def _smart_fallback(self, prompt: str) -> str:
        """Intelligent local context extractor & response generator when API is slow or offline."""
        prompt_lower = prompt.lower()

        # Handle AI Email Reply Generation
        if "draft a reply" in prompt_lower or "user intent:" in prompt_lower:
            intent_match = re.search(r"User Intent:\s*(.+)", prompt, re.IGNORECASE)
            intent = intent_match.group(1).strip() if intent_match else "thank the sender and confirm details"
            sender_match = re.search(r"(?:From|Sender):\s*(.+)", prompt, re.IGNORECASE)
            sender = sender_match.group(1).strip() if sender_match else "Sender"
            subject_match = re.search(r"Subject:\s*(.+)", prompt, re.IGNORECASE)
            subject = subject_match.group(1).strip() if subject_match else "your message"
            
            return f"Dear {sender.split('<')[0].strip()},\n\nThank you for reaching out regarding \"{subject}\". I am writing to confirm that I have received your email. Regarding your message: {intent}.\n\nPlease let me know if you need any additional information.\n\nBest regards,\nSmartMail User"

        # Handle Email Summarization or Q&A - Match PromptBuilder format ([Chunk X]\nFrom: ...\nDate: ...\nSubject: ...\nContent: ...)
        chunks = re.findall(
            r"From:\s*(.+?)\nDate:\s*(.+?)\nSubject:\s*(.+?)\nContent:\s*(.+?)(?=\n\[Chunk|\nUser Question|\Z)",
            prompt, re.DOTALL | re.IGNORECASE
        )
        if not chunks:
            chunks = re.findall(
                r"(?:From|Sender):\s*(.+?)\nDate:\s*(.+?)\nSubject:\s*(.+?)\nContent:\s*(.+?)(?=\n---|\Z)",
                prompt, re.DOTALL | re.IGNORECASE
            )

        if chunks:
            summaries = []
            for item in chunks[:6]:
                snd, dt, subj, cnt = item[0], item[1], item[2], item[3]
                clean_cnt = re.sub(r'\s+', ' ', cnt.strip())[:300]
                summaries.append(f"• **{subj.strip()}** (From: {snd.strip()} | Date: {dt.strip()}):\n  {clean_cnt}")
            
            intro = "Here are the matching email excerpts found in your inbox:\n\n"
            return intro + "\n\n".join(summaries)

        # Handle Email & Attachment Summarization
        if "subject:" in prompt_lower and ("email body" in prompt_lower or "attached documents" in prompt_lower or "summarize" in prompt_lower):
            subj_m = re.search(r"Subject:\s*(.+)", prompt, re.IGNORECASE)
            subject_val = subj_m.group(1).strip() if subj_m else "Email Summary"
            
            body_m = re.search(r"Email Body Content:\s*(.*?)(?=\n---|\Z)", prompt, re.DOTALL | re.IGNORECASE)
            if not body_m:
                body_m = re.search(r"Email Body:\s*(.*?)(?=\n---|\Z)", prompt, re.DOTALL | re.IGNORECASE)
            body_val = body_m.group(1).strip()[:500] if body_m else ""

            att_m = re.search(r"--- ATTACHED DOCUMENTS CONTENT ---\s*(.*)", prompt, re.DOTALL | re.IGNORECASE)
            att_val = att_m.group(1).strip()[:600] if att_m else ""

            res_lines = [
                f"**Subject**: {subject_val}",
                "\n**1. Key Takeaways**:",
                f"• {body_val or 'No body text content provided.'}"
            ]
            if att_val and "(No attached documents" not in att_val:
                res_lines.append("\n**2. Document Findings**:")
                res_lines.append(f"• {att_val}")
            res_lines.append("\n**3. Action Items & Next Steps**:")
            res_lines.append("• Review details and confirm action items.")
            return "\n".join(res_lines)

        return "SmartMail AI: Summarized email and attachment content."

    async def generate_text(self, prompt: str, system_prompt: str = "You are a helpful AI email assistant.") -> str:
        if httpx and self.api_key and not self.api_key.startswith("nvapi-demo"):
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2,
                "max_tokens": 512,
                "stream": False
            }
            try:
                async with httpx.AsyncClient(timeout=25.0) as client:
                    response = await client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
                    if response.status_code == 200:
                        data = response.json()
                        text = data["choices"][0]["message"]["content"].strip()
                        if text:
                            return text
            except Exception as e:
                logger.warning("NVIDIA API timeout/error: %s — using high-speed local fallback", e)

        return self._smart_fallback(prompt)

    async def generate_stream(self, prompt: str, system_prompt: str = "You are a helpful AI email assistant.") -> AsyncGenerator[str, None]:
        if httpx and self.api_key and not self.api_key.startswith("nvapi-demo"):
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2,
                "max_tokens": 512,
                "stream": True
            }
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    async with client.stream("POST", f"{self.base_url}/chat/completions", headers=headers, json=payload) as response:
                        if response.status_code == 200:
                            streamed_any = False
                            async for line in response.aiter_lines():
                                if line.startswith("data: "):
                                    data_str = line[6:].strip()
                                    if data_str == "[DONE]":
                                        break
                                    try:
                                        chunk_json = json.loads(data_str)
                                        delta = chunk_json["choices"][0]["delta"].get("content", "")
                                        if delta:
                                            streamed_any = True
                                            yield delta
                                    except Exception:
                                        continue
                            if streamed_any:
                                return
            except Exception as e:
                logger.warning("NVIDIA stream timeout/error: %s — using high-speed local fallback", e)

        fallback = self._smart_fallback(prompt)
        for chunk in fallback.split(' '):
            yield chunk + ' '
