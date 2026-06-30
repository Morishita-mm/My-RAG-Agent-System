import os
import sys
import unittest
import math

# パス追加
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(script_dir))
from scripts.mcp_server import normalize_vector, cosine_similarity

class TestSemanticCacheOpt(unittest.TestCase):
    def test_normalize_vector(self):
        # ベクトルの L2 正規化（長さが 1.0 になること）を検証
        v = [3.0, 4.0]
        normalized = normalize_vector(v)
        self.assertAlmostEqual(normalized[0], 0.6)
        self.assertAlmostEqual(normalized[1], 0.8)
        
        # ゼロベクトルのハンドリング
        zero_v = [0.0, 0.0]
        self.assertEqual(normalize_vector(zero_v), [0.0, 0.0])

    def test_cosine_similarity_normalized(self):
        # 単位ベクトル化したもの同士の内積（ドット積）が、元のベクトルのコサイン類似度と一致することを確認
        v1 = [1.0, 2.0, 3.0]
        v2 = [4.0, 5.0, 6.0]
        
        # 通常のコサイン類似度
        orig_sim = cosine_similarity(v1, v2)
        
        # 正規化ベクトルのドット積
        nv1 = normalize_vector(v1)
        nv2 = normalize_vector(v2)
        dot_sim = sum(a * b for a, b in zip(nv1, nv2))
        
        self.assertAlmostEqual(orig_sim, dot_sim, places=6)
