use std::fs;
use serde_json::Value;
use std::collections::HashMap;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TuiMode {
    ProjectList,
    ConfirmDelete,
    Chat,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ChatFocus {
    Input,
    History,
}

#[derive(Clone)]
pub struct ChatMessage {
    pub is_user: bool,
    pub content: String,
}

#[derive(Clone)]
pub struct ProjectInfo {
    pub name: String,
    pub dataset_id: String,
    pub api_key: String,
    pub api_base: String,
    pub synced_files: usize,
    pub pending_files: usize,
}

use std::path::PathBuf;

pub(crate) fn get_project_root() -> PathBuf {
    if let Ok(exe_path) = std::env::current_exe() {
        if let Ok(real_path) = std::fs::canonicalize(exe_path) {
            let mut current = real_path.parent();
            while let Some(path) = current {
                if path.join("Cargo.toml").exists() {
                    return path.to_path_buf();
                }
                current = path.parent();
            }
        }
    }
    std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
}

#[allow(dead_code)]
pub struct App {
    pub project_root: PathBuf,
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
    
    // NotebookLM / Vim 拡張用
    pub mode: TuiMode,
    pub chat_history: Vec<ChatMessage>,
    pub input_buffer: String,
    pub is_loading_chat: bool,
    pub chat_focus: ChatFocus,
    pub chat_scroll_offset: usize,
}

fn log_tui_debug(msg: &str) {
    let project_root = get_project_root();
    let log_path = project_root.join("logs/tui_debug.log");
    if let Some(parent) = log_path.parent() {
        let _ = std::fs::create_dir_all(parent);
    }
    if let Ok(mut file) = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&log_path)
    {
        let local_time = chrono::Local::now().format("%Y-%m-%d %H:%M:%S");
        let _ = std::io::Write::write_all(&mut file, format!("[{}] {}\n", local_time, msg).as_bytes());
    }
}

impl App {
    pub fn new() -> Self {
        let project_root = get_project_root();
        Self {
            project_root,
            projects: Vec::new(),
            selected_project_index: 0,
            exact_cache_count: 0,
            semantic_cache_count: 0,
            hit_rate: 87.5,
            logs: vec![
                "=== Keybindings ===".to_string(),
                "Press 'j' / 'k' to move. Enter to start RAG Chat.".to_string(),
                "Press 'd' to delete the selected knowledge base.".to_string(),
                "Press 'S' to sync, 'C' to clear Redis cache.".to_string(),
            ],
            active_tab: 0,
            should_quit: false,
            status_message: "Initializing TUI...".to_string(),
            redis_connected: false,
            mode: TuiMode::ProjectList,
            chat_history: Vec::new(),
            input_buffer: String::new(),
            is_loading_chat: false,
            chat_focus: ChatFocus::Input,
            chat_scroll_offset: 0,
        }
    }

    pub fn add_log(&mut self, log: String) {
        self.logs.push(log);
        if self.logs.len() > 30 {
            self.logs.remove(0);
        }
    }

