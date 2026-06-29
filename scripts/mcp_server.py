from mcp.server.fastmcp import FastMCP
import requests
import os
import json
import logging
import redis
import math
import uuid
from langsmith import traceable

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

mcp = FastMCP("DifyRAGServer")

# Redis接続初期化
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "difyai123456")

try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        decode_responses=True,
        socket_timeout=2.0
    )
    redis_client.ping()
    logging.info(f"Connected to Redis successfully at {REDIS_HOST}:{REDIS_PORT}")
    redis_enabled = True
except Exception as e:
    logging.error(f"Failed to connect to Redis: {e}. Semantic caching will be disabled.")
    redis_enabled = False

def get_current_project():
    env_proj = os.environ.get("CURRENT_PROJECT")
    if env_proj:
        return env_proj

    continue_config = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".continue/config.json")
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
            
    return None

def get_dify_config_for_current_project(project_name=None):
    sync_config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs/sync_config.json")
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

# コサイン類似度の計算（NumPy非依存）
def cosine_similarity(v1, v2):
    if not v1 or not v2 or len(v1) != len(v2):
        return 0.0
    dot_product = sum(a * b for a, b in zip(v1, v2))
    norm_a = math.sqrt(sum(a * a for a in v1))
    norm_b = math.sqrt(sum(b * b for b in v2))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)

# LiteLLM Proxy経由でクエリをベクトル化（共通モデルプール統一）
LITELLM_BASE = os.environ.get("LITELLM_BASE", "http://localhost:4000")
LITELLM_KEY = os.environ.get("LITELLM_KEY", "sk-1234")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "multilingual-e5-large")

def get_query_embedding(query: str) -> list:
    url = f"{LITELLM_BASE}/v1/embeddings"
    headers = {
        "Authorization": f"Bearer {LITELLM_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": EMBEDDING_MODEL,
        "input": query
    }
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=5)
        if response.status_code == 200:
            data = response.json()
            embeddings = data.get("data", [])
            if embeddings:
                return embeddings[0].get("embedding", [])
            return []
        else:
            logging.error(f"LiteLLM embeddings API returned status {response.status_code}: {response.text}")
    except Exception as e:
        logging.error(f"Failed to get embeddings from LiteLLM: {e}")
    return []

# セマンティックキャッシュの照会
def check_semantic_cache(project_name: str, query_vector: list, threshold: float = 0.95) -> str:
    if not redis_enabled or not query_vector:
        return None

    project = project_name or 'default'
    pattern = f"mcp_cache:{project}:*"
    
    try:
        cursor = 0
        while True:
            cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=100)
            for key in keys:
                data_str = redis_client.get(key)
                if not data_str:
                    continue
                try:
                    data = json.loads(data_str)
                    cache_vector = data.get("embedding", [])
                    if not cache_vector:
                        continue
                    
                    similarity = cosine_similarity(query_vector, cache_vector)
                    if similarity >= threshold:
                        logging.info(f"[Semantic Cache HIT] Key: {key}, Similarity: {similarity:.4f}")
                        return data.get("result")
                except Exception as ex:
                    logging.error(f"Failed to parse cache data for key {key}: {ex}")
            if cursor == 0:
                break
    except Exception as e:
        logging.error(f"Error checking semantic cache: {e}")
    
    return None

# セマンティックキャッシュの保存
def save_semantic_cache(project_name: str, query: str, query_vector: list, result: str, ttl: int = 86400):
    if not redis_enabled or not query_vector or not result:
        return

    project = project_name or 'default'
    cache_id = str(uuid.uuid4())
    key = f"mcp_cache:{project}:{cache_id}"
    
    data = {
        "query": query,
        "embedding": query_vector,
        "result": result
    }
    
    try:
        redis_client.set(key, json.dumps(data, ensure_ascii=False), ex=ttl)
        logging.info(f"[Semantic Cache Save] Saved key: {key}")
    except Exception as e:
        logging.error(f"Failed to save semantic cache: {e}")

