from typing import AsyncGenerator
from app.services.ai.llm.base import AbstractLLMClient
from app.core.config import settings

try:
    import httpx
except ImportError:
    httpx = None

class OllamaClient(AbstractLLMClient):
    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL.rstrip('/')
        self.model = settings.OLLAMA_MODEL

    async def generate_text(self, prompt: str, system_prompt: str = "You are a helpful AI email assistant.") -> str:
        if not httpx:
            return f"Ollama Local Response for '{prompt}'"
        payload = {
            "model": self.model,
            "prompt": f"System: {system_prompt}\nUser: {prompt}\nAssistant:",
            "stream": False
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            try:
                response = await client.post(f"{self.base_url}/api/generate", json=payload)
                if response.status_code == 200:
                    return response.json().get("response", "")
                return f"[Ollama Error: {response.text}]"
            except Exception as e:
                return f"Ollama Local Response for '{prompt}'"

    async def generate_stream(self, prompt: str, system_prompt: str = "You are a helpful AI email assistant.") -> AsyncGenerator[str, None]:
        text = await self.generate_text(prompt, system_prompt)
        for word in text.split():
            yield word + " "
