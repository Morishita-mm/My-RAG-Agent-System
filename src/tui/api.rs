use super::app::{App, ChatMessage, ChatFocus, log_tui_debug};
use serde_json::Value;
use std::fs;

// ==========================================
// 1. Grader / Classifier / Rewriter ヘルパー関数 (モジュールプライベートで定義しネスト排除)
// ==========================================

// 十分性判定 (Grader)
async fn grade_sufficiency(
    client: &reqwest::Client,
    litellm_url: &str,
    query: &str,
    context: &str,
) -> String {
    let system_prompt = "You are a context relevance grader. Evaluate if the retrieved document context contains sufficient information to directly answer the user's question.\n\
        Return one of the following decisions as a single word:\n\
        - YES: The context is fully sufficient to answer the question directly.\n\
        - NO: The context is completely irrelevant or missing the key information.\n\
        - PARTIAL: The context has some relevant terms but is insufficient to provide a complete, high-quality answer.\n\
        Decision (YES/NO/PARTIAL):";

    let local_model = std::env::var("RAGY_LOCAL_MODEL")
        .unwrap_or_else(|_| "qwen2.5-coder".to_string());
    let cloud_model = std::env::var("RAGY_LLM_MODEL")
        .unwrap_or_else(|_| "gemini-2.5-flash".to_string());

    let messages = serde_json::json!([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": format!("Context:\n{}", context)},
        {"role": "user", "content": format!("Question:\n{}", query)}
    ]);

    // 1. ローカルモデルでの試行
    let payload = serde_json::json!({
        "model": local_model,
        "messages": messages,
        "temperature": 0.0
    });

    if let Ok(res) = client.post(litellm_url)
        .header("Authorization", "Bearer sk-1234")
        .json(&payload)
        .send()
        .await
    {
        if res.status().is_success() {
            if let Ok(val) = res.json::<Value>().await {
                if let Some(content) = val.get("choices")
                    .and_then(|c| c.as_array())
                    .and_then(|a| a.first())
                    .and_then(|f| f.get("message"))
                    .and_then(|m| m.get("content"))
                    .and_then(|s| s.as_str())
                {
                    let decision = content.trim().to_uppercase();
                    if decision.contains("YES") { return "YES".to_string(); }
                    if decision.contains("NO") { return "NO".to_string(); }
                    if decision.contains("PARTIAL") { return "PARTIAL".to_string(); }
                }
            }
        }
    }

    // 2. クラウドモデルへのフォールバック
    log_tui_debug(&format!("  -> [Fallback] Local model '{}' failed for grading. Trying cloud model '{}'...", local_model, cloud_model));
    let payload_fallback = serde_json::json!({
        "model": cloud_model,
        "messages": messages,
        "temperature": 0.0
    });

    if let Ok(res) = client.post(litellm_url)
        .header("Authorization", "Bearer sk-1234")
        .json(&payload_fallback)
        .send()
        .await
    {
        if res.status().is_success() {
            if let Ok(val) = res.json::<Value>().await {
                if let Some(content) = val.get("choices")
                    .and_then(|c| c.as_array())
                    .and_then(|a| a.first())
                    .and_then(|f| f.get("message"))
                    .and_then(|m| m.get("content"))
                    .and_then(|s| s.as_str())
                {
                    let decision = content.trim().to_uppercase();
                    if decision.contains("YES") { return "YES".to_string(); }
                    if decision.contains("NO") { return "NO".to_string(); }
                    if decision.contains("PARTIAL") { return "PARTIAL".to_string(); }
                }
            }
        }
    }

    "PARTIAL".to_string()
}

