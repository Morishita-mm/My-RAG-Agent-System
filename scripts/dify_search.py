import sys
import json
import os
import requests

def get_current_project():
    continue_config = "./.continue/config.json"
    if os.path.exists(continue_config):
        try:
            with open(continue_config, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("customSettings", {}).get("current_project")
        except Exception:
            pass
    return None

def get_project_config(project_id):
    sync_config = "./docs/sync_config.json"
    if os.path.exists(sync_config):
        try:
            with open(sync_config, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("projects", {}).get(project_id)
        except Exception:
            pass
    return None

def search_dify_knowledge(query):
    project_id = get_current_project()
    if not project_id:
        print("Error: No active project found in .continue/config.json")
        sys.exit(1)
        
    config = get_project_config(project_id)
    if not config:
        print(f"Error: No configuration found for project '{project_id}' in docs/sync_config.json")
        sys.exit(1)
        
    api_base = config.get("api_base", "").rstrip('/')
    api_key = config.get("api_key")
    dataset_id = config.get("dataset_id")
    
    if not api_key or not dataset_id:
        print(f"Error: Missing api_key or dataset_id for project '{project_id}'")
        sys.exit(1)
        
    url = f"{api_base}/datasets/{dataset_id}/retrieve"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "query": query,
        "retrieval_model": {
            "search_method": "hybrid_search",
            "top_k": 3,
            "reranking_enable": False,
            "score_threshold_enabled": False
        }
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
            print(f"Error: Dify API returned status code {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Error during search: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 dify_search.py <query>")
        sys.exit(1)
    search_dify_knowledge(sys.argv[1])
