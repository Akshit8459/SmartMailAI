from abc import ABC, abstractmethod
from typing import AsyncGenerator, Dict, Any, List

class AbstractLLMClient(ABC):
    @abstractmethod
    async def generate_text(self, prompt: str, system_prompt: str = "You are a helpful AI email assistant.") -> str:
        """Generate a complete text response asynchronously."""
        pass

    @abstractmethod
    async def generate_stream(self, prompt: str, system_prompt: str = "You are a helpful AI email assistant.") -> AsyncGenerator[str, None]:
        """Stream generated text chunks asynchronously."""
        pass
