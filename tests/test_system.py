import unittest
import urllib.request
import json
import os
import sys
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '../.env'))

class TestFullSystem(unittest.TestCase):
    def test_litellm_gemini_routing(self):
        """Verify E2E routing to Gemini via LiteLLM Proxy using actual GEMINI_API_KEY"""
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            self.skipTest("GEMINI_API_KEY environment variable is not set. Skipping real model access test.")

        url = "http://localhost:4000/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": "Bearer sk-1234"
        }
        payload = {
            "model": "gemini-3.5-flash",
            "messages": [
                {"role": "user", "content": "Hello! Reply with one word."}
            ],
            "max_tokens": 200
        }

        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode('utf-8'),
                headers=headers,
                method='POST'
            )
            response = urllib.request.urlopen(req, timeout=20)
            self.assertEqual(response.status, 200)
            raw_response = response.read().decode('utf-8')
            print(f"\n[SYSTEM TEST] Raw Response: {raw_response}")
            data = json.loads(raw_response)
            self.assertIn("choices", data)
            content = data["choices"][0]["message"].get("content")
            print(f"\n[SYSTEM TEST] Gemini response content: {content}")
            self.assertIsNotNone(content, f"Content is None. Response was: {raw_response}")
            self.assertTrue(len(content) > 0)
        except Exception as e:
            self.fail(f"Failed to access Gemini via LiteLLM Proxy: {e}")

    def test_dify_web_access(self):
        """Verify access to Dify Web UI (Port 8080) and check if Dify is active"""
        url = "http://localhost:8080"
        try:
            response = urllib.request.urlopen(url, timeout=10)
            self.assertEqual(response.status, 200)
            html = response.read().decode('utf-8')
            self.assertTrue("dify" in html.lower() or "manifest" in html.lower())
            print("\n[SYSTEM TEST] Dify Web UI access verified.")
        except Exception as e:
            self.fail(f"Failed to access Dify Web UI: {e}")

if __name__ == '__main__':
    unittest.main()
