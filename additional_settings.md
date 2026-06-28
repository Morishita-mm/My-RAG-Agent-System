# 引継ぎサマリー (Checkpoint 10)

## 1. Outstanding User Requests (残りのユーザー要求)
- **ステータス**: `COMPLETED`
- **残タスク**: 開発タスクはすべて完了しました。Phase（1〜5）、追加要件（キャッシュ、LangSmith、Healer、自動デプロイ）、および今回追加された `ragy sync` コマンドの実装・動作検証が正常に完了し、リポジトリにプッシュ済みです。

---

## 2. User Knowledge (ユーザーナレッジ・仕様上の重要点)
- **プロジェクト分離型セマンティックキャッシュ**:
  - セマンティックキャッシュの照会・保存時、同一 of 質問であってもプロジェクト名（`CURRENT_PROJECT`）でキャッシュキー空間を厳密に分離しています。
- **自動デプロイ Webhook パイプライン**:
  - `deploy_listener.py` を FastAPI で新規実装。GitHub webhook をトリガーに、非同期で `git pull origin main` および `./ragy restart` を走らせる仕組み。ngrokによる外部連携も正常稼働確認済み。
- **`ragy init` によるプロジェクト一括初期化**:
  - `ragy init [dataset_id]` コマンドにより、実行された各プロジェクトディレクトリで Dify データセット自動作成（未指定時）、`docs/` 実体サブディレクトリ作成、シンボリックリンクの自動マッピング、および設定テンプレート（aider / continue）のプレースホルダ置換（モデル・APIキー）を自動展開します。
- **`ragy sync` による一括同期ワークフロー**:
  - プロジェクトディレクトリ内で `ragy sync` を実行することで、`docs/` 内の全Markdownファイルを Dify データセットへ一括で追加、更新（差分）、削除同期（クリーンアップ）できます。既存プロジェクトのドキュメント移行も、初期化後の `docs/` にファイルを配置して `ragy sync` するだけで完了します。

---

## 3. Model Knowledge (モデルが得た技術的知見・注意点)
- **macOS におけるマルチスレッド環境下での fork 制限の回避**:
  - macOS (Darwin) では、Uvicorn などのマルチスレッド Python プロセスから直接 `os.fork()` してデーモン化しようとすると、システムライブラリ（CoreFoundation）の安全制限により子プロセスが `SIGABRT` で即時強制終了されます。
  - 解決策として、`subprocess.Popen` に `start_new_session=True` を指定して起動することで、fork 制限に抵触せず、かつ親のキルによるシグナルが伝播しない、完全に独立したセッション of バックグラウンドプロセスとして実行させました。
- **自動デプロイ再起動時のシグナル連鎖死（SIGHUP/SIGPIPE）の完全回避**:
  - Webhookレシーバープロセスが再起動処理中に外部からキル（kill）されると、OS がプロセスツリー全体を強制クリーンアップしてしまい、デプロイスクリプト（`sh`）まで巻き込んで終了する現象が発生しました。
  - **回避策1**: デプロイコマンド実行時に `AUTO_DEPLOY=1` を指定し、`ragy` スクリプト内での Webhook レシーバーのキル処理をスキップ。
  - **回避策2**: Webhook レシーバー自身が 200 OK レスポンスを返した直後に `os._exit(0)` で自ら正常終了し、ポート 8000 を即座に解放する。
  - **回避策3**: `ragy` スクリプトの停止処理に、PID が完全に消滅するまで最大 10 秒間待機するループを導入し、ポート再バインドの競合（Address already in use）を排除。
- **Dify API `create_by_file` および `update_by_file` のパラメータ仕様**:
  - Difyのファイル経由ドキュメント登録 API では、`indexing_technique` や `process_rule` などのパラメータを個別のフォームフィールドとして送信すると `indexing_technique is required.` のバリデーションエラーになります。
  - これを回避するため、パラメータはすべて `data` という単一のフォームキーの値に、JSON文字列形式（`json.dumps(...)`）でまとめて格納して送信する必要があります。
- **ファイルハッシュの永続化による一括同期最適化**:
  - コマンド経由での一括同期時に、毎回すべてのファイルを更新APIに送信する無駄を防ぐため、メタデータファイル `.dify_sync_meta.json` にハッシュ（MD5）を `{ "doc_id": "...", "hash": "..." }` の形式で保存する拡張を行いました。古いdoc_idのみの文字列データとの後方互換性も維持されています。

---

## 4. Files and Code (主要ファイル一覧)
- **[mcp_server.py](file:///Volumes/ORICO/src/github.com/Morishita-mm/My-RAG-Agent-System/scripts/mcp_server.py)**: Valkeyセマンティックキャッシュ・Ollamaベクトル類似度計算・LangSmith tracingの統合。
- **[agent_healer.py](file:///Volumes/ORICO/src/github.com/Morishita-mm/My-RAG-Agent-System/scripts/agent_healer.py)**: 自律的エラー修復 & PR自動送信エージェント。
- **[deploy_listener.py](file:///Volumes/ORICO/src/github.com/Morishita-mm/My-RAG-Agent-System/scripts/deploy_listener.py)**: 自動デプロイ Webhook レシーバー。
- **[sync_docs.py](file:///Volumes/ORICO/src/github.com/Morishita-mm/My-RAG-Agent-System/scripts/sync_docs.py)**: Watchdog 監視および `--sync-project` による一括同期対応スクリプト。
- **[ragy](file:///Volumes/ORICO/src/github.com/Morishita-mm/My-RAG-Agent-System/ragy)**: サービスの起動・停止・ステータス・Webhookキルバイパス・プロジェクト初期化（`init`）・一括同期（`sync`）を含む制御CLI。
- **[docker-compose.yml](file:///Volumes/ORICO/src/github.com/Morishita-mm/My-RAG-Agent-System/docker-compose.yml)**: Redisポート公開およびLangSmith連携の定義追加。

---

## 5. Current Work and Next Steps (次の推奨ステップ)
1. **既存プロジェクトの移行検証**:
   - 既存プロジェクトで `ragy init` を実行し、生成された `docs/` ディレクトリにドキュメントを配置して `ragy sync` を行うことで、一括して Dify ナレッジに同期されるワークフローが機能するか再度ご確認ください。
2. **本番運用に向けた動作の確認**:
   - ngrokによるWebhook連携が正常に動作することを確認できたため、引き続きリポジトリへのプッシュを通じた自動デプロイが機能することを確認してください。
