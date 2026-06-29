import os
import sys
import json
import time
import asyncio
import logging
import requests
import redis
import dotenv

# プロジェクトルートとscriptsのパスをインポート検索パスに追加
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(script_dir)
sys.path.append(os.path.dirname(script_dir))

# 環境変数のロード
dotenv.load_dotenv(os.path.join(os.path.dirname(script_dir), ".env"))

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(os.path.dirname(script_dir), "logs/worker.log"), encoding='utf-8')
    ]
)

# 各種スクリプトのインポート
try:
    from sync_docs import DifySyncHandler
    from agent_healer import heal_code
except ImportError as e:
    logging.error(f"Failed to import modules: {e}")
    sys.exit(1)

# Redis接続
REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", "difyai123456")
QUEUE_NAME = "ragy:jobs"

try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        password=REDIS_PASSWORD,
        decode_responses=True,
        socket_timeout=2.0
    )
    redis_client.ping()
    logging.info(f"Worker connected to Redis successfully at {REDIS_HOST}:{REDIS_PORT}")
except Exception as e:
    if REDIS_HOST == "redis":
        logging.warning(f"Failed to connect to Redis host 'redis': {e}. Retrying with 'localhost'...")
        try:
            REDIS_HOST = "localhost"
            redis_client = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                password=REDIS_PASSWORD,
                decode_responses=True,
                socket_timeout=2.0
            )
            redis_client.ping()
            logging.info(f"Worker connected to Redis successfully at {REDIS_HOST}:{REDIS_PORT} (fallback)")
        except Exception as fallback_err:
            logging.critical(f"Worker failed to connect to Redis on both 'redis' and 'localhost': {fallback_err}")
            sys.exit(1)
    else:
        logging.critical(f"Worker failed to connect to Redis: {e}")
        sys.exit(1)

def run_sync_docs(project_name):
    logging.info(f"Starting async sync_docs job for project: {project_name}")
    watch_dir = os.environ.get("DIFY_SYNC_DIR", "./docs")
    api_base = os.environ.get("DIFY_API_BASE", "http://localhost:8080/v1")
    api_key = os.environ.get("DIFY_DATASET_API_KEY")
    dataset_id = os.environ.get("DIFY_DATASET_ID")
    
    # パスが絶対パスで解決できるように調整
    repo_root = os.path.dirname(script_dir)
    watch_dir = os.path.join(repo_root, "docs")
    
    try:
        handler = DifySyncHandler(watch_dir, api_base, api_key, dataset_id)
        handler.sync_project_once(project_name)
        logging.info(f"Finished sync_docs job for project: {project_name}")
    except Exception as e:
        logging.error(f"Error during sync_docs job for project {project_name}: {e}")

async def run_healer(file_path, error_log):
    logging.info(f"Starting async healer job for file: {file_path}")
    try:
        success = await heal_code(file_path, error_log)
        if success:
            logging.info(f"Healer job succeeded for: {file_path}")
        else:
            logging.error(f"Healer job failed for: {file_path}")
    except Exception as e:
        logging.error(f"Error during healer job for {file_path}: {e}")

async def process_job(job_data):
    job_type = job_data.get("type")
    payload = job_data.get("payload", {})
    job_id = job_data.get("id", "unknown")
    
    logging.info(f"Processing job {job_id} [Type: {job_type}]")
    
    if job_type == "sync_docs":
        project_name = payload.get("project_name")
        if project_name:
            # 同期処理はブロッキングIOのため、executor等を利用して非同期イベントループを妨げないように実行
            await asyncio.to_thread(run_sync_docs, project_name)
        else:
            logging.error(f"Invalid payload for sync_docs job {job_id}: missing project_name")
            
    elif job_type == "run_healer":
        file_path = payload.get("file_path")
        error_log = payload.get("error_log")
        if file_path and error_log:
            await run_healer(file_path, error_log)
        else:
            logging.error(f"Invalid payload for run_healer job {job_id}: missing file_path or error_log")
            
    else:
        logging.error(f"Unknown job type: {job_type}")

async def worker_loop():
    logging.info("Starting worker loop waiting for jobs...")
    while True:
        try:
            # blpop はブロッキング処理なので、非同期に実行するため to_thread を利用
            # タイムアウトを1秒にして定期的にイベントループに制御を戻す
            result = await asyncio.to_thread(
                redis_client.blpop, QUEUE_NAME, timeout=1
            )
            if result:
                _, job_json = result
                try:
                    job_data = json.loads(job_json)
                    await process_job(job_data)
                except json.JSONDecodeError:
                    logging.error(f"Failed to parse job JSON: {job_json}")
                except Exception as e:
                    logging.error(f"Error processing job: {e}")
            else:
                # タイムアウト時は少しだけ待つ
                await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            logging.info("Worker loop cancelled. Exiting...")
            break
        except Exception as e:
            logging.error(f"Error in worker loop: {e}")
            await asyncio.sleep(2)

def main():
    pid_file = os.path.join(os.path.dirname(script_dir), "logs/worker.pid")
    os.makedirs(os.path.dirname(pid_file), exist_ok=True)
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))
        
    try:
        asyncio.run(worker_loop())
    finally:
        if os.path.exists(pid_file):
            try:
                os.remove(pid_file)
            except OSError:
                pass

if __name__ == "__main__":
    main()
