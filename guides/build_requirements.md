# 個人用RAG＋エージェント環境（OrbStack）構築要件およびタスク定義書

## 1. 概要とエージェントへの基本指示

本ドキュメントは、Mac M4 16GB環境（OrbStack）上に、APIとローカルのハイブリッド型AIコーディングエージェントおよびドキュメントRAGの高度なPoC環境を構築するための要件定義書です。

【AIエージェントへの厳格な実行プロトコル】
あなたは以下の手順に従って自律的に作業を進めること。

1. 作業開始前に、カレントディレクトリに `TASK_TRACKER.md` というタスク管理ファイルを作成し、本ドキュメントの「フェーズ別構築要件」に記載されているすべてのタスクを未完了のチェックリスト形式 (`- [ ]`) で転記すること。
2. 1つのタスクが完了し、動作確認（ローカルでのcurlテストやコンテナ起動確認）に成功するたびに、`TASK_TRACKER.md` の該当項目を完了 (`- [x]`) に更新し、実行したコマンドやエラー対処のメモを追記すること。
3. 決して複数のフェーズを同時に進めないこと。一つずつ確実に完了させること。

## 2. 前提条件と環境要件

- OS: macOS (M4チップ, メモリ16GB)
- コンテナランタイム: OrbStack
- ネットワーク: `rag-network` (ブリッジネットワーク)
- ポートマッピング: LiteLLM(4000), Dify(8080), Ollama(11434)

---

## 3. フェーズ別構築要件 (タスク一覧)

### Phase 1: APIゲートウェイ (LiteLLM Proxy) の構築

- [ ] `docker-compose.yml` のベース作成 (LiteLLMをポート4000で定義)
- [ ] `litellm_config.yaml` の作成 (Google AI Studio等の外部APIルーティング定義)
- [ ] コンテナを起動し、LiteLLMのダッシュボードUIが有効化されていることを確認

### Phase 2: コーディングエージェント (Continue) の接続

- [ ] `continue_config_template.json` の作成 (LiteLLMをプロバイダーとして設定)
- [ ] LiteLLMのプロンプトガードレール設定 (XMLタグの強制解釈指示の追加)

### Phase 3: RAG基盤 (Dify) の構築

- [ ] `docker-compose.yml` にDifyの関連コンテナ群 (db, redis, weaviate, api, web等) を追記
- [ ] ポート8080でDifyのWeb UIが起動することを確認
- [ ] `dify_setup_guide.md` を作成し、LiteLLMをシステムモデルとして登録する手順を明記

### Phase 4: ローカルLLM (Ollama) のハイブリッド運用テスト

- [ ] `ollama_setup_guide.md` の作成 (Macネイティブでの `qwen2.5-coder:3b` 起動コマンド等)
- [ ] `litellm_config.yaml` を更新し、ホスト側 (host.docker.internal:11434) へのルーティングを追加

### Phase 5: 高度なPoC機能 (同期・MCP・自己修復・ログローテーション) の実装

- [ ] ドキュメント自動同期スクリプト `sync_docs.py` の作成 (watchdogを用いてローカルフォルダを監視し、Dify APIへ送信)
- [ ] MCPサーバー用設定の雛形 `mcp_server.py` の作成 (ContinueとDifyを連携させるプロトコル実装)
- [ ] ログローテーションスクリプト `log_cleanup.sh` の作成 (LiteLLMのSQLiteログを7日で削除・VACUUMする処理)
- [ ] 自己修復(Human-in-the-Loop)のワークフローを定義した `auto_fix_workflow.md` の作成
