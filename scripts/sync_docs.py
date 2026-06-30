import os
import sys
import time
import json
import logging
import hashlib
import requests
import argparse
import redis
import uuid
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class DifySyncHandler(FileSystemEventHandler):
    def __init__(self, watch_dir, api_base, api_key, dataset_id, meta_file=".dify_sync_meta.json", config_file=None):
        self.watch_dir = os.path.abspath(watch_dir)
        self.api_base = api_base.rstrip('/') if api_base else ""
        self.api_key = api_key
        self.dataset_id = dataset_id
        self.meta_file = meta_file
        self.config_file = config_file or os.path.join(self.watch_dir, "sync_config.json")
        self.config_mtime = 0
        self.project_configs = self.load_project_configs()
        self.metadata = self.load_metadata()
        self.file_hashes = {}
        for file_path, val in self.metadata.items():
            if isinstance(val, dict) and "hash" in val:
                self.file_hashes[file_path] = val["hash"]
                
        # サポートする拡張子定義
        self.supported_extensions = ('.md', '.pdf', '.docx', '.xlsx', '.xls', '.exls')
        
        # Redis接続初期化
        self.redis_enabled = False
        self.queue_name = "ragy:jobs"
        self.lock_key_prefix = "ragy:queued_projects"
        try:
            redis_host = os.environ.get("REDIS_HOST", "localhost")
            redis_port = int(os.environ.get("REDIS_PORT", 6379))
            redis_password = os.environ.get("REDIS_PASSWORD", "difyai123456")
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                password=redis_password,
                decode_responses=True,
                socket_timeout=2.0
            )
            self.redis_client.ping()
            self.redis_enabled = True
            logging.info("sync_docs.py connected to Redis successfully for queuing.")
        except Exception as e:
            if redis_host == "redis":
                logging.warning(f"sync_docs.py failed to connect to Redis host 'redis': {e}. Retrying with 'localhost'...")
                try:
                    redis_host = "localhost"
                    self.redis_client = redis.Redis(
                        host=redis_host,
                        port=redis_port,
                        password=redis_password,
                        decode_responses=True,
                        socket_timeout=2.0
                    )
                    self.redis_client.ping()
                    self.redis_enabled = True
                    logging.info("sync_docs.py connected to Redis successfully for queuing (fallback).")
                except Exception as fallback_err:
                    logging.error(f"sync_docs.py failed to connect to Redis on both 'redis' and 'localhost': {fallback_err}. Falling back to synchronous execution.")
            else:
                logging.error(f"sync_docs.py failed to connect to Redis: {e}. Falling back to synchronous execution.")

    def get_doc_id(self, file_path):
        val = self.metadata.get(file_path)
        if isinstance(val, dict):
            return val.get("doc_id")
        return val

    def get_saved_hash(self, file_path):
        val = self.metadata.get(file_path)
        if isinstance(val, dict):
            return val.get("hash")
        return None

    def load_project_configs(self):
        if os.path.exists(self.config_file):
            try:
                mtime = os.path.getmtime(self.config_file)
                self.config_mtime = mtime
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    logging.info(f"Loaded project configs: {self.config_file}")
                    return data.get("projects", {})
            except Exception as e:
                logging.error(f"Failed to load project configs from {self.config_file}: {e}")
        return {}

    def get_project_config(self, file_path):
        # Check if config file was modified and reload if necessary
        if os.path.exists(self.config_file):
            try:
                mtime = os.path.getmtime(self.config_file)
                if mtime != self.config_mtime:
                    self.project_configs = self.load_project_configs()
            except Exception as e:
                logging.error(f"Error checking config file modification: {e}")

        abs_path = os.path.abspath(file_path)
        try:
            rel_path = os.path.relpath(abs_path, self.watch_dir)
            parts = rel_path.split(os.sep)
            # サブフォルダに属している場合 (例: project_a/hello.md)
            if len(parts) > 1 and parts[0] != "..":
                proj_name = parts[0]
                if proj_name in self.project_configs:
                    return self.project_configs[proj_name]
        except Exception as e:
            logging.error(f"Error resolving project for {file_path}: {e}")

        # フォールバック (環境変数などのデフォルト設定)
        if self.api_key and self.dataset_id:
            return {
                "api_base": self.api_base,
                "api_key": self.api_key,
                "dataset_id": self.dataset_id
            }
        return None

    def load_metadata(self):
        if os.path.exists(self.meta_file):
            try:
                with open(self.meta_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logging.error(f"Failed to load metadata file: {e}")
        return {}

    def save_metadata(self):
        try:
            with open(self.meta_file, 'w', encoding='utf-8') as f:
                json.dump(self.metadata, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"Failed to save metadata file: {e}")

    def is_target_file(self, file_path):
        return file_path.lower().endswith(self.supported_extensions) and not ".parsed_cache" in file_path

    def get_parsed_cache_path(self, file_path):
        abs_path = os.path.abspath(file_path)
        rel_path = os.path.relpath(abs_path, self.watch_dir)
        cache_root = os.path.join(self.watch_dir, ".parsed_cache")
        cache_path = os.path.join(cache_root, rel_path + ".md")
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        return cache_path

    def get_file_hash(self, file_path):
        if not os.path.exists(file_path):
            return None
        hasher = hashlib.md5()
        try:
            with open(file_path, 'rb') as f:
                buf = f.read()
                hasher.update(buf)
            return hasher.hexdigest()
        except Exception as e:
            logging.error(f"Failed to calculate hash for {file_path}: {e}")
            return None

    def upload_file(self, file_path):
        config = self.get_project_config(file_path)
        if not config:
            logging.warning(f"No Dify config found for file: {file_path}. Skipping.")
            return

        api_base = config.get("api_base", "").rstrip('/')
        api_key = config.get("api_key")
        dataset_id = config.get("dataset_id")

        ext = os.path.splitext(file_path)[1].lower()
        actual_upload_path = file_path
        
        if ext != '.md':
            logging.info(f"Converting non-markdown file {file_path} to Markdown...")
            from document_parser import convert_document_to_markdown
            markdown_str = convert_document_to_markdown(file_path)
            cache_path = self.get_parsed_cache_path(file_path)
            with open(cache_path, 'w', encoding='utf-8') as f_cache:
                f_cache.write(markdown_str)
            actual_upload_path = cache_path

        filename = os.path.basename(actual_upload_path)
        url = f"{api_base}/datasets/{dataset_id}/document/create_by_file"
        headers = {"Authorization": f"Bearer {api_key}"}
        data = {
            "data": json.dumps({
                "indexing_technique": "high_quality",
                "process_rule": {
                    "mode": "automatic"
                }
            })
        }
        try:
            with open(actual_upload_path, 'rb') as f:
                files = {'file': (filename, f, 'text/plain')}
                response = requests.post(url, headers=headers, data=data, files=files, timeout=15)
            
            if response.status_code in (200, 201):
                res_data = response.json()
                doc_id = res_data.get("document", {}).get("id")
                if doc_id:
                    current_hash = self.get_file_hash(file_path)
                    self.metadata[file_path] = {
                        "doc_id": doc_id,
                        "hash": current_hash
                    }
                    self.save_metadata()
                    self.file_hashes[file_path] = current_hash
                    logging.info(f"Successfully uploaded: {filename} (source: {os.path.basename(file_path)}) to dataset {dataset_id} (ID: {doc_id})")
                else:
                    logging.warning(f"Uploaded {filename} but no document ID returned: {res_data}")
            else:
                logging.error(f"Failed to upload {filename} to dataset {dataset_id}: {response.status_code} - {response.text}")
        except Exception as e:
            logging.error(f"Exception during upload of {filename}: {e}")

    def update_file(self, file_path, doc_id):
        config = self.get_project_config(file_path)
        if not config:
            logging.warning(f"No Dify config found for file: {file_path}. Skipping.")
            return

        api_base = config.get("api_base", "").rstrip('/')
        api_key = config.get("api_key")
        dataset_id = config.get("dataset_id")

        ext = os.path.splitext(file_path)[1].lower()
        actual_upload_path = file_path
        
        if ext != '.md':
            logging.info(f"Re-converting modified non-markdown file {file_path} to Markdown...")
            from document_parser import convert_document_to_markdown
            markdown_str = convert_document_to_markdown(file_path)
            cache_path = self.get_parsed_cache_path(file_path)
            with open(cache_path, 'w', encoding='utf-8') as f_cache:
                f_cache.write(markdown_str)
            actual_upload_path = cache_path

        filename = os.path.basename(actual_upload_path)
        url = f"{api_base}/datasets/{dataset_id}/documents/{doc_id}/update_by_file"
        headers = {"Authorization": f"Bearer {api_key}"}
        data = {
            "data": json.dumps({
                "indexing_technique": "high_quality",
                "process_rule": {
                    "mode": "automatic"
                }
            })
        }
        try:
            with open(actual_upload_path, 'rb') as f:
                files = {'file': (filename, f, 'text/plain')}
                response = requests.post(url, headers=headers, data=data, files=files, timeout=15)
            
            if response.status_code in (200, 201):
                current_hash = self.get_file_hash(file_path)
                self.metadata[file_path] = {
                    "doc_id": doc_id,
                    "hash": current_hash
                }
                self.save_metadata()
                self.file_hashes[file_path] = current_hash
                logging.info(f"Successfully updated: {filename} (source: {os.path.basename(file_path)}) in dataset {dataset_id} (ID: {doc_id})")
            else:
                logging.error(f"Failed to update {filename} in dataset {dataset_id}: {response.status_code} - {response.text}")
        except Exception as e:
            logging.error(f"Exception during update of {filename}: {e}")

    def delete_file(self, file_path, doc_id):
        config = self.get_project_config(file_path)
        if not config:
            logging.warning(f"No Dify config found for file: {file_path}. Skipping.")
            return

        api_base = config.get("api_base", "").rstrip('/')
        api_key = config.get("api_key")
        dataset_id = config.get("dataset_id")

        filename = os.path.basename(file_path)
        url = f"{api_base}/datasets/{dataset_id}/documents/{doc_id}"
        headers = {"Authorization": f"Bearer {api_key}"}
        try:
            response = requests.delete(url, headers=headers, timeout=15)
            if response.status_code in (200, 204):
                if file_path in self.metadata:
                    del self.metadata[file_path]
                    self.save_metadata()
                if file_path in self.file_hashes:
                    del self.file_hashes[file_path]
                
                # キャッシュが存在する場合はキャッシュファイルも削除
                ext = os.path.splitext(file_path)[1].lower()
                if ext != '.md':
                    cache_path = self.get_parsed_cache_path(file_path)
                    if os.path.exists(cache_path):
                        try:
                            os.remove(cache_path)
                        except OSError as oe:
                            logging.warning(f"Failed to delete cache file {cache_path}: {oe}")
                            
                logging.info(f"Successfully deleted from Dify: {filename} from dataset {dataset_id}")
            else:
                logging.error(f"Failed to delete {filename} from dataset {dataset_id}: {response.status_code} - {response.text}")
        except Exception as e:
            logging.error(f"Exception during deletion of {filename}: {e}")

    def get_project_name(self, file_path):
        abs_path = os.path.abspath(file_path)
        try:
            rel_path = os.path.relpath(abs_path, self.watch_dir)
            parts = rel_path.split(os.sep)
            if len(parts) > 1 and parts[0] != "..":
                return parts[0]
        except Exception as e:
            logging.error(f"Error resolving project name for {file_path}: {e}")
        return None

    def enqueue_sync_job(self, project_name):
        if not self.redis_enabled:
            return False
            
        # 5秒のデバウンス（重複キューイング防止）
        lock_key = f"{self.lock_key_prefix}:{project_name}"
        try:
            if self.redis_client.set(lock_key, "1", ex=5, nx=True):
                job_id = str(uuid.uuid4())
                job = {
                    "id": job_id,
                    "type": "sync_docs",
                    "payload": {
                        "project_name": project_name
                    },
                    "created_at": int(time.time())
                }
                self.redis_client.rpush(self.queue_name, json.dumps(job))
                logging.info(f"Enqueued sync_docs job for project {project_name} (Job ID: {job_id})")
                return True
            else:
                logging.debug(f"Sync job for project {project_name} is already queued. Skipping duplicate.")
                return True
        except Exception as e:
            logging.error(f"Failed to enqueue job for project {project_name}: {e}")
            return False

    def on_created(self, event):
        if not event.is_directory and self.is_target_file(event.src_path):
            project_name = self.get_project_name(event.src_path)
            if project_name:
                logging.info(f"File created: {event.src_path}. Triggering async sync.")
                if not self.enqueue_sync_job(project_name):
                    # Redis接続がない場合は同期的にフォールバック実行
                    doc_id = self.get_doc_id(event.src_path)
                    if not doc_id:
                        self.upload_file(event.src_path)
            else:
                logging.warning(f"Created file {event.src_path} does not belong to a registered project.")

    def on_modified(self, event):
        if not event.is_directory and self.is_target_file(event.src_path):
            project_name = self.get_project_name(event.src_path)
            if project_name:
                logging.info(f"File modified: {event.src_path}. Triggering async sync.")
                if not self.enqueue_sync_job(project_name):
                    doc_id = self.get_doc_id(event.src_path)
                    if doc_id:
                        self.update_file(event.src_path, doc_id)
                    else:
                        self.upload_file(event.src_path)

    def on_deleted(self, event):
        if not event.is_directory and self.is_target_file(event.src_path):
            project_name = self.get_project_name(event.src_path)
            if project_name:
                logging.info(f"File deleted: {event.src_path}. Triggering async sync.")
                if not self.enqueue_sync_job(project_name):
                    doc_id = self.get_doc_id(event.src_path)
                    if doc_id:
                        self.delete_file(event.src_path, doc_id)

    def sync_project_once(self, project_name):
        config = self.project_configs.get(project_name)
        if not config:
            raise ValueError(f"No Dify config found for project: {project_name}. Please run 'ragy init' first.")

        project_dir = os.path.join(self.watch_dir, project_name)
        if not os.path.exists(project_dir):
            raise FileNotFoundError(f"Project directory does not exist: {project_dir}")

        logging.info(f"Starting one-shot sync for project: {project_name} in {project_dir}")

        local_files = []
        for root, dirs, files in os.walk(project_dir):
            # 中間キャッシュディレクトリは無視する
            if ".parsed_cache" in dirs:
                dirs.remove(".parsed_cache")
            for file in files:
                file_path = os.path.join(root, file)
                if self.is_target_file(file_path):
                    local_files.append(os.path.abspath(file_path))

        meta_project_files = []
        for file_path in list(self.metadata.keys()):
            if os.path.abspath(file_path).startswith(os.path.abspath(project_dir)):
                meta_project_files.append(file_path)

        # 1. アップロードおよび更新処理
        for file_path in local_files:
            doc_id = self.get_doc_id(file_path)
            current_hash = self.get_file_hash(file_path)
            saved_hash = self.get_saved_hash(file_path)

            if not doc_id:
                logging.info(f"File not registered. Uploading: {file_path}")
                self.upload_file(file_path)
            elif current_hash != saved_hash:
                logging.info(f"File changed. Updating: {file_path}")
                self.update_file(file_path, doc_id)
            else:
                logging.info(f"File unchanged. Skipping: {file_path}")

        # 2. ローカルに存在せず、メタデータにあるファイルをDifyから削除
        for file_path in meta_project_files:
            if file_path not in local_files:
                doc_id = self.get_doc_id(file_path)
                if doc_id:
                    logging.info(f"File deleted locally. Deleting from Dify: {file_path}")
                    self.delete_file(file_path, doc_id)

def main():
    parser = argparse.ArgumentParser(description="Sync local markdown documents to Dify dataset.")
    parser.add_argument("--sync-project", help="Sync a specific project and exit (one-shot mode).")
    args = parser.parse_args()

    watch_dir = os.environ.get("DIFY_SYNC_DIR", "./docs")
    api_base = os.environ.get("DIFY_API_BASE", "http://localhost:8080/v1")
    api_key = os.environ.get("DIFY_DATASET_API_KEY")
    dataset_id = os.environ.get("DIFY_DATASET_ID")

    if not os.path.exists(watch_dir):
        os.makedirs(watch_dir)

    event_handler = DifySyncHandler(watch_dir, api_base, api_key, dataset_id)

    if args.sync_project:
        try:
            event_handler.sync_project_once(args.sync_project)
        except Exception as e:
            logging.error(f"Sync project failed: {e}")
            sys.exit(1)
        return

    observer = Observer()
    observer.schedule(event_handler, path=watch_dir, recursive=True)
    observer.start()
    logging.info(f"Started monitoring folder: {watch_dir} (recursive=True)")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

if __name__ == "__main__":
    main()
