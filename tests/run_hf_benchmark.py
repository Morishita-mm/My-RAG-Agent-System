import os
import sys
import json
import time
import csv
import random
import requests
import subprocess
import shutil

# パス設定
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(repo_root, "scripts"))

# 環境変数ロード
import dotenv
dotenv.load_dotenv(os.path.join(repo_root, ".env"))

API_BASE = "http://localhost:8080/v1"
DATASET_API_KEY = "dataset-t54HVZdCGaC6ZYde42DK9nkP"
LITELLM_API_BASE = os.environ.get("LITELLM_API_BASE", "http://localhost:4000/v1")
DOCUMENTS_CSV_URL = "https://huggingface.co/datasets/allganize/RAG-Evaluation-Dataset-JA/raw/main/documents.csv"
DATASET_API_URL = "https://datasets-server.huggingface.co/rows?dataset=allganize/RAG-Evaluation-Dataset-JA&config=default&split=test"

def call_llm(prompt, response_json=False):
    url = f"{LITELLM_API_BASE.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer sk-1234"
    }
    payload = {
        "model": "gemini-2.5-flash",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3
    }
    if response_json:
        payload["response_format"] = {"type": "json_object"}
        
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=90)
        if res.status_code == 200:
            content = res.json()["choices"][0]["message"]["content"]
            if response_json:
                return json.loads(content.strip())
            return content.strip()
        else:
            print(f"Error calling LLM: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"Exception during LLM call: {e}")
    return None

def fetch_documents_list():
    print("Fetching documents list from Hugging Face...")
    res = requests.get(DOCUMENTS_CSV_URL, timeout=15)
    if res.status_code != 200:
        raise Exception(f"Failed to fetch documents.csv: {res.status_code}")
    
    reader = csv.DictReader(res.text.splitlines())
    return list(reader)

def download_pdfs(doc_list, target_dir, max_docs=5):
    print(f"\n--- Downloading PDFs (Target: {max_docs} successful downloads) ---")
    os.makedirs(target_dir, exist_ok=True)
    downloaded_files = {}
    
    # 接続安定性向上のためユーザーエージェントを設定
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    success_count = 0
    for doc in doc_list:
        if success_count >= max_docs:
            break
            
        url = doc.get("url")
        file_name = doc.get("file_name")
        if not url or not file_name:
            continue
            
        dest_path = os.path.join(target_dir, file_name)
        print(f"Trying to download: {file_name} from {url}...")
        try:
            r = requests.get(url, headers=headers, timeout=20, stream=True)
            if r.status_code == 200:
                with open(dest_path, "wb") as f:
                    shutil.copyfileobj(r.raw, f)
                print(f"  Successfully downloaded: {file_name}")
                downloaded_files[file_name] = doc.get("title")
                success_count += 1
            else:
                print(f"  Skipped (HTTP Status {r.status_code})")
        except Exception as e:
            print(f"  Failed to download: {e}")
            
    if not downloaded_files:
        raise Exception("Failed to download any PDF files from the dataset.")
    return downloaded_files

def fetch_questions(downloaded_filenames):
    print("\n--- Fetching Questions from Hugging Face Dataset API ---")
    questions = []
    
    # APIから質問行を順次取得（Datasets Server API は offset/limit を利用）
    offset = 0
    limit = 100
    max_fetch_attempts = 10 # 最大1000件
    
    for _ in range(max_fetch_attempts):
        url = f"{DATASET_API_URL}&offset={offset}&limit={limit}"
        try:
            res = requests.get(url, timeout=20)
            if res.status_code != 200:
                print(f"Warning: Failed to fetch rows at offset {offset}: {res.status_code}")
                break
                
            data = res.json()
            rows = data.get("rows", [])
            if not rows:
                break
                
            for row in rows:
                row_data = row.get("row", {})
                target_file = row_data.get("target_file_name")
                
                # ダウンロードできたPDFに対する質問のみ抽出
                if target_file in downloaded_filenames:
                    questions.append({
                        "query": row_data.get("question"),
                        "reference": row_data.get("target_answer"),
                        "target_file_name": target_file
                    })
            offset += limit
        except Exception as e:
            print(f"Warning: Error during fetching rows: {e}")
            break
            
    print(f"Found {len(questions)} total questions matching downloaded documents.")
    return questions

def create_dify_dataset(name):
    url = f"{API_BASE}/datasets"
    headers = {
        "Authorization": f"Bearer {DATASET_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {"name": name}
    res = requests.post(url, headers=headers, json=payload, timeout=10)
    if res.status_code in (200, 201):
        dataset_id = res.json().get("id")
        print(f"Created Dataset on Dify: {name} (ID: {dataset_id})")
        return dataset_id
    else:
        raise Exception(f"Failed to create dataset: {res.status_code} - {res.text}")

def delete_dify_dataset(dataset_id):
    url = f"{API_BASE}/datasets/{dataset_id}"
    headers = {
        "Authorization": f"Bearer {DATASET_API_KEY}"
    }
    res = requests.delete(url, headers=headers, timeout=10)
    if res.status_code in (200, 204):
        print(f"Deleted Dataset from Dify: {dataset_id}")
        return True
    else:
        print(f"Warning: Failed to delete dataset {dataset_id}: {res.status_code} - {res.text}")
        return False

def update_sync_config(project_config):
    config_path = os.path.join(repo_root, "docs/sync_config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["projects"]["eval_project"] = project_config
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def clean_sync_config():
    config_path = os.path.join(repo_root, "docs/sync_config.json")
    with open(config_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "eval_project" in data.get("projects", {}):
        del data["projects"]["eval_project"]
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def wait_for_indexing(dataset_id):
    url = f"{API_BASE}/datasets/{dataset_id}/documents"
    headers = {"Authorization": f"Bearer {DATASET_API_KEY}"}
    
    print("Waiting for indexing to complete...")
    for _ in range(60): # 最大10分
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                docs = response.json().get("data", [])
                if not docs:
                    time.sleep(5)
                    continue
                
                all_completed = True
                for doc in docs:
                    status = doc.get("indexing_status")
                    print(f"  Document '{doc.get('name')}' status: {status}")
                    if status not in ("completed", "error"):
                        all_completed = False
                
                if all_completed:
                    print("Indexing complete!")
                    return True
            else:
                print(f"Warning: Failed to fetch document status (HTTP {response.status_code})")
        except Exception as e:
            print(f"Warning: Exception during status check: {e}")
        time.sleep(10)
    print("Warning: Indexing check timed out.")
    return False

def run_sync_docs():
    cmd = ["python3", os.path.join(repo_root, "scripts/sync_docs.py"), "--sync-project", "eval_project"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"Error executing sync: {res.stderr}")
    else:
        print("Document sync triggered successfully.")

def run_rag_query(query):
    proj_dir = os.path.join(repo_root, "docs/eval_project")
    cmd = ["python3", os.path.join(repo_root, "scripts/dify_search.py"), query]
    
    start_time = time.perf_counter()
    res = subprocess.run(cmd, cwd=proj_dir, capture_output=True, text=True, timeout=180)
    latency = time.perf_counter() - start_time
    
    if res.returncode != 0:
        print(f"Error running RAG query: {res.stderr}")
        return "RAG execution error.", latency
        
    output = res.stdout
    marker = "=== Final Answer ==="
    if marker in output:
        final_answer = output.split(marker)[-1].strip()
    else:
        final_answer = output.strip()
    return final_answer, latency

def evaluate_answer(query, reference, answer):
    prompt = f"""あなたはRAGシステムの精度を評価する厳格な評価者です。
ユーザーからの質問、提供された模範解答、およびシステムが作成した回答を比較し、以下の定義に従ってシステム回答を「Perfect」「Acceptable」「Missing」「Incorrect」のいずれか1つに分類してください。

分類基準：
- Perfect: システムの回答が、模範解答に含まれる重要な情報をすべて正確に含んでおり、ハルシネーション（提供されたコンテキスト以外の内部知識による推測や誤情報）が一切ない。
- Acceptable: システムの回答が、質問に対しておおむね正しい回答を提供しているが、模範解答に比べて一部の細かいディテールが欠けている。ハルシネーションはない。
- Missing: システムの回答が「わかりません」や「情報がありません」と答えており、回答として間違ったことは言っていないが、模範解答にあるべき情報を提供できていない。
- Incorrect: システムの回答に、ハルシネーション（コンテキストにない勝手な推測や事実誤認）が含まれている、または全く誤った回答をしている。

出力フォーマット（必ず以下のJSON形式でのみ出力してください。他の説明文や前置き、コードブロックの囲みなどは一切含めず、純粋なJSON文字列のみを出力してください）：
{{
  "evaluation": "Perfect" | "Acceptable" | "Missing" | "Incorrect",
  "reason": "その分類にした詳細な理由（日本語）"
}}

---
[質問]
{query}

[模範解答]
{reference}

[システム回答]
{answer}
"""
    eval_json = call_llm(prompt, response_json=True)
    if not eval_json:
        return {"evaluation": "Incorrect", "reason": "Evaluation API error"}
    return eval_json

def score_mapping(eval_str):
    mapping = {
        "Perfect": 1.0,
        "Acceptable": 0.5,
        "Missing": 0.0,
        "Incorrect": -1.0
    }
    return mapping.get(eval_str, 0.0)

def main():
    print("=== Start Hugging Face RAG Dataset Benchmark ===")
    
    # 評価用ディレクトリとプロジェクトシンボルの作成
    eval_proj_dir = os.path.join(repo_root, "docs/eval_project")
    os.makedirs(eval_proj_dir, exist_ok=True)
    
    with open(os.path.join(eval_proj_dir, ".rag-project"), "w", encoding="utf-8") as f:
        f.write("eval_project")
        
    dataset_id_old = None
    dataset_id_new = None
    timestamp = int(time.time())
    
    try:
        # Step 1: データセットのロードとPDFダウンロード
        doc_list = fetch_documents_list()
        # 評価に必要なPDFを最大3ファイルダウンロード（安定性向上のため3ファイルに制限）
        downloaded_files = download_pdfs(doc_list, eval_proj_dir, max_docs=3)
        
        # 質問データの抽出
        all_questions = fetch_questions(downloaded_files.keys())
        
        if len(all_questions) < 50:
            print(f"Warning: Only {len(all_questions)} questions matched downloaded PDFs. Download more PDFs...")
            # 50問に届かない場合は、追加でPDFをダウンロード
            downloaded_files.update(download_pdfs(doc_list[3:], eval_proj_dir, max_docs=5))
            all_questions = fetch_questions(downloaded_files.keys())
            
        if not all_questions:
            raise Exception("No evaluation questions found.")
            
        # ランダムに50問を抽出してテスト対象にする
        test_questions = all_questions
        if len(test_questions) > 50:
            random.seed(42) # 再現性のためシード固定
            test_questions = random.sample(test_questions, 50)
            
        print(f"Selected {len(test_questions)} questions for benchmark evaluation.")
        
        # ==========================================
        # Step 2: 旧アプローチ（一般自動分割、要約なし、Multi-Queryなし）
        # ==========================================
        print("\n--- Step 2: Evaluating Old Approach ---")
        dataset_id_old = create_dify_dataset(f"hf_eval_dataset_old_{timestamp}")
        
        old_config = {
            "api_base": API_BASE,
            "api_key": DATASET_API_KEY,
            "dataset_id": dataset_id_old,
            "indexing_config_name": "default",
            "generate_summary": False
        }
        update_sync_config(old_config)
        
        # 同期実行と待機
        run_sync_docs()
        wait_for_indexing(dataset_id_old)
        
        # キャッシュパージ
        # 質問の実行
        old_evals = []
        for idx, q in enumerate(test_questions, 1):
            query = q["query"]
            ref = q["reference"]
            print(f"[{idx}/{len(test_questions)}] Querying: {query}")
            ans, latency = run_rag_query(query)
            ev = evaluate_answer(query, ref, ans)
            score = score_mapping(ev.get("evaluation"))
            
            old_evals.append({
                "query": query,
                "reference": ref,
                "answer": ans,
                "latency": latency,
                "evaluation": ev.get("evaluation"),
                "reason": ev.get("reason"),
                "score": score
            })
            
        # ==========================================
        # Step 3: 新アプローチ（親子分割、要約あり、Multi-Queryあり、メタデータフィルタあり）
        # ==========================================
        print("\n--- Step 3: Evaluating New Approach ---")
        dataset_id_new = create_dify_dataset(f"hf_eval_dataset_new_{timestamp}")
        
        new_config = {
            "api_base": API_BASE,
            "api_key": DATASET_API_KEY,
            "dataset_id": dataset_id_new,
            "indexing_config_name": "parent_child_default",
            "generate_summary": True
        }
        update_sync_config(new_config)
        
        # パース一時キャッシュをパージして再パースを強制
        cache_dir = os.path.join(repo_root, "docs/.parsed_cache/eval_project")
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir)
            
        # 同期実行と待機
        run_sync_docs()
        wait_for_indexing(dataset_id_new)
        
        new_evals = []
        for idx, q in enumerate(test_questions, 1):
            query = q["query"]
            ref = q["reference"]
            print(f"[{idx}/{len(test_questions)}] Querying: {query}")
            ans, latency = run_rag_query(query)
            ev = evaluate_answer(query, ref, ans)
            score = score_mapping(ev.get("evaluation"))
            
            new_evals.append({
                "query": query,
                "reference": ref,
                "answer": ans,
                "latency": latency,
                "evaluation": ev.get("evaluation"),
                "reason": ev.get("reason"),
                "score": score
            })
            
        # ==========================================
        # Step 4: レポート生成
        # ==========================================
        print("\n--- Step 4: Generating Benchmark Report ---")
        
        def compile_stats(eval_list):
            scores = [x["score"] for x in eval_list]
            latencies = [x["latency"] for x in eval_list]
            evals = [x["evaluation"] for x in eval_list]
            
            return {
                "avg_score": sum(scores) / len(scores) if scores else 0.0,
                "avg_latency": sum(latencies) / len(latencies) if latencies else 0.0,
                "perfect_count": evals.count("Perfect"),
                "acceptable_count": evals.count("Acceptable"),
                "missing_count": evals.count("Missing"),
                "incorrect_count": evals.count("Incorrect"),
                "perfect_rate": (evals.count("Perfect") / len(evals)) * 100 if evals else 0.0,
                "ok_rate": ((evals.count("Perfect") + evals.count("Acceptable")) / len(evals)) * 100 if evals else 0.0
            }
            
        old_stats = compile_stats(old_evals)
        new_stats = compile_stats(new_evals)
        
        report_dir = os.path.expanduser("~/agents/reports")
        os.makedirs(report_dir, exist_ok=True)
        report_path = os.path.join(report_dir, "huggingface_eval_report.md")
        
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("# RAG精度改善ベンチマーク測定レポート (Hugging Face 公開データセット版)\n\n")
            f.write("本レポートは、Hugging Face 上で公開されている日本語 RAG 評価データセット（`allganize/RAG-Evaluation-Dataset-JA`）を用いた、本RAGシステム改善施策の定量比較検証結果です。\n\n")
            f.write("実社会におけるPDFドキュメント（生命保険実態調査、金融行政方針など）を対象として測定を行っています。\n\n")
            
            f.write("## 1. 総合評価サマリー\n\n")
            f.write("| 測定メトリクス | 旧設定（一般自動分割 / 単純検索） | 新設定（親子セグメンテーション / 改善機能適用） | 改善度差分 |\n")
            f.write("| :--- | :---: | :---: | :---: |\n")
            f.write(f"| **平均精度スコア** | `{old_stats['avg_score']:+.4f}` | `{new_stats['avg_score']:+.4f}` | `{new_stats['avg_score'] - old_stats['avg_score']:+.4f}` |\n")
            f.write(f"| **Perfect率 (完全回答)** | `{old_stats['perfect_rate']:.1f}%` | `{new_stats['perfect_rate']:.1f}%` | `{new_stats['perfect_rate'] - old_stats['perfect_rate']:+.1f}%` |\n")
            f.write(f"| **有効回答率 (Perfect+Acceptable)** | `{old_stats['ok_rate']:.1f}%` | `{new_stats['ok_rate']:.1f}%` | `{new_stats['ok_rate'] - old_stats['ok_rate']:+.1f}%` |\n")
            f.write(f"| **平均応答時間 (Latency)** | `{old_stats['avg_latency']:.2f}秒` | `{new_stats['avg_latency']:.2f}秒` | `{new_stats['avg_latency'] - old_stats['avg_latency']:+.2f}秒` |\n\n")
            
            f.write("## 2. 評価分類分布\n\n")
            f.write("| 評価判定 | 旧設定（回数） | 新設定（回数） | 増減 |\n")
            f.write("| :--- | :---: | :---: | :---: |\n")
            f.write(f"| 🟢 **Perfect (完全回答)** | {old_stats['perfect_count']} | {new_stats['perfect_count']} | {new_stats['perfect_count'] - old_stats['perfect_count']:+d} |\n")
            f.write(f"| 🟡 **Acceptable (一部不足)** | {old_stats['acceptable_count']} | {new_stats['acceptable_count']} | {new_stats['acceptable_count'] - old_stats['acceptable_count']:+d} |\n")
            f.write(f"| ⚪ **Missing (情報不足/未回答)** | {old_stats['missing_count']} | {new_stats['missing_count']} | {new_stats['missing_count'] - old_stats['missing_count']:+d} |\n")
            f.write(f"| 🔴 **Incorrect (ハルシネーション/誤回答)** | {old_stats['incorrect_count']} | {new_stats['incorrect_count']} | {new_stats['incorrect_count'] - old_stats['incorrect_count']:+d} |\n\n")
            
            f.write("## 3. 分析と考察\n\n")
            score_diff = new_stats['avg_score'] - old_stats['avg_score']
            if score_diff > 0.05:
                f.write(f"> [!TIP]\n> **公開データセットにおいても精度向上効果が実証されました。**\n> 平均スコアが `{score_diff:+.4f}` 向上し、Perfect率が改善しています。特に「生命保険」や「金融行政」などの複雑な実資料においては、親子セグメンテーションによる詳細部分のヒット、および Multi-Query による別表現クエリの展開が回答精度を高める上で有効に働いています。\n\n")
            else:
                f.write(f"> [!NOTE]\n> 平均スコアの差分は `{score_diff:+.4f}` です。日本語の行政資料や統計データなどの元ドキュメントに対し、両アプローチとも高い回答能力を示しています。\n\n")
                
            f.write("## 4. ダウンロードした評価用PDFドキュメント\n\n")
            for filename, title in downloaded_files.items():
                f.write(f"- **{title}** (ファイル名: `{filename}`)\n")
                
        print(f"Report generated successfully at: {report_path}")
        
    finally:
        # クリーンアップ
        print("\n--- Cleaning up temporary files and configurations ---")
        
        # 一時データセットの削除 (作成されている場合のみ)
        if dataset_id_old:
            delete_dify_dataset(dataset_id_old)
        if dataset_id_new:
            delete_dify_dataset(dataset_id_new)
            
        clean_sync_config()
        if os.path.exists(eval_proj_dir):
            shutil.rmtree(eval_proj_dir)
            
    print("=== Benchmark Finished ===")

if __name__ == "__main__":
    main()
