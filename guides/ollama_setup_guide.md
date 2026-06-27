---
type: "guide"
title: "Ollama セットアップガイド"
description: "Macホスト上で Ollama を起動し、LiteLLM からルーティング可能にする手順"
tags: ["ollama", "litellm", "local-llm"]
timestamp: "2026-06-27T13:47:00Z"
---

# Ollama ローカルLLM セットアップガイド

本ガイドは、Mac ホストマシン上で Ollama を起動し、Docker コンテナ内の LiteLLM Proxy からルーティングできるようにするための手順です。

---

## 1. Ollama のインストールとモデル取得

### ステップ 1: Ollama のインストール
1. [Ollama 公式サイト](https://ollama.com/) から Mac 版アプリをダウンロードし、インストールします。
2. アプリを起動し、メニューバーに Ollama のアイコンが表示されていることを確認します。

### ステップ 2: モデルのプル
ターミナルを開き、指定されたモデルをプルして動作確認を行います。

```bash
# qwen2.5-coder:3b のプルと起動確認
ollama run qwen2.5-coder:3b
```

---

## 2. 外部（Dockerコンテナ）からのアクセス許可

Docker コンテナ内の LiteLLM からホストの Ollama API にアクセスさせるため、Ollama のリッスンアドレスを `0.0.0.0` に設定します。

### 設定方法 (Mac の場合)
ターミナルで以下の環境変数を設定して Ollama を起動するか、すでにアプリが起動している場合は一度終了し、環境変数を設定した状態でシェルから起動します。

```bash
# 環境変数を設定して Ollama を起動
launchctl setenv OLLAMA_HOST "0.0.0.0"

# または、ターミナルで直接以下を実行して起動
OLLAMA_HOST=0.0.0.0 ollama serve
```

---

## 3. LiteLLM Proxy でのルーティング定義

LiteLLM は `host.docker.internal` を介して Mac ホスト上で動く Ollama にアクセスします。

### `litellm_config.yaml` のルーティング定義
```yaml
model_list:
  - model_name: qwen2.5-coder
    litellm_params:
      model: ollama/qwen2.5-coder:3b
      api_base: "http://host.docker.internal:11434"
```
これで、LiteLLM に `qwen2.5-coder` という名前でリクエストを送ると、ローカルホスト上の Ollama で推論が実行されます。
