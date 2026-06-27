from mcp.server.fastmcp import FastMCP
import requests
import os
import json
import logging

mcp = FastMCP("DifyRAGServer")

def get_current_project():
    continue_config = os.path.join(os.path.dirname(__file__), ".continue/config.json")
    if os.path.exists(continue_config):
        try:
            with open(continue_config, 'r', encoding='utf-8') as f:
                data = json.load(f)
                current = data.get("customSettings", {}).get("current_project")
                if not current:
                    current = data.get("current_project")
                if current:
                    return current
        except Exception as e:
            logging.error(f"Failed to read continue config: {e}")
            
    env_proj = os.environ.get("CURRENT_PROJECT")
    if env_proj:
        return env_proj

    return None

def get_dify_config_for_current_project(project_name=None):
    sync_config_path = os.path.join(os.path.dirname(__file__), "docs/sync_config.json")
    if project_name and os.path.exists(sync_config_path):
        try:
            with open(sync_config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                projects = data.get("projects", {})
                if project_name in projects:
                    return projects[project_name]
        except Exception as e:
            logging.error(f"Failed to read sync config: {e}")

    api_base = os.environ.get("DIFY_API_BASE", "http://localhost:8080/v1")
    api_key = os.environ.get("DIFY_DATASET_API_KEY")
    dataset_id = os.environ.get("DIFY_DATASET_ID")
    
    if api_key and dataset_id:
        return {
            "api_base": api_base,
            "api_key": api_key,
            "dataset_id": dataset_id
        }
    return None

@mcp.tool()
def search_dify_knowledge(query: str) -> str:
    """
    Search documents in Dify RAG knowledge base.
    
    Args:
        query: The search text query.
    """
    current_proj = get_current_project()
    config = get_dify_config_for_current_project(current_proj)

    if not config:
        return f"Error: No Dify Dataset configuration found. (Current project: {current_proj})"

    api_base = config.get("api_base", "").rstrip('/')
    api_key = config.get("api_key")
    dataset_id = config.get("dataset_id")

    if not api_key or not dataset_id:
        return f"Error: DIFY_DATASET_API_KEY or DIFY_DATASET_ID not configured for project '{current_proj}'."

    url = f"{api_base}/datasets/{dataset_id}/retrieve"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "query": query,
        "retrieval_model": {
            "search_method": "keyword_search",
            "top_k": 5,
            "reranking_enable": False,
            "score_threshold_enabled": False
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        if response.status_code == 200:
            res_data = response.json()
            records = res_data.get("records", [])
            if not records:
                return f"No matching documents found in dataset {dataset_id} for query '{query}'."
            
            results = []
            for record in records:
                segment = record.get("segment", {})
                content = segment.get("content", "")
                score = record.get("score", 0.0)
                results.append(f"Content (Score: {score}):\n{content}\n")
            return f"[Project: {current_proj or 'default'}] Search Results:\n" + "\n".join(results)
        else:
            return f"Error: Dify API responded with status {response.status_code}: {response.text}"
    except Exception as e:
        return f"Exception during Dify knowledge base search: {str(e)}"

if __name__ == "__main__":
    mcp.run()
