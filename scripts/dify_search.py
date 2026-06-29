import sys
import json
import os
import requests


def get_current_project():
    local_config = ".rag-project"
    if os.path.exists(local_config):
        with open(local_config, "r") as f:
            return f.read().strip()

    return os.environ.get("PROJECT_ID", os.path.basename(os.getcwd()))


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

    # 2. 従来のデータセットAPIへのフォールバック
    if not dataset_api_key or not dataset_id:
        print(f"Error: Missing api_key or dataset_id for project '{project_id}'")
        sys.exit(1)

    url = f"{api_base}/datasets/{dataset_id}/retrieve"
    headers = {
        "Authorization": f"Bearer {dataset_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "query": query,
        "retrieval_model": {
            "search_method": "hybrid_search",
            "top_k": 3,
            "reranking_enable": False,
            "score_threshold_enabled": False,
        },
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code == 200:
            records = response.json().get("records", [])
            if not records:
                print("No matching knowledge found.")
                return

            print(f"=== Knowledge search results for [Project: {project_id}] ===")
            for idx, rec in enumerate(records, 1):
                segment = rec.get("segment", {})
                score = rec.get("score", 0.0)
                content = segment.get("content", "")
                doc_name = segment.get("document", {}).get("name", "Unknown")
                print(f"\n[{idx}] Document: {doc_name} (Score: {score:.4f})")
                print("-" * 50)
                print(content.strip())
                print("-" * 50)
        else:
            print(
                f"Error: Dify API returned status code {response.status_code} - {response.text}"
            )
    except Exception as e:
        print(f"Error during search: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 dify_search.py <query>")
        sys.exit(1)
    search_dify_knowledge(sys.argv[1])
