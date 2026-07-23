import unittest
import asyncio
from app.services.ai.llm import get_llm_client
from app.services.ai.llm.nvidia import NvidiaNIMClient
from app.services.ai.llm.base import AbstractLLMClient

class TestLLMProvider(unittest.TestCase):
    def test_llm_factory(self):
        client = get_llm_client()
        self.assertIsInstance(client, AbstractLLMClient)
        self.assertIsInstance(client, NvidiaNIMClient)

    def test_llm_text_generation(self):
        async def _test():
            client = get_llm_client()
            response = await client.generate_text("Test prompt", "System instruction")
            self.assertIsInstance(response, str)
            self.assertTrue(len(response) > 0)
        asyncio.run(_test())

if __name__ == "__main__":
    unittest.main()
