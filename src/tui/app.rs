use std::fs;
use std::path::Path;
use serde_json::Value;

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
        let meta_path = Path::new(".dify_sync_meta.json");
        if !meta_path.exists() {
            self.status_message = "Metadata file (.dify_sync_meta.json) not found.".to_string();
            // ダミー値をセットして空ではないことをTUIで見せる
            self.projects = vec![
                ProjectInfo {
                    name: "Lissue (Local)".to_string(),
                    synced_files: 0,
                    pending_files: 0,
                }
            ];
            return;
        }

        if let Ok(content) = fs::read_to_string(meta_path) {
            if let Ok(Value::Object(map)) = serde_json::from_str::<Value>(&content) {
                let total_files = map.len();
                self.projects = vec![
                    ProjectInfo {
                        name: "Lissue (Local)".to_string(),
                        synced_files: total_files,
                        pending_files: 0,
                    }
                ];
                self.status_message = format!("Loaded {} metadata sync entries.", total_files);
            } else {
                self.status_message = "Failed to parse JSON schema.".to_string();
            }
        } else {
            self.status_message = "Failed to read metadata file.".to_string();
        }
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
