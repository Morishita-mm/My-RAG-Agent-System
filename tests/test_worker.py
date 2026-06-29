import unittest
from unittest.mock import patch, MagicMock
import os
import sys
import json
import time
import redis

import dotenv

# インポートパスの設定
script_dir = os.path.dirname(os.path.abspath(__file__))
dotenv.load_dotenv(os.path.abspath(os.path.join(script_dir, '../.env')))
sys.path.append(os.path.abspath(os.path.join(script_dir, '../scripts')))

# workerのインポート
import worker

class TestQueueWorker(unittest.TestCase):
    def setUp(self):
        # Redis接続
        self.redis_host = os.environ.get("REDIS_HOST", "localhost")
        self.redis_port = int(os.environ.get("REDIS_PORT", 6379))
        self.redis_password = os.environ.get("REDIS_PASSWORD", "difyai123456")
        self.queue_name = "ragy:jobs"
        
        try:
            self.redis_client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                password=self.redis_password,
                decode_responses=True,
                socket_timeout=2.0
            )
            self.redis_client.ping()
            self.redis_enabled = True
        except Exception:
            if self.redis_host == "redis":
                try:
                    self.redis_host = "localhost"
                    self.redis_client = redis.Redis(
                        host=self.redis_host,
                        port=self.redis_port,
                        password=self.redis_password,
                        decode_responses=True,
                        socket_timeout=2.0
                    )
                    self.redis_client.ping()
                    self.redis_enabled = True
                except Exception:
                    self.redis_enabled = False
            else:
                self.redis_enabled = False
            
        if self.redis_enabled:
            # テスト開始前にキューをクリア
            self.redis_client.delete(self.queue_name)
            # 重複防止キーもクリア
            keys = self.redis_client.keys("ragy:queued_projects:*")
            if keys:
                self.redis_client.delete(*keys)

    def tearDown(self):
        if self.redis_enabled:
            self.redis_client.delete(self.queue_name)
            keys = self.redis_client.keys("ragy:queued_projects:*")
            if keys:
                self.redis_client.delete(*keys)

    @patch('worker.run_sync_docs')
    @patch('worker.run_healer')
    async def async_test_job_processing(self, mock_healer, mock_sync_docs):
        # ジョブデータのシミュレーション
        sync_job = {
            "id": "job_1",
            "type": "sync_docs",
            "payload": {
                "project_name": "test_project_abc"
            }
        }
        healer_job = {
            "id": "job_2",
            "type": "run_healer",
            "payload": {
                "file_path": "scripts/test.py",
                "error_log": "Traceback..."
            }
        }
        
        # ジョブのディスパッチ処理テスト
        await worker.process_job(sync_job)
        mock_sync_docs.assert_called_once_with("test_project_abc")
        
        await worker.process_job(healer_job)
        mock_healer.assert_called_once_with("scripts/test.py", "Traceback...")

    def test_job_processing(self):
        """Test process_job dispatching to respective handlers"""
        import asyncio
        asyncio.run(self.async_test_job_processing())

    def test_enqueue_sync_docs_integration(self):
        """Test DifySyncHandler enqueues sync job when redis is enabled"""
        if not self.redis_enabled:
            self.skipTest("Redis is not available on localhost. Skipping integration test.")
            
        from sync_docs import DifySyncHandler
        
        # テスト専用のキューとロックキーに分離し、並行ワーカーとの競合を防ぐ
        test_queue = "ragy:jobs:test"
        test_lock_prefix = "ragy:queued_projects:test"
        
        self.redis_client.delete(test_queue)
        keys = self.redis_client.keys(f"{test_lock_prefix}:*")
        if keys:
            self.redis_client.delete(*keys)
            
        # ダミーのハンドラ作成
        handler = DifySyncHandler(
            watch_dir="./docs",
            api_base="http://localhost:8080/v1",
            api_key="mock-key",
            dataset_id="dataset-123"
        )
        
        # テスト用の宛先に上書き
        handler.queue_name = test_queue
        handler.lock_key_prefix = test_lock_prefix
        
        # Redis接続が確実に有効であることを確認
        self.assertTrue(handler.redis_enabled)
        
        # ジョブをエンキュー
        success = handler.enqueue_sync_job("test_project_x")
        self.assertTrue(success)
        
        # キューからジョブを取得して検証
        job_json = self.redis_client.lpop(test_queue)
        self.assertIsNotNone(job_json)
        
        job_data = json.loads(job_json)
        self.assertEqual(job_data["type"], "sync_docs")
        self.assertEqual(job_data["payload"]["project_name"], "test_project_x")
        
        # 後片付け
        self.redis_client.delete(test_queue)
        keys = self.redis_client.keys(f"{test_lock_prefix}:*")
        if keys:
            self.redis_client.delete(*keys)

if __name__ == '__main__':
    unittest.main()
