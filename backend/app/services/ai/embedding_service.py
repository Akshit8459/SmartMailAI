import math
import logging
import os
from typing import List

logger = logging.getLogger(__name__)


class EmbeddingService:
    """
    Semantic embedding service using NVIDIA NIM nemotron-3-embed-1b.
    Falls back to a deterministic hash-based embedding if the API is unavailable.
    """

    NVIDIA_MODEL = "nvidia/nemotron-3-embed-1b"
    NVIDIA_DIMENSION = 4096
    FALLBACK_DIMENSION = 384

    def __init__(self):
        self._api_key = os.getenv("NVIDIA_API_KEY", "")
        self._base_url = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
        self._client = None
        self._dimension = self.FALLBACK_DIMENSION

        if self._api_key and not self._api_key.startswith("nvapi-demo"):
            try:
                from openai import OpenAI
                self._client = OpenAI(
                    api_key=self._api_key,
                    base_url=self._base_url,
                    timeout=5.0,
                )
                self._dimension = self.NVIDIA_DIMENSION
                logger.info("EmbeddingService: using NVIDIA nemotron-3-embed-1b (%d-dim)", self._dimension)
            except ImportError:
                logger.warning("openai package not installed; falling back to hash-based embeddings")
        else:
            logger.warning("EmbeddingService: no valid NVIDIA_API_KEY found; using hash-based fallback")

    @property
    def dimension(self) -> int:
        return self._dimension

    def generate_embedding(self, text: str) -> List[float]:
        if not text:
            return [0.0] * self._dimension

        if self._client is not None:
            try:
                response = self._client.embeddings.create(
                    input=[text],
                    model=self.NVIDIA_MODEL,
                    encoding_format="float",
                    extra_body={"input_type": "query", "truncate": "END"},
                )
                return response.data[0].embedding
            except Exception as e:
                logger.error("NVIDIA embedding API error: %s — falling back to hash method", e)

        return self._hash_embed(text)

    def _hash_embed(self, text: str) -> List[float]:
        """Deterministic 384-dim fallback embedding (no API required)."""
        dim = self.FALLBACK_DIMENSION
        words = text.lower().split()
        vector = [0.0] * dim
        for word in words:
            h = hash(word)
            idx = abs(h) % dim
            vector[idx] += (h % 100) / 100.0
        norm = math.sqrt(sum(x * x for x in vector))
        if norm > 0:
            vector = [round(x / norm, 5) for x in vector]
        return vector

    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        dot = sum(a * b for a, b in zip(vec1, vec2))
        n1 = math.sqrt(sum(a * a for a in vec1))
        n2 = math.sqrt(sum(b * b for b in vec2))
        if n1 == 0 or n2 == 0:
            return 0.0
        return dot / (n1 * n2)


embedding_service = EmbeddingService()
