---
type: "guide"
title: "Dify セットアップガイド"
description: "Dify と LiteLLM Proxy を連携させ、Gemini をシステムモデルとして登録する手順"
tags: ["dify", "litellm", "gemini"]
timestamp: "2026-06-27T13:35:00Z"
---

# Dify + LiteLLM 連携セットアップガイド

本ガイドは、Dify の Web UI から LiteLLM Proxy を経由して Gemini 3.5 Flash をカスタムモデルとして登録・利用する手順について説明します。

---

## 1. Dify 起動の確認

ブラウザを開き、以下の URL にアクセスしてください。

- **URL**: [http://localhost:8080](http://localhost:8080)
- 初回アクセス時は、管理者アカウントの初期設定画面が表示されます。メールアドレスとパスワードを設定してログインしてください。

---

## 2. LiteLLM Proxy モデルの追加

Dify ログイン後、以下の手順で LiteLLM Proxy（Gemini）を追加します。

### ステップ 1: 設定画面を開く
1. 右上のアカウントアイコンをクリックし、**「設定 (Settings)」** を選択します。
2. 左メニューから **「モデルプロバイダー (Model Provider)」** を選択します。

### ステップ 2: OpenAI 互換プロバイダーの追加
1. **「OpenAI-compatible」**（またはカスタムプロバイダー）を見つけ、**「追加する (Add Custom Model)」** をクリックします。
2. ポップアップ画面で、以下の接続情報を入力します：

   - **モデルタイプ (Model Type)**: `LLM`
   - **モデル名 (Model Name)**: `gemini-3.5-flash`
   - **APIキー (API Key)**: `sk-1234`
   - **APIベースURL (API Base URL)**: `http://litellm:4000/v1`
     - *注意: Dify と LiteLLM は同じ Docker Compose ネットワーク内にいるため、コンテナのサービス名 `litellm` で直接通信できます。*

### ステップ 3: 保存とテスト
1. **「保存 (Save)」** をクリックします。
2. 接続テストが自動的に実行され、エラーが出なければ登録完了です。これで Dify 内で `gemini-3.5-flash` が選択可能になります。
