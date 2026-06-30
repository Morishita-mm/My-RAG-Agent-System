import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# パス追加
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(script_dir))
from scripts.mcp_server import generate_hyde_doc, search_dify_knowledge_internal

class TestHyDE(unittest.TestCase):
    @patch('requests.post')
    def test_generate_hyde_doc(self, mock_post):
        # generate_hyde_doc の正常応答パースを検証
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "これは仮想回答ドキュメントです。"
                    }
                }
            ]
        }
        mock_post.return_value = mock_response
        
        doc = generate_hyde_doc("テスト質問は何ですか？")
        self.assertEqual(doc, "これは仮想回答ドキュメントです。")

    @patch('scripts.mcp_server.generate_hyde_doc')
    @patch('requests.post')
    @patch('scripts.mcp_server.get_dify_config_for_current_project')
    def test_hyde_query_expansion(self, mock_config, mock_post, mock_generate_hyde):
        # HyDEが有効な場合にクエリが拡張されてリクエストされるかを検証
        mock_config.return_value = {
            "api_base": "http://localhost:8080/v1",
            "api_key": "dummy_key",
            "dataset_id": "dummy_dataset",
            "use_hyde": True # HyDE有効
        }
        
        mock_generate_hyde.return_value = "仮想的な回答コンテンツです。"
        
        # requests.post (Dify API呼び出し) の応答モック
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"records": []}
        mock_post.return_value = mock_response
        
        # Redisが無効な状態での検索実行
        with patch('scripts.mcp_server.redis_enabled', False):
            search_dify_knowledge_internal("質問テキスト", "test_project")
            
        # Dify Dataset retrieve API に渡された payload の query が拡張されていることをアサート
        called_args, called_kwargs = mock_post.call_args
        payload = called_kwargs.get("json", {})
        self.assertIn("質問テキスト", payload.get("query"))
        self.assertIn("仮想的な回答コンテンツです。", payload.get("query"))
