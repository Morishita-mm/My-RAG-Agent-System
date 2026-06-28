
# Development Workflow: 開発とRAG同期フロー

このシステムは、開発ディレクトリを作るだけで、AIエディタ（Aider/Continue）の設定からDifyへのRAGナレッジ同期までを自動化します。

## 1. プロジェクトの初期化 (`ragy init`)

新しく開発を始めるプロジェクトディレクトリで `ragy init` を実行します。

```bash
cd /path/to/your/new_project
/path/to/My-RAG-Agent-System/ragy init

```

**このコマンドが行うこと:**

1. Dify上に専用のデータセット（ナレッジベース）を自動作成します。
2. プロジェクト内に `docs/` ディレクトリ（シンボリックリンク）を生成します。
3. テンプレートから `.aider.conf.yml` と `.continue/config.json` を自動展開し、IDEを開いた瞬間からローカルAIが使える状態にします。

## 2. プロジェクト固有設定 (`.env`)

初期化後、プロジェクト直下に `.env` ファイルを作成し、DifyのデータセットIDを登録します。（このファイルはGitで管理可能です）

```text
# /path/to/your/new_project/.env
DIFY_DATASET_ID="<自動生成されたID>"
DIFY_DATASET_API_KEY="<DifyのAPIキー>"

```

## 3. ナレッジの一括同期 (`ragy sync`)

`docs/` フォルダにMarkdownやテキストファイルを配置した後、手動で一括同期を行いたい場合は `sync` コマンドを使用します。

```bash
cd /path/to/your/new_project
/path/to/My-RAG-Agent-System/ragy sync

```

* `ragy` コマンドがカレントディレクトリの `.env` とグローバルの `~/.ragy/env` をマージして同期スクリプトに渡します。
* `sync_docs.py` がDifyのAPI仕様（multipart/form-data内の `data` フィールドへのJSON文字列化）に準拠し、確実なアップロードを行います。

## 4. コーディング (Aider & Continue)

設定ファイルはすでに生成されているため、そのままエディタを開くか Aider を起動するだけで、Difyのナレッジを背景に持ったAI開発がスタートできます！
