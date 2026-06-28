
# Getting Started: 環境構築ガイド

本プラットフォームは、設定の分離（12 Factor Appの原則）に基づき、**「グローバルなツール設定」**と**「プロジェクト固有の設定」**を明確に分けて管理します。

## 1. 前提条件

以下のソフトウェアがインストールされていることを確認してください。

* Docker & Docker Compose
* Ollama (Macネイティブ推奨)
* Python 3.10+

## 2. グローバル設定の初期化

ツール全体で共通して使用する設定（APIのベースURLや、使用するローカルモデル名など）は、ホームディレクトリの `~/.ragy/env` に保存します。

```bash
mkdir -p ~/.ragy

cat <<EOF > ~/.ragy/env
# Ragy Global Configuration
DIFY_API_BASE="http://localhost:8080/v1"
LLM_MODEL="llama3.2"
MCP_COMMAND="python3"
EOF

```

## 3. リポジトリのクローンと起動

プラットフォームの本体をクローンし、インフラ群（Dify, LiteLLM, Redis, Weaviateなど）を一括起動します。

```bash
git clone [https://github.com/Morishita-mm/My-RAG-Agent-System.git](https://github.com/Morishita-mm/My-RAG-Agent-System.git)
cd My-RAG-Agent-System

# .envファイルの準備 (APIキー等を設定)
cp envs/middleware.env.example .env

# システムの一括起動
./ragy start

```

起動後、以下のサービスがローカルで利用可能になります。

* **Dify UI**: `http://localhost:8080`
* **LiteLLM Proxy**: `http://localhost:4000`
* **Ollama**: `http://localhost:11434`
