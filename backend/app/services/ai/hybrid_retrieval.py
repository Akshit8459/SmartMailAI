from typing import List, Dict, Any
from app.services.ai.embedding_service import embedding_service
from app.models.entities import EmailChunk

class HybridRetriever:
    """Combines BM25 Sparse Keyword Search + Dense Vector Similarity using Reciprocal Rank Fusion (RRF)."""
    
    def retrieve(self, query: str, chunks: List[EmailChunk], top_k: int = 20) -> List[Dict[str, Any]]:
        if not chunks:
            return []

        query_words = set(query.lower().split())
        query_vec = embedding_service.generate_embedding(query)

        # 1. Compute Dense Vector Similarity Scores
        dense_results = []
        for chunk in chunks:
            chunk_vec = chunk.embedding or []
            sim = embedding_service.cosine_similarity(query_vec, chunk_vec)
            dense_results.append((chunk, sim))
        
        dense_results.sort(key=lambda x: x[1], reverse=True)

        # 2. Compute BM25 Keyword Overlap Scores (including subject & sender metadata)
        sparse_results = []
        for chunk in chunks:
            meta = chunk.chunk_metadata or {}
            subject = meta.get("subject", "")
            sender = meta.get("sender", "")
            searchable_text = f"{subject} {sender} {chunk.content}".lower()
            words = set(searchable_text.split())
            score = len(query_words.intersection(words)) / max(len(query_words), 1)
            sparse_results.append((chunk, score))

        sparse_results.sort(key=lambda x: x[1], reverse=True)

        # 3. Reciprocal Rank Fusion (RRF)
        rrf_scores: Dict[str, Dict[str, Any]] = {}
        k_const = 60

        for rank, (chunk, score) in enumerate(dense_results[:top_k], 1):
            cid = chunk.id
            if cid not in rrf_scores:
                rrf_scores[cid] = {"chunk": chunk, "rrf_score": 0.0, "dense_score": score, "sparse_score": 0.0}
            rrf_scores[cid]["rrf_score"] += 1.0 / (k_const + rank)

        for rank, (chunk, score) in enumerate(sparse_results[:top_k], 1):
            cid = chunk.id
            if cid not in rrf_scores:
                rrf_scores[cid] = {"chunk": chunk, "rrf_score": 0.0, "dense_score": 0.0, "sparse_score": score}
            rrf_scores[cid]["rrf_score"] += 1.0 / (k_const + rank)
            rrf_scores[cid]["sparse_score"] = score

        # Convert to list and format
        fused_candidates = []
        for cid, data in rrf_scores.items():
            chunk = data["chunk"]
            fused_candidates.append({
                "id": chunk.id,
                "email_id": chunk.email_id,
                "thread_id": chunk.thread_id,
                "content": chunk.content,
                "chunk_metadata": chunk.chunk_metadata or {},
                "rrf_score": round(data["rrf_score"], 6),
                "dense_score": round(data["dense_score"], 4),
                "sparse_score": round(data["sparse_score"], 4)
            })

        fused_candidates.sort(key=lambda x: x["rrf_score"], reverse=True)
        return fused_candidates[:top_k]

hybrid_retriever = HybridRetriever()
