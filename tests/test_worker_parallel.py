import os
import sys
import unittest
import json
import time
import threading
from unittest.mock import patch, MagicMock

# プロジェクトパスをインポートに追加
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.abspath(os.path.join(script_dir, "../scripts")))

import worker

class TestParallelWorker(unittest.TestCase):
    def setUp(self):
        worker.RAG_MAX_WORKERS = 2
        # テスト実行用のモックジョブデータ
        self.mock_jobs = [
            {"id": f"job_{i}", "type": "sync_docs", "payload": {"project_name": "test_project"}}
            for i in range(5)
        ]

    def test_parallel_execution_limit(self):
        """同時に最大2スレッドまでしかジョブが実行されないことを検証"""
        active_threads = 0
        max_seen_concurrency = 0
        lock = threading.Lock()

        def mock_sync_docs(project_name):
            nonlocal active_threads, max_seen_concurrency
            # 現在のスレッドIDを取得して現在の並行数を追跡
            with lock:
                active_threads += 1
                if active_threads > max_seen_concurrency:
                    max_seen_concurrency = active_threads
            
            # 各ジョブごとに少しスリープして、並行実行状態を作り出す
            time.sleep(0.1)
            
            with lock:
                active_threads -= 1

        with patch('worker.run_sync_docs', side_effect=mock_sync_docs), \
             patch('worker.redis_client') as mock_redis:
            
            # 6回目以降もNoneを返し続けられるように十分なバッファを追加
            pop_results = [("queue", json.dumps(job)) for job in self.mock_jobs]
            pop_results.extend([None] * 50)
            
            mock_redis.blpop.side_effect = pop_results
            
            # worker_loop を動かし、途中でCancelErrorを発生させて終了させる
            # asyncio イベントループの run_in_executor を動かすため、実際の非同期ループ内で検証
            import asyncio
            
            async def run_test():
                # ワーカーをバックグラウンドタスクとして起動
                task = asyncio.create_task(worker.worker_loop())
                # ジョブがポップされてスレッドプール上で走り終えるのを待つ
                await asyncio.sleep(0.6)
                # タスクを終了
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

            asyncio.run(run_test())

        # アサーション: 同時実行数が2以下に制限されていることを検証
        print(f"Max observed concurrency during test: {max_seen_concurrency}")
        self.assertTrue(max_seen_concurrency > 0, "No parallel jobs were executed.")
        self.assertTrue(max_seen_concurrency <= 2, f"Concurrency exceeded threshold! Max was: {max_seen_concurrency}")

if __name__ == "__main__":
    unittest.main()
