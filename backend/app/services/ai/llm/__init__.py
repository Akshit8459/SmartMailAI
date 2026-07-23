from app.core.config import settings
from app.services.ai.llm.base import AbstractLLMClient
from app.services.ai.llm.nvidia import NvidiaNIMClient
from app.services.ai.llm.openai_client import OpenAIClient
from app.services.ai.llm.ollama_client import OllamaClient

def get_llm_client() -> AbstractLLMClient:
    provider = settings.LLM_PROVIDER.lower().strip()
    if provider == "openai":
        return OpenAIClient()
    elif provider == "ollama":
        return OllamaClient()
    else:
        # Default to NVIDIA NIM free API
        return NvidiaNIMClient()