    pub fn load_project_metadata(&mut self) {
        let config_path = self.project_root.join("docs/sync_config.json");
        let meta_path = self.project_root.join(".dify_sync_meta.json");

        if !config_path.exists() {
            self.status_message = format!("No config {:?} found.", config_path);
            return;
        }

        // 1. メタデータのロード
        let mut meta_map: HashMap<String, Value> = HashMap::new();
        if meta_path.exists() {
            if let Ok(content) = fs::read_to_string(&meta_path) {
                if let Ok(Value::Object(map)) = serde_json::from_str::<Value>(&content) {
                    for (k, v) in map {
                        meta_map.insert(k, v);
                    }
                }
            }
        }

        // 2. 設定ファイルロード ＆ 各プロジェクトのフォルダスキャン
        let mut detected_projects = Vec::new();
        if let Ok(content) = fs::read_to_string(&config_path) {
            if let Ok(Value::Object(map)) = serde_json::from_str::<Value>(&content) {
                if let Some(Value::Object(projects_obj)) = map.get("projects") {
                    for (project_name, proj_val) in projects_obj {
                        let dataset_id = proj_val.get("dataset_id").and_then(|d| d.as_str()).unwrap_or("").to_string();
                        let api_key = proj_val.get("api_key").and_then(|k| k.as_str()).unwrap_or("").to_string();
                        let api_base = proj_val.get("api_base").and_then(|b| b.as_str()).unwrap_or("").to_string();
                        let project_dir = self.project_root.join("docs").join(project_name);
                        
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
                                if let Ok(abs_meta_path) = fs::canonicalize(self.project_root.join(meta_path_str)) {
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
                            dataset_id,
                            api_key,
                            api_base,
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

    pub async fn delete_selected_project(&mut self) -> Result<(), Box<dyn std::error::Error>> {
        if self.projects.is_empty() { return Ok(()); }
        let project = &self.projects[self.selected_project_index];
        
        let client = reqwest::Client::new();
        
        // 1. Dify API でデータセットを削除
        let delete_url = format!("{}/datasets/{}", project.api_base, project.dataset_id);
        let _ = client.delete(&delete_url)
            .header("Authorization", format!("Bearer {}", project.api_key))
            .send()
            .await;
            
        // 2. sync_config.json からプロジェクトを削除
        let config_path = self.project_root.join("docs/sync_config.json");
        if config_path.exists() {
            if let Ok(content) = fs::read_to_string(&config_path) {
                if let Ok(mut val) = serde_json::from_str::<Value>(&content) {
                    if let Some(projects_obj) = val.get_mut("projects").and_then(|p| p.as_object_mut()) {
                        projects_obj.remove(&project.name);
                        let updated_json = serde_json::to_string_pretty(&val)?;
                        fs::write(&config_path, updated_json)?;
                    }
                }
            }
        }
        
        // 3. 同期メタデータ (.dify_sync_meta.json) からそのプロジェクト関連ファイルを削除
        let meta_path = self.project_root.join(".dify_sync_meta.json");
        if meta_path.exists() {
            if let Ok(content) = fs::read_to_string(&meta_path) {
                if let Ok(mut val) = serde_json::from_str::<Value>(&content) {
                    if let Some(meta_obj) = val.as_object_mut() {
                        let project_prefix = format!("docs/{}", project.name);
                        meta_obj.retain(|k, _| !k.starts_with(&project_prefix));
                        let updated_json = serde_json::to_string_pretty(&val)?;
                        fs::write(&meta_path, updated_json)?;
                    }
                }
            }
        }

        self.add_log(format!("Deleted knowledge base '{}' from Dify.", project.name));
        self.load_project_metadata();
        self.selected_project_index = 0;
        
        Ok(())
    }

    pub async fn send_rag_chat(&mut self, query: String, tx: tokio::sync::mpsc::Sender<String>) {
        if self.projects.is_empty() { return; }
        let project = self.projects[self.selected_project_index].clone();
        
        self.is_loading_chat = true;
        self.chat_scroll_offset = 0;
        self.chat_focus = ChatFocus::Input;
        self.chat_history.push(ChatMessage {
            is_user: true,
            content: query.clone(),
        });

        tokio::spawn(async move {
            let client = reqwest::Client::new();
            
            // 1. Dify Retrieval API でコンテキストを取得
            let rerank_enabled = std::env::var("RAGY_RERANK_ENABLE")
                .map(|v| v == "1" || v.eq_ignore_ascii_case("true"))
                .unwrap_or(false);

            let retrieve_url = format!("{}/datasets/{}/retrieve", project.api_base, project.dataset_id);
            
            log_tui_debug(&format!("=== NEW CHAT QUERY: '{}' (Project: {}) ===", query, project.name));
            log_tui_debug(&format!("Dify Retrieve URL: {}", retrieve_url));
            
            let retrieve_res = client.post(&retrieve_url)
                .header("Authorization", format!("Bearer {}", project.api_key))
                .json(&serde_json::json!({
                    "query": query,
                    "retrieval_model": {
                        "search_method": "hybrid_search",
                        "top_k": 3,
                        "reranking_enable": rerank_enabled,
                        "score_threshold_enabled": false
                    }
                }))
                .send()
                .await;

            let mut context_str = String::new();
            match retrieve_res {
                Ok(res) => {
                    let status = res.status();
                    log_tui_debug(&format!("Dify Retrieve HTTP Status: {}", status));
                    if status.is_success() {
                        if let Ok(val) = res.json::<Value>().await {
                            log_tui_debug(&format!("Dify Retrieve Raw Response: {}", val));
                            if let Some(records) = val.get("records").and_then(|r| r.as_array()) {
                                log_tui_debug(&format!("Retrieved {} records from Dify.", records.len()));
                                // Lost in the Middle 対策のコンテキスト再配置を適用
                                let mut records_vec = records.clone();
                                if records_vec.len() > 2 {
                                    records_vec.sort_by(|a, b| {
                                        let score_a = a.get("score").and_then(|s| s.as_f64()).unwrap_or(0.0);
                                        let score_b = b.get("score").and_then(|s| s.as_f64()).unwrap_or(0.0);
                                        score_b.partial_cmp(&score_a).unwrap_or(std::cmp::Ordering::Equal)
                                    });
                                    let mut reordered = vec![Value::Null; records_vec.len()];
                                    let mut left = 0;
                                    let mut right = records_vec.len() - 1;
                                    for (idx, item) in records_vec.into_iter().enumerate() {
                                        if idx % 2 == 0 {
                                            reordered[left] = item;
                                            left += 1;
                                        } else {
                                            reordered[right] = item;
                                            right -= 1;
                                        }
                                    }
                                    records_vec = reordered;
                                }

                                for rec in records_vec {
                                    let content_opt = rec.get("segment")
                                        .and_then(|s| s.get("content"))
                                        .or_else(|| rec.get("content"))
                                        .and_then(|c| c.as_str());
                                    if let Some(content) = content_opt {
                                        context_str.push_str(content);
                                        context_str.push_str("\n\n");
                                    }
                                }
                            }
                        } else {
                            log_tui_debug("Error: Failed to parse Dify Retrieval response JSON.");
                            let _ = tx.send("Error: Failed to parse Dify Retrieval response JSON.".to_string()).await;
                            return;
                        }
                    } else {
                        let err_text = res.text().await.unwrap_or_default();
                        log_tui_debug(&format!("Dify Retrieval HTTP Error {}: {}", status, err_text));
                        let _ = tx.send(format!("Dify Retrieval HTTP Error {}: {}", status, err_text)).await;
                        return;
                    }
                }
                Err(e) => {
                    log_tui_debug(&format!("Dify Retrieval Connect Error: {}", e));
                    let _ = tx.send(format!("Dify Retrieval Connect Error: {}", e)).await;
                    return;
                }
            }

            if context_str.is_empty() {
                log_tui_debug("Warning: Extracted context is empty!");
                context_str = "No relevant context found in dataset.".to_string();
            } else {
                log_tui_debug(&format!("Final Context String passed to LLM ({} chars):\n{}", context_str.len(), context_str));
            }

            // 2. LiteLLM Proxy を介して LLM を呼び出す
            let litellm_base = std::env::var("LITELLM_API_BASE")
                .unwrap_or_else(|_| "http://localhost:4000/v1".to_string());
            let litellm_url = format!("{}/chat/completions", litellm_base);
            
            let llm_model = std::env::var("RAGY_LLM_MODEL")
                .unwrap_or_else(|_| "gemini-2.5-flash".to_string());

            let chat_payload = serde_json::json!({
                "model": llm_model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a helpful coding assistant. Use the provided context to answer the user's question accurately. If you don't know the answer based on the context, say so."
                    },
                    {
                        "role": "user",
                        "content": format!("Context:\n{}\n\nQuestion: {}", context_str, query)
                    }
                ]
            });
            log_tui_debug(&format!("LiteLLM URL: {}", litellm_url));
            log_tui_debug(&format!("LiteLLM Payload: {}", chat_payload));

            let chat_res = client.post(&litellm_url)
                .header("Authorization", "Bearer sk-1234")
                .json(&chat_payload)
                .send()
                .await;

            let reply_content = match chat_res {
                Ok(res) => {
                    let status = res.status();
                    log_tui_debug(&format!("LiteLLM Response Status: {}", status));
                    if status.is_success() {
                        if let Ok(val) = res.json::<Value>().await {
                            log_tui_debug(&format!("LiteLLM Raw Response: {}", val));
                            if let Some(content) = val.get("choices")
                                .and_then(|c| c.as_array())
                                .and_then(|a| a.first())
                                .and_then(|f| f.get("message"))
                                .and_then(|m| m.get("content"))
                                .and_then(|s| s.as_str()) {
                                    content.to_string()
                                } else {
                                    format!("Error: Unexpected LLM Response Format: {:?}", val)
                                }
                        } else {
                            log_tui_debug("Error: Failed to parse LLM Response JSON.");
                            "Error: Failed to parse LLM Response JSON.".to_string()
                        }
                    } else {
                        let err_text = res.text().await.unwrap_or_default();
                        log_tui_debug(&format!("LiteLLM Proxy HTTP Error {}: {}", status, err_text));
                        format!("LLM Proxy HTTP Error {}: {}", status, err_text)
                    }
                }
                Err(e) => {
                    log_tui_debug(&format!("LiteLLM Proxy Connect Error: {}", e));
                    format!("LLM Proxy Connect Error: {}", e)
                }
            };

            log_tui_debug(&format!("LLM Reply: {}", reply_content));
            let _ = tx.send(reply_content).await;
        });
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::TcpListener;
    use std::io::{Read, Write};
    use std::thread;
    use tokio::sync::mpsc;

    #[tokio::test]
    async fn test_tui_rag_chat_flow() {
        // 1. HTTPモックサーバーの起動 (ポートはランダム自動割り当て)
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let local_addr = listener.local_addr().unwrap();
        let port = local_addr.port();
        
        // テスト用に環境変数を書き換えてモックサーバーに仕向ける
        std::env::set_var("LITELLM_API_BASE", format!("http://127.0.0.1:{}", port));

        // スレッドで簡易HTTPモックサーバーの振る舞いを記述
        thread::spawn(move || {
            // 第一リクエスト: Dify Retrieval API
            if let Ok((mut stream, _)) = listener.accept() {
                let mut buffer = [0; 2048];
                let _ = stream.read(&mut buffer);
                
                let dify_mock_response = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\
                    \"records\": [\
                        {\"content\": \"Self-Attention is powerful.\"},\
                        {\"content\": \"Transformer improves accuracy.\"}\
                    ]\
                }";
                let _ = stream.write_all(dify_mock_response.as_bytes());
            }
            
            // 第二リクエスト: LiteLLM Proxy API
            if let Ok((mut stream, _)) = listener.accept() {
                let mut buffer = [0; 2048];
                let _ = stream.read(&mut buffer);
                
                let litellm_mock_response = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\
                    \"choices\": [\
                        {\
                            \"message\": {\
                                \"role\": \"assistant\",\
                                \"content\": \"Self-Attention design details summary.\"\
                            }\
                        }\
                    ]\
                }";
                let _ = stream.write_all(litellm_mock_response.as_bytes());
            }
        });

        // 2. テスト用 App のセットアップ
        let mut app = App::new();
        app.projects = vec![
            ProjectInfo {
                name: "TestProject".to_string(),
                dataset_id: "test-dataset-123".to_string(),
                api_key: "test-api-key-456".to_string(),
                api_base: format!("http://127.0.0.1:{}", port),
                synced_files: 10,
                pending_files: 0,
            }
        ];
        app.selected_project_index = 0;
        app.mode = TuiMode::Chat;

        // 非同期チャットチャンネル
        let (chat_tx, mut chat_rx) = mpsc::channel::<String>(10);

        // 3. チャットの非同期送信テスト
        app.send_rag_chat("Explain Attention".to_string(), chat_tx).await;
        
        // 非同期回答がモックサーバーから回収されるのを待機 (最長3秒)
        let mut received_reply = None;
        for _ in 0..30 {
            if let Ok(reply) = chat_rx.try_recv() {
                received_reply = Some(reply);
                break;
            }
            tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;
        }

        // 4. アサーション検証
        assert!(received_reply.is_some(), "Should receive RAG chat reply from mock server");
        let reply = received_reply.unwrap();
        assert!(reply.contains("Self-Attention design details summary."));
        
        // 環境変数をクリーンアップ
        std::env::remove_var("LITELLM_API_BASE");
    }

    #[tokio::test]
    #[ignore]
    async fn test_real_e2e_rag_chat_flow() {
        // .env を手動で読み込んで環境変数にセット
        if let Ok(content) = std::fs::read_to_string(".env") {
            for line in content.lines() {
                if line.trim().is_empty() || line.starts_with('#') {
                    continue;
                }
                if let Some((key, val)) = line.split_once('=') {
                    std::env::set_var(key.trim(), val.trim());
                }
            }
        }
        
        let api_key = std::env::var("DIFY_DATASET_API_KEY")
            .expect("DIFY_DATASET_API_KEY must be set in .env for E2E integration test");
            
        let mut app = App::new();
        app.projects = vec![
            ProjectInfo {
                name: "RealTest".to_string(),
                dataset_id: "d42ec795-1e17-4ced-8efa-8996e479ae23".to_string(), // 実在するMy-GitHub-RAGのデータセットID
                api_key,
                api_base: "http://localhost:8080/v1".to_string(), // 本番Dify Gateway
                synced_files: 1,
                pending_files: 0,
            }
        ];
        app.selected_project_index = 0;
        app.mode = TuiMode::Chat;

        let (chat_tx, mut chat_rx) = mpsc::channel::<String>(10);
        
        // 実際の RAG チャット呼び出しをトリガー
        app.send_rag_chat("What is My-RAG-Agent-System?".to_string(), chat_tx).await;
        
        // リアルな LLM からの応答を最大 15 秒間待機
        let mut received_reply = None;
        for _ in 0..150 {
            if let Ok(reply) = chat_rx.try_recv() {
                received_reply = Some(reply);
                break;
            }
            tokio::time::sleep(tokio::time::Duration::from_millis(100)).await;
        }

        assert!(received_reply.is_some(), "E2E: Should receive RAG chat reply from real LiteLLM Proxy / Dify");
        let reply = received_reply.unwrap();
        println!("Real E2E Response: {}", reply);
        assert!(!reply.contains("Error:"), "Should not contain Error string, but got: {}", reply);
        assert!(reply.len() > 10, "Response should be a valid text explanation");
    }
}
