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
        
        // 第二リクエスト: LiteLLM Grader API (YES を返す)
        if let Ok((mut stream, _)) = listener.accept() {
            let mut buffer = [0; 2048];
            let _ = stream.read(&mut buffer);
            
            let grader_mock_response = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\
                \"choices\": [\
                    {\
                        \"message\": {\
                            \"role\": \"assistant\",\
                            \"content\": \"YES\"\
                        }\
                    }\
                ]\
            }";
            let _ = stream.write_all(grader_mock_response.as_bytes());
        }
        // 第三リクエスト: LiteLLM Classifier API (クエリ難易度判定: SIMPLE を返す)
        if let Ok((mut stream, _)) = listener.accept() {
            let mut buffer = [0; 2048];
            let _ = stream.read(&mut buffer);
            
            let classifier_mock_response = "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n{\
                \"choices\": [\
                    {\
                        \"message\": {\
                            \"role\": \"assistant\",\
                            \"content\": \"SIMPLE\"\
                        }\
                    }\
                ]\
            }";
            let _ = stream.write_all(classifier_mock_response.as_bytes());
        }

        // 第四リクエスト: LiteLLM Proxy API (最終回答)
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
        while let Ok(reply) = chat_rx.try_recv() {
            if !reply.starts_with("[STATUS]") {
                received_reply = Some(reply);
                break;
            }
        }
        if received_reply.is_some() {
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
    
    // リアルな LLM からの応答を最大 40 秒間待機
    let mut received_reply = None;
    for _ in 0..400 {
        while let Ok(reply) = chat_rx.try_recv() {
            if !reply.starts_with("[STATUS]") {
                received_reply = Some(reply);
                break;
            }
        }
        if received_reply.is_some() {
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
