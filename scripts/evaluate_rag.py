import os
import sys
import json
import time
import urllib.request
import urllib.error
import dotenv

# パス追加
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(script_dir)
sys.path.append(os.path.dirname(script_dir))

# 環境変数ロード
dotenv.load_dotenv(os.path.join(os.path.dirname(script_dir), ".env"))

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
LITELLM_API_BASE = os.environ.get("LITELLM_API_BASE", "http://localhost:4000/v1")

def get_project_config():
    config_path = os.path.join(os.path.dirname(script_dir), "docs/sync_config.json")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("projects", {}).get("Lissue", {})
    return {}

def call_gemini_2_5_eval(query, reference, answer):
    if not GEMINI_API_KEY:
        print("Error: GEMINI_API_KEY is not configured in environment or .env file.")
        sys.exit(1)
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    prompt = f"""あなたはRAGシステムの精度を評価する厳格な評価者です。
ユーザーからの質問、提供された模範解答、およびシステムが作成した回答を比較し、以下の定義に従ってシステム回答を「Perfect」「Acceptable」「Missing」「Incorrect」のいずれか1つに分類してください。

分類基準：
- Perfect: システムの回答が、模範解答に含まれる重要な情報をすべて正確に含んでおり、ハルシネーション（提供されたコンテキスト以外の内部知識による推測や誤情報）が一切ない。
- Acceptable: システムの回答が、質問に対しておおむね正しい回答を提供しているが、模範解答に比べて一部の細かいディテールが欠けている。ハルシネーションはない。
- Missing: システムの回答が「わかりません」や「情報がありません」と答えており、回答として間違ったことは言っていないが、模範解答にあるべき情報を提供できていない。
- Incorrect: システムの回答に、ハルシネーション（コンテキストにない勝手な推測や事実誤認）が含まれている、または全く誤った回答をしている。

出力フォーマット（必ず以下のJSON形式でのみ出力してください。他の説明文や前置き、コードブロックの囲み ```json は一切含めず、純粋なJSON文字列のみを出力してください）：
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

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.0,
            "responseMimeType": "application/json"
        }
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            text = res_data["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text.strip())
    except Exception as e:
        print(f"Failed to call Gemini 2.5 API for evaluation: {e}")
        return {"evaluation": "Incorrect", "reason": f"Evaluation error: {e}"}

def call_standard_rag(query, config):
    api_base = config.get("api_base", "http://localhost:8080/v1").rstrip('/')
    api_key = config.get("api_key")
    dataset_id = config.get("dataset_id")
    
    # 1. Retrieve context from Dify Dataset
    retrieve_url = f"{api_base}/datasets/{dataset_id}/retrieve"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "query": query,
        "retrieval_model": {
            "search_method": "hybrid_search",
            "top_k": 4,
            "reranking_enable": False,
            "score_threshold_enabled": False
        }
    }
    
    req = urllib.request.Request(
        retrieve_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    
    context_parts = []
    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            for record in res_data.get("records", []):
                segment = record.get("segment", {})
                content = segment.get("content", "")
                if content:
                    context_parts.append(content)
    except Exception as e:
        print(f"Failed to retrieve context from Dify: {e}")
        return f"Error retrieving context: {e}"
        
    context = "\n\n".join(context_parts)
    
    # 2. Call LiteLLM for response generation
    litellm_url = f"{LITELLM_API_BASE.rstrip('/')}/chat/completions"
    litellm_payload = {
        "model": "gemini-3.5-flash",
        "messages": [
            {
                "role": "user",
                "content": f"以下に提供するドキュメント情報（コンテキスト）のみに基づいて、質問に正確に回答してください。ドキュメントに記述されていない情報については、絶対に推測や自分の知識を使わずに「情報がありません」とだけ答えてください。\n\n[コンテキスト]\n{context}\n\n[質問]\n{query}"
            }
        ],
        "temperature": 0.0
    }
    
    req = urllib.request.Request(
        litellm_url,
        data=json.dumps(litellm_payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer sk-1234"},
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            return res_data["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"Failed to get response from LiteLLM: {e}")
        return f"Error generating answer: {e}"

def call_workflow_rag(query, config):
    api_base = config.get("api_base", "http://localhost:8080/v1").rstrip('/')
    workflow_api_key = config.get("workflow_api_key")
    
    if not workflow_api_key:
        return "Workflow API Key is not configured."
        
    url = f"{api_base}/workflows/run"
    headers = {
        "Authorization": f"Bearer {workflow_api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "inputs": {
            "query": query
        },
        "response_mode": "blocking",
        "user": "evaluation-agent"
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST"
    )
    
    try:
        with urllib.request.urlopen(req) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            data = res_data.get("data", {})
            outputs = data.get("outputs", {})
            ans = outputs.get("result") or outputs.get("text")
            if not ans and outputs:
                ans = list(outputs.values())[0]
            return ans or "No response from workflow."
    except Exception as e:
        print(f"Failed to execute Dify workflow: {e}")
        return f"Error executing workflow: {e}"

def score_mapping(eval_str):
    mapping = {
        "Perfect": 1.0,
        "Acceptable": 0.5,
        "Missing": 0.0,
        "Incorrect": -1.0
    }
    return mapping.get(eval_str, 0.0)

def main():
    print("=== Starting RAG Quantitative Accuracy Evaluation ===")
    config = get_project_config()
    if not config:
        print("Error: Project config for Lissue is missing in sync_config.json.")
        sys.exit(1)
        
    dataset_path = os.path.join(os.path.dirname(script_dir), "tests/evaluation_dataset.json")
    if not os.path.exists(dataset_path):
        print(f"Error: Dataset file not found at {dataset_path}")
        sys.exit(1)
        
    with open(dataset_path, "r", encoding="utf-8") as f:
        dataset = json.load(f)
        
    questions = dataset.get("questions", [])
    print(f"Loaded {len(questions)} test questions.")
    
    sys_a_scores = []
    sys_b_scores = []
    
    results = []
    
    for idx, q in enumerate(questions, 1):
        query = q.get("query")
        reference = q.get("reference")
        print(f"\n[{idx}/{len(questions)}] Processing Query: {query}")
        
        # System A (Standard RAG)
        print("  Running System A (Standard RAG)...")
        ans_a = call_standard_rag(query, config)
        print("  Evaluating System A response...")
        eval_a = call_gemini_2_5_eval(query, reference, ans_a)
        score_a = score_mapping(eval_a.get("evaluation"))
        sys_a_scores.append(score_a)
        
        # System B (Agentic RAG / Dify Workflow)
        ans_b = "Workflow Skipped (No API Key)"
        eval_b = {"evaluation": "Missing", "reason": "Workflow API Key not set"}
        score_b = 0.0
        
        if config.get("workflow_api_key"):
            print("  Running System B (Dify Workflow)...")
            ans_b = call_workflow_rag(query, config)
            print("  Evaluating System B response...")
            eval_b = call_gemini_2_5_eval(query, reference, ans_b)
            score_b = score_mapping(eval_b.get("evaluation"))
            sys_b_scores.append(score_b)
        else:
            sys_b_scores.append(0.0)
            
        results.append({
            "id": q.get("id"),
            "query": query,
            "reference": reference,
            "system_a": {
                "answer": ans_a,
                "evaluation": eval_a.get("evaluation"),
                "reason": eval_a.get("reason"),
                "score": score_a
            },
            "system_b": {
                "answer": ans_b,
                "evaluation": eval_b.get("evaluation"),
                "reason": eval_b.get("reason"),
                "score": score_b
            }
        })
        
    avg_score_a = sum(sys_a_scores) / len(sys_a_scores) if sys_a_scores else 0.0
    avg_score_b = sum(sys_b_scores) / len(sys_b_scores) if sys_b_scores else 0.0
    
    # レポートファイルの出力先 (常に ~/agents/reports/ に出力)
    report_dir = os.path.expanduser("~/agents/reports")
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, "evaluation_report.md")
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# RAG精度評価レポート (RAG Quantitative Accuracy Report)\n\n")
        f.write(f"本レポートは、RAGシステムにおける回答精度の測定結果です。評価用LLMとして `gemini-2.5-flash` を使用し、事実性・適合性・ハルシネーションの有無を定量的にスコア化しています。\n\n")
        
        f.write("## 1. 総合スコア比較\n")
        f.write("スコア範囲: `-1.0` (全て誤回答/ハルシネーション) 〜 `1.0` (全て完璧な回答)\n\n")
        f.write("| システムアプローチ | 平均スコア | 評価概要 |\n")
        f.write("|---|---|---|\n")
        f.write(f"| **System A (Standard RAG)** | `{avg_score_a:+.4f}` | Dify Retrieve 経由のドキュメント検索 ＋ ローカル推論 |\n")
        if config.get("workflow_api_key"):
            f.write(f"| **System B (Dify Workflow)** | `{avg_score_b:+.4f}` | Dify ワークフロー（Agentic RAG / リランク・クエリ拡張） |\n\n")
        else:
            f.write(f"| **System B (Dify Workflow)** | `N/A` | ※ `DIFY_RAG_WORKFLOW_API_KEY` 未設定のためスキップ |\n\n")
            
        f.write("## 2. 質問ごとの詳細評価結果\n")
        for idx, res in enumerate(results, 1):
            f.write(f"### Q{idx}. {res['query']}\n")
            f.write(f"**模範解答 (Reference):**\n> {res['reference']}\n\n")
            
            f.write("#### 🔴 System A (Standard RAG)\n")
            f.write(f"- **生成回答**: {res['system_a']['answer']}\n")
            f.write(f"- **分類評価**: `{res['system_a']['evaluation']}` (点数: `{res['system_a']['score']:+.1f}`)\n")
            f.write(f"- **評価理由**: {res['system_a']['reason']}\n\n")
            
            if config.get("workflow_api_key"):
                f.write("#### 🔵 System B (Dify Workflow)\n")
                f.write(f"- **生成回答**: {res['system_b']['answer']}\n")
                f.write(f"- **分類評価**: `{res['system_b']['evaluation']}` (点数: `{res['system_b']['score']:+.1f}`)\n")
                f.write(f"- **評価理由**: {res['system_b']['reason']}\n\n")
            else:
                f.write("#### 🔵 System B (Dify Workflow)\n")
                f.write("- **評価**: スキップ\n")
                f.write("- **注意**: 本システムで Dify ワークフローの精度を測定するには、Dify 管理画面にてワークフロー API キーを発行し、`docs/sync_config.json` 内の `Lissue` プロジェクト設定の `workflow_api_key` にキーを設定してください。\n\n")
            f.write("---\n\n")
            
    print(f"\nEvaluation complete! Report successfully generated at: {report_path}")

if __name__ == "__main__":
    main()
