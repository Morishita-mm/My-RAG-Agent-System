use std::fs;
use std::path::Path;
use serde_json::Value;
use std::collections::HashMap;

#[derive(Clone)]
pub struct ProjectInfo {
    pub name: String,
    pub synced_files: usize,
    pub pending_files: usize,
}

#[allow(dead_code)]
pub struct App {
    pub projects: Vec<ProjectInfo>,
    pub selected_project_index: usize,
    pub exact_cache_count: usize,
    pub semantic_cache_count: usize,
    pub hit_rate: f64,
    pub logs: Vec<String>,
    pub active_tab: usize,
    pub should_quit: bool,
    pub status_message: String,
    pub redis_connected: bool,
}

impl App {
    pub fn new() -> Self {
        Self {
            projects: Vec::new(),
            selected_project_index: 0,
            exact_cache_count: 0,
            semantic_cache_count: 0,
            hit_rate: 87.5,
            logs: vec![
                "Press 'S' to run sync_docs.py".to_string(),
                "Press 'C' to clear active Redis caches".to_string(),
                "Press 'Tab' to switch views, 'Q' to exit.".to_string(),
            ],
            active_tab: 0,
            should_quit: false,
            status_message: "Initializing TUI...".to_string(),
            redis_connected: false,
        }
    }

    pub fn add_log(&mut self, log: String) {
        self.logs.push(log);
        if self.logs.len() > 30 {
            self.logs.remove(0);
        }
    }

    pub fn load_project_metadata(&mut self) {
        let config_path = Path::new("docs/sync_config.json");
        let meta_path = Path::new(".dify_sync_meta.json");

        if !config_path.exists() {
            self.status_message = "No config docs/sync_config.json found.".to_string();
            return;
        }

        // 1. メタデータのロード
        let mut meta_map: HashMap<String, Value> = HashMap::new();
        if meta_path.exists() {
            if let Ok(content) = fs::read_to_string(meta_path) {
                if let Ok(Value::Object(map)) = serde_json::from_str::<Value>(&content) {
                    for (k, v) in map {
                        meta_map.insert(k, v);
                    }
                }
            }
        }

        // 2. 設定ファイルロード ＆ 各プロジェクトのフォルダスキャン
        let mut detected_projects = Vec::new();
        if let Ok(content) = fs::read_to_string(config_path) {
            if let Ok(Value::Object(map)) = serde_json::from_str::<Value>(&content) {
                if let Some(Value::Object(projects_obj)) = map.get("projects") {
                    for (project_name, _) in projects_obj {
                        let project_dir = Path::new("docs").join(project_name);
                        
                        let mut local_files = Vec::new();
                        if project_dir.exists() {
                            let mut dirs_to_visit = vec![project_dir.clone()];
                            let supported_extensions = [".md", ".pdf", ".docx", ".xlsx", ".xls", ".exls", ".png", ".jpg", ".jpeg"];
                            
                            while let Some(dir) = dirs_to_visit.pop() {
                                if let Ok(entries) = fs::read_dir(dir) {
                                    for entry in entries.flatten() {
                                        let path = entry.path();
                                        if path.is_dir() {
                                            if let Some(dir_name) = path.file_name().and_then(|n| n.to_str()) {
                                                if dir_name != ".parsed_cache" {
                                                    dirs_to_visit.push(path);
                                                }
                                            }
                                        } else if path.is_file() {
                                            if let Some(ext) = path.extension().and_then(|e| e.to_str()) {
                                                let dot_ext = format!(".{}", ext.to_lowercase());
                                                if supported_extensions.contains(&dot_ext.as_str()) {
                                                    if let Ok(abs_path) = fs::canonicalize(&path) {
                                                        local_files.push(abs_path.to_string_lossy().to_string());
                                                    }
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        // 同期ステータスカウント
                        let mut synced_files = 0;
                        let mut pending_files = 0;

                        for local_file in &local_files {
                            let mut found = false;
                            for (meta_path_str, _) in &meta_map {
                                if let Ok(abs_meta_path) = fs::canonicalize(Path::new(meta_path_str)) {
                                    if abs_meta_path.to_string_lossy().to_string() == *local_file {
                                        synced_files += 1;
                                        found = true;
                                        break;
                                    }
                                }
                            }
                            if !found {
                                pending_files += 1;
                            }
                        }

                        detected_projects.push(ProjectInfo {
                            name: project_name.clone(),
                            synced_files,
                            pending_files,
                        });
                    }
                }
            }
        }

        detected_projects.sort_by(|a, b| a.name.cmp(&b.name));
        self.projects = detected_projects;
        self.status_message = format!("Loaded {} projects successfully.", self.projects.len());
    }

    pub async fn fetch_redis_stats(&mut self) {
        let client_res = redis::Client::open("redis://:difyai123456@127.0.0.1:6379");
        match client_res {
            Ok(client) => {
                if let Ok(mut con) = client.get_tokio_connection().await {
                    self.redis_connected = true;
                    
                    let exact_keys: Vec<String> = redis::cmd("KEYS")
                        .arg("mcp_exact_cache:*")
                        .query_async(&mut con)
                        .await
                        .unwrap_or(Vec::new());
                    self.exact_cache_count = exact_keys.len();

                    let semantic_keys: Vec<String> = redis::cmd("KEYS")
                        .arg("mcp_cache:*")
                        .query_async(&mut con)
                        .await
                        .unwrap_or(Vec::new());
                    self.semantic_cache_count = semantic_keys.len();
                } else {
                    self.redis_connected = false;
                }
            }
            Err(_) => {
                self.redis_connected = false;
            }
        }
    }

    pub async fn clear_project_cache(&mut self) {
        let client_res = redis::Client::open("redis://:difyai123456@127.0.0.1:6379");
        if let Ok(client) = client_res {
            if let Ok(mut con) = client.get_tokio_connection().await {
                let exact_keys: Vec<String> = redis::cmd("KEYS")
                    .arg("mcp_exact_cache:*")
                    .query_async(&mut con)
                    .await
                    .unwrap_or(Vec::new());
                let mut deleted_count = 0;
                for key in exact_keys {
                    let _: () = redis::cmd("DEL").arg(&key).query_async(&mut con).await.unwrap_or(());
                    deleted_count += 1;
                }

                let semantic_keys: Vec<String> = redis::cmd("KEYS")
                    .arg("mcp_cache:*")
                    .query_async(&mut con)
                    .await
                    .unwrap_or(Vec::new());
                for key in semantic_keys {
                    let _: () = redis::cmd("DEL").arg(&key).query_async(&mut con).await.unwrap_or(());
                    deleted_count += 1;
                }
                
                self.add_log(format!("Cleared {} Redis cache keys.", deleted_count));
                self.exact_cache_count = 0;
                self.semantic_cache_count = 0;
            } else {
                self.add_log("Redis connection refused during clear.".to_string());
            }
        }
    }
}