// クエリ書き換え (Rewriter)
async fn rewrite_query(
    client: &reqwest::Client,
    litellm_url: &str,
    query: &str,
    context: &str,
) -> String {
    let system_prompt = "You are a search query optimizer. Given the original question and the current insufficient search context, rewrite the query to improve the chance of finding the missing information in the vector database.\n\
        Only output the rewritten search query. Do not add any explanation, quotation marks, or preamble.";

    let local_model = std::env::var("RAGY_LOCAL_MODEL")
        .unwrap_or_else(|_| "qwen2.5-coder".to_string());
    let cloud_model = std::env::var("RAGY_LLM_MODEL")
        .unwrap_or_else(|_| "gemini-2.5-flash".to_string());

    let messages = serde_json::json!([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": format!("Current Context:\n{}", context)},
        {"role": "user", "content": format!("Original Question:\n{}", query)}
    ]);

    // 1. ローカルモデルでの試行
    let payload = serde_json::json!({
        "model": local_model,
        "messages": messages,
        "temperature": 0.3
    });

    if let Ok(res) = client.post(litellm_url)
        .header("Authorization", "Bearer sk-1234")
        .json(&payload)
        .send()
        .await
    {
        if res.status().is_success() {
            if let Ok(val) = res.json::<Value>().await {
                if let Some(content) = val.get("choices")
                    .and_then(|c| c.as_array())
                    .and_then(|a| a.first())
                    .and_then(|f| f.get("message"))
                    .and_then(|m| m.get("content"))
                    .and_then(|s| s.as_str())
                {
                    return content.trim().trim_matches('"').trim_matches('\'').to_string();
                }
            }
        }
    }

    // 2. クラウドモデルへのフォールバック
    log_tui_debug(&format!("  -> [Fallback] Local model '{}' failed for rewriting. Trying cloud model '{}'...", local_model, cloud_model));
    let payload_fallback = serde_json::json!({
        "model": cloud_model,
        "messages": messages,
        "temperature": 0.3
    });

    if let Ok(res) = client.post(litellm_url)
        .header("Authorization", "Bearer sk-1234")
        .json(&payload_fallback)
        .send()
        .await
    {
        if res.status().is_success() {
            if let Ok(val) = res.json::<Value>().await {
                if let Some(content) = val.get("choices")
                    .and_then(|c| c.as_array())
                    .and_then(|a| a.first())
                    .and_then(|f| f.get("message"))
                    .and_then(|m| m.get("content"))
                    .and_then(|s| s.as_str())
                {
                    return content.trim().trim_matches('"').trim_matches('\'').to_string();
                }
            }
        }
    }

    query.to_string()
}

// クエリ難易度判定 (Classifier)
async fn classify_query_difficulty(
    client: &reqwest::Client,
    litellm_url: &str,
    query: &str,
) -> String {
    let system_prompt = "Determine if the user's question requires advanced coding capability, complex logic analysis, or detailed system architectural design.\n\
        Return exactly \"ADVANCED\" if it is complex, or \"SIMPLE\" if it is a simple greeting, generic question, basic coding term explanation, or trivial query.\n\
        Do not output any other words.\n\
        Decision (ADVANCED/SIMPLE):";

    let local_model = std::env::var("RAGY_LOCAL_MODEL")
        .unwrap_or_else(|_| "qwen2.5-coder".to_string());
    let cloud_model = std::env::var("RAGY_LLM_MODEL")
        .unwrap_or_else(|_| "gemini-2.5-flash".to_string());

    let messages = serde_json::json!([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": format!("Question:\n{}", query)}
    ]);

    // 1. ローカルモデルでの試行
    let payload = serde_json::json!({
        "model": local_model,
        "messages": messages,
        "temperature": 0.0
    });

    if let Ok(res) = client.post(litellm_url)
        .header("Authorization", "Bearer sk-1234")
        .json(&payload)
        .send()
        .await
    {
        if res.status().is_success() {
            if let Ok(val) = res.json::<Value>().await {
                if let Some(content) = val.get("choices")
                    .and_then(|c| c.as_array())
                    .and_then(|a| a.first())
                    .and_then(|f| f.get("message"))
                    .and_then(|m| m.get("content"))
                    .and_then(|s| s.as_str())
                {
                    let decision = content.trim().to_uppercase();
                    if decision.contains("SIMPLE") { return "SIMPLE".to_string(); }
                    if decision.contains("ADVANCED") { return "ADVANCED".to_string(); }
                }
            }
        }
    }

    // 2. クラウドモデルへのフォールバック
    log_tui_debug(&format!("  -> [Fallback] Local model '{}' failed for difficulty classification. Trying cloud model '{}'...", local_model, cloud_model));
    let payload_fallback = serde_json::json!({
        "model": cloud_model,
        "messages": messages,
        "temperature": 0.0
    });

    if let Ok(res) = client.post(litellm_url)
        .header("Authorization", "Bearer sk-1234")
        .json(&payload_fallback)
        .send()
        .await
    {
        if res.status().is_success() {
            if let Ok(val) = res.json::<Value>().await {
                if let Some(content) = val.get("choices")
                    .and_then(|c| c.as_array())
                    .and_then(|a| a.first())
                    .and_then(|f| f.get("message"))
                    .and_then(|m| m.get("content"))
                    .and_then(|s| s.as_str())
                {
                    let decision = content.trim().to_uppercase();
                    if decision.contains("SIMPLE") { return "SIMPLE".to_string(); }
                }
            }
        }
    }

    "ADVANCED".to_string()
}

