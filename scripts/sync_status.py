import os
import sys
import json
import hashlib

def get_file_hash(file_path):
    if not os.path.exists(file_path):
        return None
    hasher = hashlib.md5()
    try:
        with open(file_path, 'rb') as f:
            buf = f.read()
            hasher.update(buf)
        return hasher.hexdigest()
    except Exception as e:
        return None

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    
    config_path = os.path.join(project_root, "docs/sync_config.json")
    meta_path = os.path.join(project_root, ".dify_sync_meta.json")
    watch_dir = os.path.join(project_root, "docs")
    
    if not os.path.exists(config_path):
        print("\n=== Document Sync Status ===")
        print("No RAG projects configured yet.")
        return
        
    with open(config_path, "r", encoding="utf-8") as f:
        config_data = json.load(f)
    projects = config_data.get("projects", {})
    
    meta_data = {}
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as f:
            meta_data = json.load(f)
            
    supported_extensions = ('.md', '.pdf', '.docx', '.xlsx', '.xls', '.exls')
    
    print("\n=== Document Sync Status ===")
    if not projects:
        print("No active projects found in config.")
        return
        
    for project_name, proj_conf in projects.items():
        dataset_id = proj_conf.get("dataset_id")
        project_dir = os.path.join(watch_dir, project_name)
        print(f"\nProject: {project_name} (Dataset ID: {dataset_id})")
        
        if not os.path.exists(project_dir):
            print("  [Warning] Project folder does not exist locally.")
            continue
            
        local_files = []
        for root, dirs, files in os.walk(project_dir):
            if ".parsed_cache" in dirs:
                dirs.remove(".parsed_cache")
            for file in files:
                if file.lower().endswith(supported_extensions):
                    local_files.append(os.path.abspath(os.path.join(root, file)))
                    
        # メタデータのうち、このプロジェクトに属するもの
        meta_project_files = {}
        for file_path, info in meta_data.items():
            abs_meta_path = os.path.abspath(file_path)
            if abs_meta_path.startswith(os.path.abspath(project_dir)):
                meta_project_files[abs_meta_path] = info
                
        # 1. ローカルに存在するファイルのステータス
        if not local_files and not meta_project_files:
            print("  No documents found.")
            continue
            
        for file_path in sorted(local_files):
            rel_path = os.path.relpath(file_path, project_root)
            meta_info = meta_project_files.get(file_path)
            
            if not meta_info:
                print(f"  [NEW]       {rel_path}")
            else:
                current_hash = get_file_hash(file_path)
                saved_hash = meta_info.get("hash")
                doc_id = meta_info.get("doc_id")
                if current_hash != saved_hash:
                    print(f"  [MODIFIED]  {rel_path} (ID: {doc_id})")
                else:
                    print(f"  [SYNCED]    {rel_path} (ID: {doc_id})")
                    
        # 2. メタデータにはあるが、ローカルで削除されたファイル
        for file_path, meta_info in sorted(meta_project_files.items()):
            if file_path not in local_files:
                rel_path = os.path.relpath(file_path, project_root)
                doc_id = meta_info.get("doc_id")
                print(f"  [DELETED]   {rel_path} (Pending Removal, ID: {doc_id})")

if __name__ == "__main__":
    main()
