import os
import sys
import unittest
from unittest.mock import MagicMock, patch
import threading
import json

# パス追加
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(script_dir))
from scripts.sync_docs import DifySyncHandler

class TestSyncParallelPurge(unittest.TestCase):
    def setUp(self):
        self.watch_dir = os.path.join(script_dir, "test_watch")
        os.makedirs(self.watch_dir, exist_ok=True)
        self.meta_file = os.path.join(self.watch_dir, ".dify_sync_meta_test.json")
        if os.path.exists(self.meta_file):
            os.remove(self.meta_file)
            
        # ダミーのハンドラ作成
        self.handler = DifySyncHandler(
            watch_dir=self.watch_dir,
            api_base="http://localhost:8080/v1",
            api_key="dummy_key",
            dataset_id="dummy_dataset",
            meta_file=self.meta_file
        )

    def tearDown(self):
        if os.path.exists(self.meta_file):
            os.remove(self.meta_file)
        if os.path.exists(self.watch_dir):
            import shutil
            shutil.rmtree(self.watch_dir)

    def test_meta_lock_exists(self):
        # meta_lockが存在し、ロックオブジェクトであることを確認 (タスク1)
        self.assertTrue(hasattr(self.handler, 'meta_lock'))
        self.assertTrue(hasattr(self.handler.meta_lock, '__enter__'))
        self.assertTrue(hasattr(self.handler.meta_lock, '__exit__'))

    def test_save_metadata_thread_safety(self):
        # 複数スレッドから同時に save_metadata が呼ばれても破損やデッドロックが起きないか検証
        threads = []
        errors = []
        
        def worker(i):
            try:
                with self.handler.meta_lock:
                    self.handler.metadata[f"file_{i}.md"] = {"doc_id": f"id_{i}", "hash": f"hash_{i}"}
                self.handler.save_metadata()
            except Exception as e:
                errors.append(e)

        for i in range(20):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0, f"Thread-safety test failed with errors: {errors}")
        
        # 保存されたメタデータを確認
        with open(self.meta_file, 'r', encoding='utf-8') as f:
            saved_data = json.load(f)
        self.assertEqual(len(saved_data), 20)

    @patch('redis.Redis')
    def test_purge_project_cache(self, mock_redis):
        # Redisのパージ挙動を検証 (タスク3)
        mock_client = MagicMock()
        self.handler.redis_enabled = True
        self.handler.redis_client = mock_client
        
        # keys() が返すダミーのキー
        mock_client.keys.side_effect = lambda pat: [
            "mcp_exact_cache:test_proj:hash1" if "mcp_exact_cache" in pat else "mcp_cache:test_proj:uuid1"
        ]
        
        self.handler.purge_project_cache("test_proj")
        
        # delete が呼び出され、パージ対象のキーが渡されたか
        mock_client.delete.assert_called_once_with(
            "mcp_exact_cache:test_proj:hash1", "mcp_cache:test_proj:uuid1"
        )