// ==========================================
// 2. App 構造体の API / Redis 操作メソッド実装
// ==========================================
impl App {
    pub(crate) fn redis_client(&self) -> Result<redis::Client, redis::RedisError> {
        let redis_url = std::env::var("REDIS_URL")
            .unwrap_or_else(|_| "redis://:difyai123456@127.0.0.1:6379".to_string());
        redis::Client::open(redis_url)
    }

    pub async fn fetch_redis_stats(&mut self) {
        let client_res = self.redis_client();
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
        let client_res = self.redis_client();
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
            let rerank_enabled = std::env::var("RAGY_RERANK_ENABLE")
                .map(|v| v == "1" || v.eq_ignore_ascii_case("true"))
                .unwrap_or(false);

            let retrieve_url = format!("{}/datasets/{}/retrieve", project.api_base, project.dataset_id);
            
            let litellm_base = std::env::var("LITELLM_API_BASE")
                .unwrap_or_else(|_| "http://localhost:4000/v1".to_string());
            let litellm_url = format!("{}/chat/completions", litellm_base);
            
            log_tui_debug(&format!("=== NEW CHAT QUERY: '{}' (Project: {}) ===", query, project.name));
            log_tui_debug(&format!("Dify Retrieve URL: {}", retrieve_url));
            log_tui_debug(&format!("LiteLLM URL: {}", litellm_url));

            let mut current_query = query.clone();
            let mut retrieved_segments: Vec<String> = Vec::new();
            let mut seen_contents: std::collections::HashSet<String> = std::collections::HashSet::new();
            let max_loops = 3;

            for loop_idx in 1..=max_loops {
                let _ = tx.send(format!("[STATUS]Searching dataset (Loop {}/{})...", loop_idx, max_loops)).await;
                log_tui_debug(&format!("[Loop {}/{}] Searching for: '{}'", loop_idx, max_loops, current_query));
                
                let retrieve_res = client.post(&retrieve_url)
                    .header("Authorization", format!("Bearer {}", project.api_key))
                    .json(&serde_json::json!({
                        "query": current_query,
                        "retrieval_model": {
                            "search_method": "hybrid_search",
                            "top_k": 3,
                            "reranking_enable": rerank_enabled,
                            "score_threshold_enabled": false
                        }
                    }))
                    .send()
                    .await;

                match retrieve_res {
                    Ok(res) => {
                        let status = res.status();
                        log_tui_debug(&format!("  -> Dify Retrieve HTTP Status: {}", status));
                        if status.is_success() {
                            if let Ok(val) = res.json::<Value>().await {
                                log_tui_debug(&format!("  -> Dify Retrieve Raw Response: {}", val));
                                if let Some(records) = val.get("records").and_then(|r| r.as_array()) {
                                    log_tui_debug(&format!("  -> Retrieved {} records from Dify.", records.len()));
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
                                            let content_str = content.to_string();
                                            if !seen_contents.contains(&content_str) {
                                                seen_contents.insert(content_str.clone());
                                                retrieved_segments.push(content_str);
                                            }
                                        }
                                    }
                                }
                            } else {
                                log_tui_debug("  -> Error: Failed to parse Dify Retrieval response JSON.");
                                let _ = tx.send("Error: Failed to parse Dify Retrieval response JSON.".to_string()).await;
                                return;
                            }
                        } else {
                            let err_text = res.text().await.unwrap_or_default();
                            log_tui_debug(&format!("  -> Dify Retrieval HTTP Error {}: {}", status, err_text));
                            let _ = tx.send(format!("Dify Retrieval HTTP Error {}: {}", status, err_text)).await;
                            return;
                        }
                    }
                    Err(e) => {
                        log_tui_debug(&format!("  -> Dify Retrieval Connect Error: {}", e));
                        let _ = tx.send(format!("Dify Retrieval Connect Error: {}", e)).await;
                        return;
                    }
                }

