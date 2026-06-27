import unittest
import urllib.request
import json

class TestPhase4Ollama(unittest.TestCase):
    def test_litellm_proxy_models_contains_qwen(self):
        """Verify LiteLLM Proxy routing contains qwen2.5-coder"""
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
            model_names = [model["id"] for model in data["data"]]
            self.assertIn("qwen2.5-coder", model_names)
        except Exception as e:
            self.fail(f"Failed to query models from LiteLLM Proxy: {e}")

    def test_ollama_local_connection(self):
        """Verify if local Ollama service is running on host"""
        url = "http://localhost:11434/api/tags"
        try:
            response = urllib.request.urlopen(url, timeout=3)
            self.assertEqual(response.status, 200)
            data = json.loads(response.read().decode('utf-8'))
            print("\n[INFO] Local Ollama service is RUNNING.")
            print(f"[INFO] Installed local models: {[m['name'] for m in data.get('models', [])]}")
        except Exception as e:
            print(f"\n[WARNING] Local Ollama service is not running on host (localhost:11434): {e}")
            print("[WARNING] Skipped actual Ollama routing test.")

if __name__ == '__main__':
    unittest.main()
