from typing import List, Dict, Any

class CrossEncoderReranker:
    """Reranks top candidate chunks using relevance scoring."""
    
    def rerank(self, query: str, candidates: List[Dict[str, Any]], top_k: int = 5) -> List[Dict[str, Any]]:
        if not candidates:
            return []
        
        query_words = set(query.lower().split())
        scored_candidates = []
        
        for cand in candidates:
            text = cand.get("content", "").lower()
            text_words = set(text.split())
            overlap = len(query_words.intersection(text_words))
            
            # Combine initial similarity score with word overlap score
            base_score = cand.get("rrf_score", cand.get("similarity", 0.5))
            final_score = base_score * 0.6 + (overlap / max(len(query_words), 1)) * 0.4
            
            item = dict(cand)
            item["rerank_score"] = round(final_score, 4)
            scored_candidates.append(item)
            
        scored_candidates.sort(key=lambda x: x["rerank_score"], reverse=True)
        return scored_candidates[:top_k]

reranker = CrossEncoderReranker()
