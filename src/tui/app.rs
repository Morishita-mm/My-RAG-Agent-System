use std::collections::HashMap;
use std::fs;
use std::path::PathBuf;
use serde::{Deserialize, Serialize};
use serde_json::Value;

#[derive(Clone, Debug)]
pub struct ProjectInfo {
    pub name: String,
    pub dataset_id: String,
    pub api_key: String,
    pub api_base: String,
    pub synced_files: usize,
    pub pending_files: usize,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct ChatMessage {
    pub is_user: bool,
    pub content: String,
}

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

pub(crate) fn get_project_root() -> PathBuf {
    std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))
}

pub(crate) fn log_tui_debug(msg: &str) {
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

pub struct App {
    pub project_root: PathBuf,
    pub projects: Vec<ProjectInfo>,
    pub selected_project_index: usize,
    pub logs: Vec<String>,
    pub active_tab: usize,
    pub should_quit: bool,
    pub status_message: String,
    pub redis_connected: bool,
    pub exact_cache_count: usize,
    pub semantic_cache_count: usize,
    pub hit_rate: f64,
    
    // NotebookLM / Vim 拡張用
    pub mode: TuiMode,
    pub chat_history: Vec<ChatMessage>,
    pub input_buffer: String,
    pub is_loading_chat: bool,
    pub chat_focus: ChatFocus,
    pub chat_scroll_offset: usize,
    pub chat_status: String,
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
            chat_status: String::new(),
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
                if let Ok(map) = serde_json::from_str::<HashMap<String, Value>>(&content) {
                    meta_map = map;
                }
            }
        }

        // ディスクI/O canonicalize の事前キャッシュによるO(N + M)への高速化
        let mut synced_paths = std::collections::HashSet::new();
        for meta_path_str in meta_map.keys() {
            if let Ok(abs_meta_path) = fs::canonicalize(self.project_root.join(meta_path_str)) {
                synced_paths.insert(abs_meta_path.to_string_lossy().to_string());
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
                            if synced_paths.contains(local_file) {
                                synced_files += 1;
                            } else {
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
}

#[cfg(test)]
#[path = "app_tests.rs"]
mod app_tests;
