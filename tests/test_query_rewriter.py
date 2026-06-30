import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# パス追加
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(script_dir))
sys.path.append(os.path.join(os.path.dirname(script_dir), "scripts"))

from scripts.mcp_server import rewrite_query_with_history, search_dify_knowledge_internal

class TestQueryRewriter(unittest.TestCase):
    @patch('requests.post')
    def test_rewrite_query_no_history(self, mock_post):
        # 会話履歴が空の場合、クエリ書き換えを行わないことを検証
        result = rewrite_query_with_history("最新バージョンは何ですか？", [])
        self.assertEqual(result, "最新バージョンは何ですか？")
        mock_post.assert_not_called()

    @patch('requests.post')
    def test_rewrite_query_with_history(self, mock_post):
        # 会話履歴がある場合のクエリ書き換えのパースを検証
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [
                {
                    "message": {
                        "content": "Lissueの最新バージョンは何ですか？"
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        chat_history = [
            {"role": "user", "content": "Lissueについて教えてください。"},
            {"role": "assistant", "content": "Lissueはローカルタスク管理ツールです。"}
        ]
        
        result = rewrite_query_with_history("最新バージョンは何ですか？", chat_history)
        self.assertEqual(result, "Lissueの最新バージョンは何ですか？")
        
        # リクエスト送信内容のアサーション
        called_args, called_kwargs = mock_post.call_args
        payload = called_kwargs.get("json", {})
        messages = payload.get("messages", [])
        self.assertEqual(len(messages), 1)
        
        prompt = messages[0].get("content", "")
        self.assertIn("Lissueについて教えてください。", prompt)
        self.assertIn("最新バージョンは何ですか？", prompt)

    @patch('scripts.mcp_server.rewrite_query_with_history')
    @patch('requests.post')
    @patch('scripts.mcp_server.get_dify_config_for_current_project')
    def test_search_dify_knowledge_internal_uses_rewritten_query(self, mock_config, mock_post, mock_rewrite):
        # search_dify_knowledge_internal に履歴を渡した場合、書き換えクエリが使用されるかを検証
        mock_config.return_value = {
            "api_base": "http://localhost:8080/v1",
            "api_key": "dummy_key",
            "dataset_id": "dummy_dataset"
        }
        
        mock_rewrite.return_value = "Lissueのインストール方法"
        
        # requests.post (Dify API呼び出し) の応答モック
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"records": []}
        mock_post.return_value = mock_response
        
        chat_history = [{"role": "user", "content": "Lissueの件です。"}]
        
        with patch('scripts.mcp_server.redis_enabled', False):
            search_dify_knowledge_internal("インストール方法", "test_proj", chat_history)
            
        mock_rewrite.assert_called_once_with("インストール方法", chat_history)
        
        # Dify retrieve API 呼び出し時の query が書き換えクエリになっていることを検証
        called_args, called_kwargs = mock_post.call_args
        payload = called_kwargs.get("json", {})
        self.assertEqual(payload.get("query"), "Lissueのインストール方法")
