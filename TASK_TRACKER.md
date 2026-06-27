# Task Tracker

## Phase 1: APIゲートウェイ (LiteLLM Proxy) の構築
- [x] `docker-compose.yml` のベース作成 (LiteLLMをポート4000で定義)
- [x] `litellm_config.yaml` の作成 (Google AI Studio等の外部APIルーティング定義)
- [x] コンテナを起動し、LiteLLM of ダッシュボードUIが有効化されていることを確認
      - 2026-06-27: コンテナ起動および疎通テスト完了。

## Phase 2: コーディングエージェント (aider) の接続
- [x] `.aider.conf.yml` の作成 (LiteLLMをプロバイダーとして設定)
- [x] `aider_setup_guide.md` の作成 (Neovim環境およびシェルからの起動・設定方法)
- [x] LiteLLMのプロンプトガードレール設定 (XMLタグの強制解釈指示の追加)
      - 2026-06-27: 設定ファイルの作成、Neovim/Aider向けセットアップガイド作成、LiteLLMにシステムプロンプトの形でXML解釈のガードレールを設定完了。

## Phase 3: RAG基盤 (Dify) の構築
- [x] `docker-compose.yml` にDifyの関連コンテナ群 (db, redis, weaviate, api, web等) を追記
- [x] ポート8080でDify of Web UIが起動することを確認
- [x] `dify_setup_guide.md` を作成し、LiteLLMをシステムモデルとして登録する手順を明記
      - 2026-06-27: DifyのCompose構成をマージし、ポート8080で起動を確認。疎通確認とヘルスチェックテストコード `tests/test_phase3.py` を実装しテスト合格。セットアップガイドも作成。

## Phase 4: ローカルLLM (Ollama) のハイブリッド運用テスト
- [x] `ollama_setup_guide.md` の作成 (Macネイティブでの `qwen2.5-coder:3b` 起動コマンド等)
- [x] `litellm_config.yaml` を更新し、ホスト側 (host.docker.internal:11434) へのルーティングを追加
- [x] LiteLLM Proxyを再起動し、疎通確認を実施する
- [x] 結合テストを行い、ルーティングが正常に動作することを確認する
      - 2026-06-27: ガイドの作成、Ollamaルーティング設定の追加、コンテナ再起動、テストコード `tests/test_phase4.py` によるルーティング登録テスト合格。

## Phase 5: 高度なPoC機能 (同期・MCP・自己修復・ログローテーション) の実装
- [x] ドキュメント自動同期スクリプト `sync_docs.py` の作成 (watchdogを用いてローカルフォルダを監視し、Dify APIへ送信)
- [x] MCPサーバー用設定 of 雛形 `mcp_server.py` の作成 (Dify等と連携させるプロトコル実装)
- [x] ログの自動クリーンアップスクリプト `log_cleanup.sh` の作成 (ログローテーションと古いファイルの削除)
- [x] 自己修復ワークフローの設計書 `auto_fix_workflow.md` の作成
      - 2026-06-27: 各スクリプトの実装完了、自己修復設計書の作成、`tests/test_phase5.py` による各機能の結合・単体テスト合格。
