import os
import sys
import unittest

# パス追加
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(script_dir))
sys.path.append(os.path.join(os.path.dirname(script_dir), "scripts"))

from scripts.mcp_server import reorder_records as mcp_reorder
from scripts.dify_search import reorder_records as search_reorder

class TestContextOptimization(unittest.TestCase):
    def test_reorder_empty_or_short(self):
        # 2件以下の場合はそのまま返ることを検証
        records_0 = []
        self.assertEqual(mcp_reorder(records_0), [])
        
        records_1 = [{"score": 0.9, "content": "A"}]
        self.assertEqual(mcp_reorder(records_1), records_1)
        
        records_2 = [{"score": 0.9, "content": "A"}, {"score": 0.8, "content": "B"}]
        self.assertEqual(mcp_reorder(records_2), records_2)

    def test_reorder_lost_in_the_middle(self):
        # 5件のテストデータを用意 (スコアは降順にソート)
        records = [
            {"score": 0.95, "content": "Doc 1 (Best)"},
            {"score": 0.85, "content": "Doc 2 (Second Best)"},
            {"score": 0.75, "content": "Doc 3 (Middle)"},
            {"score": 0.65, "content": "Doc 4 (Lower)"},
            {"score": 0.55, "content": "Doc 5 (Worst)"}
        ]
        
        reordered = mcp_reorder(records)
        
        # 件数が変わっていないことを検証
        self.assertEqual(len(reordered), 5)
        
        # Lost in the Middle を避けるための配置の検証:
        # インデックス 0 (最上部): Rank 1 (score 0.95)
        # インデックス 1: Rank 3 (score 0.75)
        # インデックス 2 (真ん中): Rank 5 (score 0.55 - 最悪値)
        # インデックス 3: Rank 4 (score 0.65)
        # インデックス 4 (最下部): Rank 2 (score 0.85 - 2番目に良い値)
        self.assertEqual(reordered[0]["score"], 0.95)
        self.assertEqual(reordered[1]["score"], 0.75)
        self.assertEqual(reordered[2]["score"], 0.55)
        self.assertEqual(reordered[3]["score"], 0.65)
        self.assertEqual(reordered[4]["score"], 0.85)

        # dify_search.py の reorder_records も同じロジックであることを確認
        search_reordered = search_reorder(records)
        self.assertEqual(search_reordered, reordered)

if __name__ == '__main__':
    unittest.main()
