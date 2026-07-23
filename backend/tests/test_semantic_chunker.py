import unittest
from app.services.indexing.semantic_chunker import semantic_chunker

class TestSemanticChunker(unittest.TestCase):
    def test_quoted_reply_stripping(self):
        raw_email = """Hi Team,

I'd like to confirm the project timeline for Q3.

On Mon, Jul 20, 2026 at 10:00 AM John Doe <john@example.com> wrote:
> Hi Alex,
> Can we review the timeline for Q3?
"""
        cleaned = semantic_chunker.clean_email_body(raw_email)
        self.assertIn("confirm the project timeline for Q3", cleaned)
        self.assertNotIn("On Mon, Jul 20", cleaned)

    def test_email_chunking_and_metadata(self):
        chunks = semantic_chunker.chunk_email(
            email_id="msg_test",
            thread_id="thread_test",
            user_id="user_test",
            sender="Microsoft",
            subject="Interview Invitation",
            date_str="2026-07-28",
            body_text="We invite you to interview for the Software Engineer position at Microsoft on July 28 at 10:00 AM."
        )
        self.assertTrue(len(chunks) > 0)
        self.assertEqual(chunks[0]["email_id"], "msg_test")
        self.assertEqual(chunks[0]["chunk_metadata"]["subject"], "Interview Invitation")
        self.assertEqual(len(chunks[0]["embedding"]), 384)

if __name__ == "__main__":
    unittest.main()
