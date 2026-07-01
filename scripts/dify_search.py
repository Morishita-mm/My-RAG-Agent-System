import sys
import json
import os
import requests


# パス解決とユーティリティのインポート
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)
from utils import get_current_project, reorder_records

LITELLM_BASE = os.environ.get("LITELLM_BASE", "http://localhost:4000")
LITELLM_KEY = os.environ.get("LITELLM_KEY", "sk-1234")

def generate_local_summary(query: str, context: str) -> str:
    url = f"{LITELLM_BASE}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {LITELLM_KEY}",
        "Content-Type": "application/json"
    }
    prompt = f"""以下に提供するドキュメント情報（コンテキスト）のみに基づいて、質問に日本語で正確に回答してください。
ドキュメントに記述されていない情報については、絶対に推測や自分の知識を使わずに「情報がありません」とだけ答えてください。
ハルシネーションを厳格に防止してください。

[コンテキスト]
{context}

[質問]
{query}
"""
    payload = {
        "model": "qwen2.5-coder",
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.0
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=25)
        if response.status_code == 200:
            data = response.json()
            return data["choices"][0]["message"]["content"]
    except Exception:
        pass
    return "Error generating local RAG summary."


def grade_context_sufficiency(query: str, context: str) -> str:
    url = f"{LITELLM_BASE}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {LITELLM_KEY}",
        "Content-Type": "application/json"
    }
    prompt = f"""You are a context relevance grader. Evaluate if the retrieved document context contains sufficient information to directly answer the user's question.
Return one of the following decisions as a single word:
- YES: The context is fully sufficient to answer the question directly.
- NO: The context is completely irrelevant or missing the key information.
- PARTIAL: The context has some relevant terms but is insufficient to provide a complete, high-quality answer.

[Context]
{context}

[Question]
{query}

Decision (YES/NO/PARTIAL):"""

    payload = {
        "model": "qwen2.5-coder",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        if response.status_code == 200:
            decision = response.json()["choices"][0]["message"]["content"].strip().upper()
            if "YES" in decision:
                return "YES"
            elif "NO" in decision:
                return "NO"
            elif "PARTIAL" in decision:
                return "PARTIAL"
    except Exception:
        pass
    return "PARTIAL"


def rewrite_search_query(query: str, context: str) -> str:
    url = f"{LITELLM_BASE}/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {LITELLM_KEY}",
        "Content-Type": "application/json"
    }
    prompt = f"""You are a search query optimizer. Given the original question and the current insufficient search context, rewrite the query to improve the chance of finding the missing information in the vector database.
Only output the rewritten search query. Do not add any explanation, quotation marks, or preamble.

[Original Question]
{query}

[Current Context]
{context}

Optimized Search Query:"""

    payload = {
        "model": "qwen2.5-coder",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"].strip().strip('"').strip("'")
    except Exception:
        pass
    return query


def get_project_config(project_id):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)
    sync_config = os.path.join(repo_root, "docs/sync_config.json")

    if os.path.exists(sync_config):
        try:
            with open(sync_config, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("projects", {}).get(project_id)
        except Exception:
            pass
    return None


def search_dify_knowledge(query):
    project_id = get_current_project()
    if not project_id:
        print("Error: Could not determine project name from current directory.")
        sys.exit(1)

    config = get_project_config(project_id)
    if not config:
        print(
            f"Error: No configuration found for project '{project_id}' in docs/sync_config.json"
        )
        sys.exit(1)

    api_base = config.get("api_base", "").rstrip("/")
    dataset_api_key = config.get("api_key")
    workflow_api_key = config.get("workflow_api_key") or os.environ.get(
        "DIFY_RAG_WORKFLOW_API_KEY"
    )
    dataset_id = config.get("dataset_id")

    # 1. ワークフローAPIが利用可能な場合は優先実行 (Agentic RAG)
    if workflow_api_key:
        url = f"{api_base}/workflows/run"
        headers = {
            "Authorization": f"Bearer {workflow_api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "inputs": {"query": query},
            "response_mode": "blocking",
            "user": "mcp-agent",
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=20)
            if response.status_code == 200:
                res_data = response.json()
                outputs = res_data.get("data", {}).get("outputs", {})
                records = outputs.get("result", [])

                if isinstance(records, list) and records:
                    print(
                        f"=== Knowledge search results for [Project: {project_id}] (Agentic RAG) ==="
                    )
                    for idx, rec in enumerate(records, 1):
                        if isinstance(rec, dict):
                            score = rec.get("score", 0.0)
                            content = rec.get("content", "")
                            print(f"\n[{idx}] Score: {score:.4f}")
                            print("-" * 50)
                            print(content.strip())
                            print("-" * 50)
                        else:
                            print(f"\n[{idx}] Output:")
                            print(str(rec))
                    return
                elif isinstance(records, str) and records:
                    print(
                        f"=== Knowledge search results for [Project: {project_id}] (Agentic RAG) ==="
                    )
                    print(records)
                    return
            else:
                print(
                    f"Warning: Dify Workflow API responded with {response.status_code}. Falling back to retrieve API..."
                )
        except Exception as e:
            print(
                f"Warning: Exception during Dify Workflow search ({e}). Falling back to retrieve API..."
            )

    # 2. 従来のデータセットAPIへのフォールバック（Self-RAGループ処理）
    if not dataset_api_key or not dataset_id:
        print(f"Error: Missing api_key or dataset_id for project '{project_id}'")
        sys.exit(1)

    url = f"{api_base}/datasets/{dataset_id}/retrieve"
    headers = {
        "Authorization": f"Bearer {dataset_api_key}",
        "Content-Type": "application/json",
    }

    current_query = query
    retrieved_segments = []
    seen_contents = set()
    max_loops = 3

    print(f"=== Knowledge search results for [Project: {project_id}] (Self-RAG/Local Synthesis) ===")

    for loop_idx in range(1, max_loops + 1):
        print(f"\n[Loop {loop_idx}/3] Searching for: '{current_query}'...")
        payload = {
            "query": current_query,
            "retrieval_model": {
                "search_method": "hybrid_search",
                "top_k": 5,
                "reranking_enable": True,
                "score_threshold_enabled": True,
                "score_threshold": 0.4,
            },
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=15)
            if response.status_code == 200:
                records = response.json().get("records", [])
                if not records:
                    print(f"  -> No matching knowledge found in loop {loop_idx}.")
                else:
                    reordered_records = reorder_records(records)
                    new_added = 0
                    for rec in reordered_records:
                        segment = rec.get("segment", {})
                        content = segment.get("content", "")
                        if content and content not in seen_contents:
                            seen_contents.add(content)
                            retrieved_segments.append(content)
                            new_added += 1
                    print(f"  -> Found {len(records)} records (Added {new_added} new unique segments).")
            else:
                print(f"  -> Error response: {response.status_code}")
        except Exception as e:
            print(f"  -> Connection error: {e}")

        raw_context = "\n\n".join(retrieved_segments)

        if not raw_context:
            decision = "NO"
        else:
            decision = grade_context_sufficiency(query, raw_context)
            print(f"  -> Sufficiency Grade: {decision}")

        if decision == "YES" or loop_idx == max_loops:
            break

        current_query = rewrite_search_query(query, raw_context)
        print(f"  -> Rewritten Query: '{current_query}'")

    final_context = "\n\n".join(retrieved_segments) if retrieved_segments else "No relevant context found in dataset."
    summary = generate_local_summary(query, final_context)
    print("\n=== Final Answer ===")
    print(summary)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 dify_search.py <query>")
        sys.exit(1)
    search_dify_knowledge(sys.argv[1])