                let raw_context = retrieved_segments.join("\n\n");
                let decision = if raw_context.is_empty() {
                    "NO".to_string()
                } else {
                    let _ = tx.send(format!("[STATUS]Grading relevance (Loop {}/{})...", loop_idx, max_loops)).await;
                    let d = grade_sufficiency(&client, &litellm_url, &query, &raw_context).await;
                    log_tui_debug(&format!("  -> Sufficiency Grade: {}", d));
                    d
                };

                if decision == "YES" || loop_idx == max_loops {
                    break;
                }

                let _ = tx.send(format!("[STATUS]Optimizing query (Loop {}/{})...", loop_idx, max_loops)).await;
                current_query = rewrite_query(&client, &litellm_url, &query, &raw_context).await;
                log_tui_debug(&format!("  -> Rewritten Query: '{}'", current_query));
            }

            let mut context_str = retrieved_segments.join("\n\n");
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
            
            // クエリ難易度の自動分類とモデル決定 (Routing)
            let _ = tx.send("[STATUS]Classifying query difficulty...".to_string()).await;
            let difficulty = classify_query_difficulty(&client, &litellm_url, &query).await;
            let local_model = std::env::var("RAGY_LOCAL_MODEL")
                .unwrap_or_else(|_| "qwen2.5-coder".to_string());
            let cloud_model = std::env::var("RAGY_LLM_MODEL")
                .unwrap_or_else(|_| "gemini-2.5-flash".to_string());

            let target_model = if difficulty == "SIMPLE" {
                log_tui_debug(&format!("  -> [Routing] Query classified as 'SIMPLE'. Routing final answer to local model '{}'.", local_model));
                local_model.clone()
            } else {
                log_tui_debug(&format!("  -> [Routing] Query classified as 'ADVANCED'. Routing final answer to cloud model '{}'.", cloud_model));
                cloud_model.clone()
            };

            let _ = tx.send(format!("[STATUS]Synthesizing answer using {}...", target_model)).await;

            let chat_payload = serde_json::json!({
                "model": target_model,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a helpful coding assistant. Use the provided context to answer the user's question accurately. You MUST write your entire response in Japanese. If you do not know the answer based on the context, say '情報がありません'."
                    },
                    {
                        "role": "user",
                        "content": format!("Context:\n{}", context_str)
                    },
                    {
                        "role": "user",
                        "content": format!("Question:\n{}", query)
                    }
                ]
            });
            log_tui_debug(&format!("LiteLLM URL: {}", litellm_url));
            log_tui_debug(&format!("LiteLLM Payload: {}", chat_payload));

            let mut final_reply = None;

            let chat_res = client.post(&litellm_url)
                .header("Authorization", "Bearer sk-1234")
                .json(&chat_payload)
                .send()
                .await;

            match chat_res {
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
                                .and_then(|s| s.as_str())
                            {
                                final_reply = Some(content.to_string());
                            }
                        }
                    }
                }
                Err(e) => {
                    log_tui_debug(&format!("LiteLLM Proxy Connect Error: {}", e));
                }
            }

            // ローカルで失敗した場合、クラウドへ自動フォールバック
            if final_reply.is_none() && target_model == local_model {
                log_tui_debug(&format!("  -> [Fallback] Final answer generation failed on local model '{}'. Routing final answer to cloud model '{}'.", local_model, cloud_model));
                let chat_payload_fallback = serde_json::json!({
                    "model": cloud_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are a helpful coding assistant. Use the provided context to answer the user's question accurately. You MUST write your entire response in Japanese. If you do not know the answer based on the context, say '情報がありません'."
                        },
                        {
                            "role": "user",
                            "content": format!("Context:\n{}", context_str)
                        },
                        {
                            "role": "user",
                            "content": format!("Question:\n{}", query)
                        }
                    ]
                });
                if let Ok(res) = client.post(&litellm_url)
                    .header("Authorization", "Bearer sk-1234")
                    .json(&chat_payload_fallback)
                    .send()
                    .await
                {
                    if res.status().is_success() {
                        if let Ok(val) = res.json::<Value>().await {
                            if let Some(content) = val.get("choices")
                                .and_then(|c| c.as_array())
                                .and_then(|a| a.first())
                                .and_then(|f| f.get("message"))
                                .and_then(|m| m.get("content"))
                                .and_then(|s| s.as_str())
                            {
                                final_reply = Some(content.to_string());
                            }
                        }
                    }
                }
            }

            let reply_text = final_reply.unwrap_or_else(|| "Error generating RAG reply.".to_string());
            let _ = tx.send(reply_text).await;
        });
    }
}
