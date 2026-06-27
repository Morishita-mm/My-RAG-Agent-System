import unittest
import urllib.request
import json

class TestPhase3RAG(unittest.TestCase):
    def test_dify_web_ui(self):
        """Verify Dify Web UI is accessible on port 8080"""
        url = "http://localhost:8080"
        try:
            response = urllib.request.urlopen(url, timeout=10)
            self.assertEqual(response.status, 200)
            html = response.read().decode('utf-8')
            self.assertTrue("html" in html.lower())
        except Exception as e:
            self.fail(f"Failed to connect to Dify Web UI: {e}")

    def test_litellm_proxy_models(self):
        """Verify LiteLLM Proxy is accessible and returns models list"""
        url = "http://localhost:4000/v1/models"
        try:
            req = urllib.request.Request(
                url,
                headers={"Authorization": "Bearer sk-1234"}
            )
            response = urllib.request.urlopen(req, timeout=10)
            self.assertEqual(response.status, 200)
            data = json.loads(response.read().decode('utf-8'))
            self.assertIn("data", data)
            # モデル名の存在を確認
            model_names = [model["id"] for model in data["data"]]
            self.assertIn("gemini-3.5-flash", model_names)
        except Exception as e:
            self.fail(f"Failed to query models from LiteLLM Proxy: {e}")

if __name__ == '__main__':
    unittest.main()
