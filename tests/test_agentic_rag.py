import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import json
import dotenv

# パス追加
script_dir = os.path.dirname(os.path.abspath(__file__))
dotenv.load_dotenv(os.path.abspath(os.path.join(script_dir, '../.env')))
sys.path.append(os.path.abspath(os.path.join(script_dir, '../scripts')))

import mcp_server
import dify_search

class TestAgenticRAG(unittest.TestCase):
    def setUp(self):
        # テスト用のプロジェクト定義ダミー
        self.mock_config = {
            "api_base": "http://mock-dify-api/v1",
            "api_key": "mock-dataset-api-key",
            "dataset_id": "mock-dataset-id",
            "workflow_api_key": "mock-workflow-api-key"
        }
        
        # プロジェクト設定関数のパッチ
        self.config_patcher = patch('mcp_server.get_dify_config_for_current_project', return_value=self.mock_config)
        self.config_patcher.start()

        # Redisの無効化（テスト時の一時退避）
        self.real_redis_enabled = mcp_server.redis_enabled
        mcp_server.redis_enabled = False

    def tearDown(self):
        self.config_patcher.stop()
        mcp_server.redis_enabled = self.real_redis_enabled

    @patch('requests.post')
    def test_search_via_dify_workflow_success_list(self, mock_post):
        """Test successful Agentic RAG retrieval which returns a list of segments"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "outputs": {
                    "result": [
                        {"content": "Segment 1 content related to query", "score": 0.9234},
                        {"content": "Segment 2 content with details", "score": 0.8123}
                    ]
                }
            }
        }
        mock_post.return_value = mock_response
        
        result = mcp_server.search_dify_knowledge("test agentic search")
        
        # ワークフローAPIが呼ばれたか確認
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        self.assertIn("/workflows/run", args[0])
        self.assertEqual(kwargs['headers']['Authorization'], "Bearer mock-workflow-api-key")
        
        # 結果のフォーマットチェック
        self.assertIn("Agentic RAG", result)
        self.assertIn("Segment 1 content related to query", result)
        self.assertIn("Score: 0.9234", result)

    @patch('requests.post')
    def test_search_via_dify_workflow_success_string(self, mock_post):
        """Test successful Agentic RAG retrieval which returns a single text output"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": {
                "outputs": {
                    "result": "This is a direct string summary text returned by the workflow output."
                }
            }
        }
        mock_post.return_value = mock_response
        
        result = mcp_server.search_dify_knowledge("test string query")
        
        self.assertIn("Agentic RAG", result)
        self.assertIn("This is a direct string summary text", result)

    @patch('requests.post')
    def test_search_via_dify_workflow_fallback_on_empty(self, mock_post):
        """Test fallback to Dataset retrieval when workflow result is empty"""
        # 1回目のポスト（ワークフロー）は空の出力を返し、2回目のポスト（データセット検索）で結果を返すように設定
        mock_res_workflow = MagicMock()
        mock_res_workflow.status_code = 200
        mock_res_workflow.json.return_value = {
            "data": {"outputs": {"result": []}} # 空のリスト
        }
        
        mock_res_dataset = MagicMock()
        mock_res_dataset.status_code = 200
        mock_res_dataset.json.return_value = {
            "records": [
                {
                    "segment": {"content": "Fallback Dataset Segment", "document": {"name": "doc.md"}},
                    "score": 0.77
                }
            ]
        }
        
        mock_post.side_effect = [mock_res_workflow, mock_res_dataset]
        
        result = mcp_server.search_dify_knowledge("test fallback query")
        
        # 2回ポストが呼ばれたことを確認
        self.assertEqual(mock_post.call_count, 2)
        
        # 最終的にデータセット側の結果が取得できているか
        self.assertIn("Fallback Dataset Segment", result)
        self.assertNotIn("Agentic RAG", result)

    @patch('requests.post')
    def test_search_via_dify_workflow_fallback_on_error(self, mock_post):
        """Test fallback to Dataset retrieval when workflow API fails"""
        mock_res_workflow = MagicMock()
        mock_res_workflow.status_code = 500
        mock_res_workflow.text = "Internal Server Error"
        
        mock_res_dataset = MagicMock()
        mock_res_dataset.status_code = 200
        mock_res_dataset.json.return_value = {
            "records": [
                {
                    "segment": {"content": "Dataset Segment after HTTP 500", "document": {"name": "doc.md"}},
                    "score": 0.85
                }
            ]
        }
        
        mock_post.side_effect = [mock_res_workflow, mock_res_dataset]
        
        result = mcp_server.search_dify_knowledge("test error fallback")
        
        # 2回呼ばれてデータセット検索が動いたことを確認
        self.assertEqual(mock_post.call_count, 2)
        self.assertIn("Dataset Segment after HTTP 500", result)

if __name__ == '__main__':
    unittest.main()
