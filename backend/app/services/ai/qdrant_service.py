import logging
from typing import List, Dict, Any, Optional
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)

class QdrantVectorService:
    """
    Qdrant Vector Database Integration Engine for SmartMail AI.
    Handles 4096-dim NVIDIA Nemotron embeddings, HNSW indexing,
    and metadata payload filtering with fallback handling.
    """

    def __init__(self):
        self.host = settings.QDRANT_HOST
        self.port = settings.QDRANT_PORT
        self.api_key = settings.QDRANT_API_KEY
        self.collection_name = settings.QDRANT_COLLECTION
        self.base_url = f"http://{self.host}:{self.port}"
        self.headers = {"Content-Type": "application/json"}
        if self.api_key:
            self.headers["api-key"] = self.api_key

    async def is_available(self) -> bool:
        """Checks if Qdrant instance is live and reachable."""
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get(f"{self.base_url}/healthz", headers=self.headers)
                return res.status_code == 200
        except Exception:
            return False

    async def ensure_collection(self, vector_size: int = 4096) -> bool:
        """Ensures Qdrant collection exists with HNSW Cosine vector index."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                # Check collection
                res = await client.get(f"{self.base_url}/collections/{self.collection_name}", headers=self.headers)
                if res.status_code == 200:
                    return True

                # Create collection
                payload = {
                    "vectors": {
                        "size": vector_size,
                        "distance": "Cosine"
                    },
                    "hnsw_config": {
                        "m": 16,
                        "ef_construct": 100
                    }
                }
                put_res = await client.put(f"{self.base_url}/collections/{self.collection_name}", json=payload, headers=self.headers)
                if put_res.status_code in (200, 201):
                    logger.info("Qdrant collection '%s' created successfully.", self.collection_name)
                    return True
        except Exception as ex:
            logger.warning("Qdrant collection creation warning: %s", ex)
        return False

    async def upsert_chunks(self, points: List[Dict[str, Any]]) -> bool:
        """
        Upserts chunk vectors and payload metadata into Qdrant.
        point = {"id": "...", "vector": [...4096-dim...], "payload": {"user_id": "...", "email_id": "...", "content": "..."}}
        """
        if not points:
            return True
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                url = f"{self.base_url}/collections/{self.collection_name}/points"
                payload = {"points": points}
                res = await client.put(url, json=payload, headers=self.headers)
                return res.status_code in (200, 201)
        except Exception as ex:
            logger.warning("Error upserting vectors to Qdrant: %s", ex)
            return False

    async def search_vectors(
        self,
        query_vector: List[float],
        user_id: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Searches top-k vector matches for a user in Qdrant with payload filtering.
        """
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                url = f"{self.base_url}/collections/{self.collection_name}/points/search"
                payload = {
                    "vector": query_vector,
                    "limit": limit,
                    "with_payload": True,
                    "filter": {
                        "must": [
                            {"key": "user_id", "match": {"value": user_id}}
                        ]
                    }
                }
                res = await client.post(url, json=payload, headers=self.headers)
                if res.status_code == 200:
                    results = res.json().get("result", [])
                    return [
                        {
                            "score": item.get("score", 0.0),
                            "email_id": item.get("payload", {}).get("email_id"),
                            "content": item.get("payload", {}).get("content"),
                            "metadata": item.get("payload", {})
                        }
                        for item in results
                    ]
        except Exception as ex:
            logger.warning("Qdrant vector search warning: %s", ex)
        return []

# Singleton instance
qdrant_svc = QdrantVectorService()
