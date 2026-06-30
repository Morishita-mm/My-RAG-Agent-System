import os
import sys
import unittest
import urllib.request

# パス追加
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(os.path.dirname(script_dir))
sys.path.append(os.path.join(os.path.dirname(script_dir), "scripts"))

from scripts.evaluate_rag import run_evaluation, get_project_config

class TestRAGEvaluationIntegration(unittest.TestCase):
    def setUp(self):
        # サービス接続のチェック
        self.config = get_project_config()
        self.dify_live = False
        
        if self.config:
            api_base = self.config.get("api_base", "http://localhost:8080/v1")
            # リダイレクトポート問題を回避するため、末尾にスラッシュを付与
            if not api_base.endswith("/"):
                api_base += "/"
            try:
                # Dify API接続可能か確認 (404/401等のHTTPErrorはサーバーが起動している証)
                req = urllib.request.Request(api_base, method="HEAD")
                urllib.request.urlopen(req, timeout=2.0)
                self.dify_live = True
            except urllib.error.HTTPError as e:
                self.dify_live = True
            except Exception as e:
                # localhost を 127.0.0.1 に置換して再試行
                try:
                    alt_base = api_base.replace("localhost", "127.0.0.1")
                    req = urllib.request.Request(alt_base, method="HEAD")
                    urllib.request.urlopen(req, timeout=2.0)
                    self.dify_live = True
                except urllib.error.HTTPError:
                    self.dify_live = True
                except Exception:
                    pass

    def test_quantitative_rag_evaluation_integration(self):
        if not self.dify_live:
            self.skipTest("Local Dify API service is not running or unreachable.")
            
        print("\n=== Running Automated RAG Evaluation Integration Test ===")
        # リクエスト数制限 1件で高速実行
        metrics = run_evaluation(limit=1, config_override=self.config)
        
        self.assertIn("avg_score_a", metrics)
        self.assertIn("avg_score_b", metrics)
        self.assertIn("results", metrics)
        self.assertGreaterEqual(len(metrics["results"]), 1)
        
        # 精度スコアの自動アサーション
        # スコアが -1.0 (Incorrect: ハルシネーション/致命的間違い) でないことをアサート
        score_a = metrics["avg_score_a"]
        print(f"Standard RAG (System A) Score: {score_a:+.4f}")
        self.assertGreaterEqual(score_a, 0.0, "Standard RAG accuracy score dropped into the negative/incorrect range!")
        
        # レポートファイルが生成されていることをアサート
        report_path = os.path.expanduser("~/agents/reports/evaluation_report.md")
        self.assertTrue(os.path.exists(report_path), "Accuracy report file was not generated.")

if __name__ == '__main__':
    unittest.main()
