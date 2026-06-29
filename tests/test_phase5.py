import unittest
from unittest.mock import patch, MagicMock
import os
import shutil
import subprocess
import time
import json
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts')))
from sync_docs import DifySyncHandler
import mcp_server
from mcp_server import search_dify_knowledge

class TestPhase5Scripts(unittest.TestCase):
    def setUp(self):
        self.test_dir = "./test_docs_tmp"
        if not os.path.exists(self.test_dir):
            os.makedirs(self.test_dir)
        self.meta_file = "./test_sync_meta_tmp.json"
        
        self.config_file = os.path.join(self.test_dir, "sync_config.json")
        config_data = {
            "projects": {
                "project_x": {
                    "api_base": "http://mock-dify-api/x/v1",
                    "api_key": "api-key-x",
                    "dataset_id": "dataset-id-x"
                },
                "project_y": {
                    "api_base": "http://mock-dify-api/y/v1",
                    "api_key": "api-key-y",
                    "dataset_id": "dataset-id-y"
                }
            }
        }
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config_data, f)

    def tearDown(self):
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
        if os.path.exists(self.meta_file):
            try:
                os.remove(self.meta_file)
            except OSError:
                pass

    @patch('requests.post')
    def test_sync_docs_handler_upload_multi_project(self, mock_post):
        """Test document upload to multiple datasets based on directory structure"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"document": {"id": "doc_12345"}}
        mock_post.return_value = mock_response

        handler = DifySyncHandler(
            watch_dir=self.test_dir,
            api_base="",
            api_key="",
            dataset_id="",
            meta_file=self.meta_file,
            config_file=self.config_file
        )

        proj_x_dir = os.path.join(self.test_dir, "project_x")
        os.makedirs(proj_x_dir)
        test_file_x = os.path.join(proj_x_dir, "hello.md")
        with open(test_file_x, 'w', encoding='utf-8') as f:
            f.write("# Hello X")

        proj_y_dir = os.path.join(self.test_dir, "project_y")
        os.makedirs(proj_y_dir)
        test_file_y = os.path.join(proj_y_dir, "world.md")
        with open(test_file_y, 'w', encoding='utf-8') as f:
            f.write("# Hello Y")

        handler.upload_file(test_file_x)
        handler.upload_file(test_file_y)

        self.assertEqual(mock_post.call_count, 2)
        
        calls = mock_post.call_args_list
        args_x, kwargs_x = calls[0]
        self.assertEqual(args_x[0], "http://mock-dify-api/x/v1/datasets/dataset-id-x/document/create_by_file")
        self.assertEqual(kwargs_x["headers"]["Authorization"], "Bearer api-key-x")

        args_y, kwargs_y = calls[1]
        self.assertEqual(args_y[0], "http://mock-dify-api/y/v1/datasets/dataset-id-y/document/create_by_file")
        self.assertEqual(kwargs_y["headers"]["Authorization"], "Bearer api-key-y")

        self.assertEqual(handler.get_doc_id(test_file_x), "doc_12345")
        self.assertEqual(handler.get_doc_id(test_file_y), "doc_12345")

    def test_mcp_server_tool_missing_env(self):
        """Test search_dify_knowledge missing environment variables"""
        with patch.dict(os.environ, {}, clear=True):
            result = search_dify_knowledge("hello")
            self.assertIn("Error", result)

    @patch('requests.post')
    def test_mcp_server_tool_success(self, mock_post):
        """Test search_dify_knowledge tool returns results"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "records": [
                {"segment": {"content": "This is matched text."}, "score": 0.95}
            ]
        }
        mock_post.return_value = mock_response

        env = {
            "DIFY_DATASET_API_KEY": "mock-key",
            "DIFY_DATASET_ID": "dataset-123"
        }
        with patch.dict(os.environ, env):
            result = search_dify_knowledge("test-query")
            self.assertIn("This is matched text.", result)
            self.assertIn("0.95", result)

    @patch('requests.post')
    @patch('mcp_server.check_semantic_cache')
    def test_mcp_server_tool_dynamic_project(self, mock_check_cache, mock_post):
        """Test search_dify_knowledge dynamically switches dataset based on continue config"""
        mock_check_cache.return_value = None
        
        def mock_post_side_effect(url, *args, **kwargs):
            res = MagicMock()
            res.status_code = 200
            if "embeddings" in url:
                res.json.return_value = {"data": [{"embedding": [0.1] * 1024}]}
            else:
                res.json.return_value = {
                    "records": [{"segment": {"content": "Matched in project x."}, "score": 0.88}]
                }
            return res
        mock_post.side_effect = mock_post_side_effect

        # mock docs/sync_config.json mappings
        sync_config_data = {
            "projects": {
                "project_x": {
                    "api_base": "http://mock-dify-api/x/v1",
                    "api_key": "api-key-x",
                    "dataset_id": "dataset-id-x"
                }
            }
        }
        real_sync_config = "./docs/sync_config.json"
        has_real_config = os.path.exists(real_sync_config)
        backup_sync_config = "./docs/sync_config.json.bak"
        if has_real_config:
            shutil.copy2(real_sync_config, backup_sync_config)
        with open(real_sync_config, 'w', encoding='utf-8') as f:
            json.dump(sync_config_data, f)

        # Create active project configuration .continue/config.json
        continue_dir = "./.continue"
        if not os.path.exists(continue_dir):
            os.makedirs(continue_dir)
        continue_file = os.path.join(continue_dir, "config.json")
        continue_data = {
            "customSettings": {
                "current_project": "project_x"
            }
        }
        with open(continue_file, 'w', encoding='utf-8') as f:
            json.dump(continue_data, f)

        try:
            result = search_dify_knowledge("test-query")
            self.assertIn("Matched in project x.", result)
            self.assertIn("[Project: project_x]", result)
            
            self.assertEqual(mock_post.call_count, 2)
            # embeddings と retrieve の2つの呼び出しがそれぞれ行われたことを確認
            calls = mock_post.call_args_list
            embedding_call = calls[0]
            dify_call = calls[1]
            self.assertIn("embeddings", embedding_call[0][0])
            self.assertEqual(dify_call[0][0], "http://mock-dify-api/x/v1/datasets/dataset-id-x/retrieve")
            self.assertEqual(dify_call[1]["headers"]["Authorization"], "Bearer api-key-x")
        finally:
            if os.path.exists(continue_file):
                os.remove(continue_file)
            if os.path.exists(continue_dir):
                os.rmdir(continue_dir)
            if has_real_config:
                shutil.move(backup_sync_config, real_sync_config)
            elif os.path.exists(real_sync_config):
                os.remove(real_sync_config)

    def test_log_cleanup_script(self):
        """Test log rotation and cleanup bash script"""
        test_log_dir = "./test_logs_tmp"
        if os.path.exists(test_log_dir):
            shutil.rmtree(test_log_dir)
        os.makedirs(test_log_dir)

        old_log = os.path.join(test_log_dir, "old.log")
        with open(old_log, 'w') as f:
            f.write("old data")
        ten_days_ago = time.time() - (10 * 24 * 60 * 60)
        os.utime(old_log, (ten_days_ago, ten_days_ago))

        new_log = os.path.join(test_log_dir, "new.log")
        with open(new_log, 'w') as f:
            f.write("new data")

        large_log = os.path.join(test_log_dir, "large.log")
        with open(large_log, 'wb') as f:
            f.write(b"x" * (11 * 1024 * 1024))

        script_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../scripts/log_cleanup.sh'))
        
        result = subprocess.run([script_path, test_log_dir], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0)

        self.assertFalse(os.path.exists(old_log))
        self.assertTrue(os.path.exists(new_log))
        self.assertTrue(os.path.exists(large_log))
        self.assertEqual(os.path.getsize(large_log), 0)
        
        files = os.listdir(test_log_dir)
        gz_files = [f for f in files if f.endswith(".gz") and "large.log" in f]
        self.assertEqual(len(gz_files), 1)

        shutil.rmtree(test_log_dir)

if __name__ == '__main__':
    unittest.main()
