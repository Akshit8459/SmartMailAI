from typing import AsyncGenerator
from app.services.ai.llm.base import AbstractLLMClient
from app.core.config import settings

try:
    import httpx
except ImportError:
    httpx = None

class OpenAIClient(AbstractLLMClient):
    def __init__(self):
        self.api_key = settings.OPENAI_API_KEY
        self.model = settings.OPENAI_MODEL

    async def generate_text(self, prompt: str, system_prompt: str = "You are a helpful AI email assistant.") -> str:
        if not httpx:
            return f"OpenAI Fallback Response for '{prompt}'"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=payload)
                if response.status_code == 200:
                    return response.json()["choices"][0]["message"]["content"]
                return f"[OpenAI Error: {response.text}]"
            except Exception as e:
                return f"OpenAI Fallback Response for '{prompt}'"

    async def generate_stream(self, prompt: str, system_prompt: str = "You are a helpful AI email assistant.") -> AsyncGenerator[str, None]:
        text = await self.generate_text(prompt, system_prompt)
        for word in text.split():
            yield word + " "
