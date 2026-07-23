import unittest
from app.services.ai.hybrid_retrieval import hybrid_retriever
from app.services.ai.reranker import reranker
from app.models.entities import EmailChunk

class TestRAGPipeline(unittest.TestCase):
    def test_hybrid_retrieval_and_reranking(self):
        chunk1 = EmailChunk(
            id="c1",
            email_id="e1",
            thread_id="t1",
            user_id="u1",
            content="From: Microsoft | Subject: Interview Invitation | Date: 2026-07-28\n\nYour technical interview is scheduled for July 28.",
            chunk_metadata={"subject": "Interview Invitation", "sender": "Microsoft"},
            embedding=[0.1] * 384
        )
        chunk2 = EmailChunk(
            id="c2",
            email_id="e2",
            thread_id="t2",
            user_id="u1",
            content="From: Google Cloud | Subject: Monthly Invoice | Date: 2026-07-20\n\nYour invoice #GC-982173 for $42.50 is now available.",
            chunk_metadata={"subject": "Monthly Invoice", "sender": "Google Cloud"},
            embedding=[0.05] * 384
        )

        candidates = hybrid_retriever.retrieve("When is my Microsoft interview?", [chunk1, chunk2], top_k=2)
        self.assertTrue(len(candidates) > 0)

        top_results = reranker.rerank("When is my Microsoft interview?", candidates, top_k=1)
        self.assertEqual(len(top_results), 1)
        self.assertEqual(top_results[0]["email_id"], "e1")

if __name__ == "__main__":
    unittest.main()
