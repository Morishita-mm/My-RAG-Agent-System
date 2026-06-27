---
type: "guide"
title: "aider セットアップガイド"
description: "Neovim環境およびターミナルから Aider を使用して LiteLLM Proxy 経由で Gemini を呼び出すための手順"
tags: ["aider", "neovim", "litellm"]
timestamp: "2026-06-27T13:02:00Z"
---

# aider + Neovim セットアップガイド

本ガイドは、Neovim またはターミナル環境から、ローカルに起動した LiteLLM Proxy（ポート4000）を介して、Gemini API を使用した AI ペアプログラミング環境を構築するためのものです。

---

## 1. 前提条件

- `docker-compose.yml` で LiteLLM Proxy が正常に起動していること（`http://localhost:4000`）。
- `aider` コマンドがホストマシンにインストールされていること。
  - 未インストールの場合は、以下でインストールしてください：
    ```bash
    # pipxによる推奨インストール
    pipx install aider-chat
    ```

---

## 2. Aider の設定ファイル

プロジェクトルートに配置された `.aider.conf.yml` が Aider 起動時に自動的に読み込まれます。

### `.aider.conf.yml` の記述内容
```yaml
# 指定するモデル名（LiteLLM Proxyで定義されたモデル名）
model: "openai/gemini-3.5-flash"

# LiteLLM Proxyのエンドポイント
openai-api-base: "http://localhost:4000/v1"

# LiteLLM Proxyのマスターキー
openai-api-key: "sk-1234"

# 自動コミットの設定（Git規約に基づき自動コミットは無効化）
auto-commits: false
```

---

## 3. Aider の起動方法

プロジェクトのルートディレクトリで、単に `aider` コマンドを実行するだけで、上記の設定が自動的に適用されて起動します。

```bash
# プロジェクトルートで実行
aider
```

特定のファイルのみを対象にする場合は、ファイルを指定して起動できます：
```bash
aider src/main.py docs/README.md
```

---

## 4. Neovim との連携方法

Aider は Neovim の中で快適に利用することができます。

### 方法 A: Neovim 内蔵ターミナルの利用 (シンプル)
Neovim を開き、以下のコマンドを実行して内蔵ターミナルから `aider` を起動します。

```vim
:terminal aider
```

### 方法 B: aider.nvim プラグインの利用 (推奨)
Neovim で Aider をフローティングウィンドウなどで管理するために、コミュニティ製プラグイン [aider.nvim](https://github.com/GeorgesPierre/aider.nvim) などを導入すると、ショートカットキーによる操作が可能になります。

**lazy.nvim での導入例**:
```lua
{
  "GeorgesPierre/aider.nvim",
  keys = {
    { "<leader>aa", "<cmd>AiderOpen<cr>", desc = "Open Aider" },
    { "<leader>ac", "<cmd>AiderAddCurrentFile<cr>", desc = "Add current file to Aider" },
  },
  opts = {
    -- 必要に応じてデフォルト引数を設定可能
  }
}
```

---

## 5. トラブルシューティング

### 5.1 Connection Refused エラー
- **原因**: LiteLLM Proxy コンテナが起動していないか、ポートが競合しています。
- **対処**: ホストマシンで `docker compose ps` を実行し、`litellm_proxy` が `Up` 状態かつポート `4000` をバインドしているか確認してください。

### 5.2 APIキーエラー (401 Unauthorized / Invalid Key)
- **原因**: Aider が送信したキーが LiteLLM Proxy の `master_key` と一致していないか、LiteLLM が Gemini API キーを取得できていません。
- **対処**:
  1. `.aider.conf.yml` の `openai-api-key` が `sk-1234` であるか確認します。
  2. プロジェクトの `.env` ファイルに `GEMINI_API_KEY` が正しく設定されていることを確認してください。