@mcp.tool()
@traceable(run_type="retriever", name="search_dify_knowledge")
def search_dify_knowledge(query: str) -> str:
    """
    Search documents in Dify RAG knowledge base.
    
    Args:
        query: The search text query.
    """
    current_proj = get_current_project()
    
    # 1. セマンティックキャッシュのチェック
    query_vector = None
    if redis_enabled:
        logging.info(f"Generating embeddings for semantic cache lookup: '{query}'")
        query_vector = get_query_embedding(query)
        if query_vector:
            cached_result = check_semantic_cache(current_proj, query_vector)
            if cached_result:
                return cached_result

    # 2. キャッシュミス時の通常検索処理
    config = get_dify_config_for_current_project(current_proj)

    if not config:
        return f"Error: No Dify Dataset configuration found. (Current project: {current_proj})"

    api_base = config.get("api_base", "").rstrip('/')
    dataset_api_key = config.get("api_key")  # 従来のデータセットAPIキー
    workflow_api_key = config.get("workflow_api_key") or os.environ.get("DIFY_RAG_WORKFLOW_API_KEY")
    dataset_id = config.get("dataset_id")

    # 2.1 ワークフローAPIが利用可能な場合は Agentic RAG を優先実行
    if workflow_api_key:
        logging.info(f"Initiating Agentic RAG search via Dify Workflow for project '{current_proj}'...")
        workflow_url = f"{api_base}/workflows/run"
        workflow_headers = {
            "Authorization": f"Bearer {workflow_api_key}",
            "Content-Type": "application/json"
        }
        workflow_payload = {
            "inputs": {
                "query": query
            },
            "response_mode": "blocking",
            "user": "mcp-agent"
        }
        
        try:
            response = requests.post(workflow_url, headers=workflow_headers, json=workflow_payload, timeout=20)
            if response.status_code == 200:
                res_data = response.json()
                outputs = res_data.get("data", {}).get("outputs", {})
                # DSL定義で outputs.result にナレッジ取得結果が入る
                records = outputs.get("result", [])
                
                # もし outputs.result が文字列（LLM要約等）や空だった場合、リストでない場合も考慮してパース
                if isinstance(records, list) and records:
                    results = []
                    for record in records:
                        if isinstance(record, dict):
                            content = record.get("content", "")
                            score = record.get("score", 0.0)
                            results.append(f"Content (Score: {score}):\n{content}\n")
                        else:
                            results.append(str(record))
                    
                    final_result = f"[Project: {current_proj or 'default'} (Agentic RAG)] Search Results:\n" + "\n".join(results)
                    
                    # キャッシュの保存
                    if redis_enabled and query_vector:
                        save_semantic_cache(current_proj, query, query_vector, final_result)
                        
                    return final_result
                elif isinstance(records, str) and records:
                    # テキストとして直接結果が返るパターン
                    final_result = f"[Project: {current_proj or 'default'} (Agentic RAG)] Search Results:\n{records}"
                    if redis_enabled and query_vector:
                        save_semantic_cache(current_proj, query, query_vector, final_result)
                    return final_result
                else:
                    logging.warning("Dify Workflow completed but returned empty result list. Falling back to Dataset retrieval...")
            else:
                logging.error(f"Dify Workflow API responded with {response.status_code}: {response.text}. Falling back...")
        except Exception as e:
            logging.error(f"Exception during Dify Workflow search: {e}. Falling back...")

    # 2.2 フォールバック: 従来のデータセット retrieve API による検索
    if not dataset_api_key or not dataset_id:
        return f"Error: DIFY_DATASET_API_KEY or DIFY_DATASET_ID not configured for project '{current_proj}'."

    url = f"{api_base}/datasets/{dataset_id}/retrieve"
    headers = {
        "Authorization": f"Bearer {dataset_api_key}",
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
                final_result = f"No matching documents found in dataset {dataset_id} for query '{query}'."
            else:
                results = []
                for record in records:
                    segment = record.get("segment", {})
                    content = segment.get("content", "")
                    score = record.get("score", 0.0)
                    results.append(f"Content (Score: {score}):\n{content}\n")
                final_result = f"[Project: {current_proj or 'default'}] Search Results:\n" + "\n".join(results)
            
            # キャッシュの保存
            if redis_enabled and query_vector:
                save_semantic_cache(current_proj, query, query_vector, final_result)
                
            return final_result
        else:
            return f"Error: Dify API responded with status {response.status_code}: {response.text}"
    except Exception as e:
        return f"Exception during Dify knowledge base search: {str(e)}"

if __name__ == "__main__":
    mcp.run()
