import asyncio
import os
import sys
import re
import subprocess
import logging
import uuid
import pydantic
import dotenv
from google.antigravity import Agent, LocalAgentConfig

# 環境変数のロード
dotenv.load_dotenv()

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class CodeFixProposal(pydantic.BaseModel):
    file_path: str
    explanation: str
    modified_code: str

def create_github_pull_request(file_path: str, explanation: str, error_log: str) -> bool:
    try:
        # ブランチ名の生成
        branch_name = f"fix/auto-heal-{str(uuid.uuid4())[:8]}"
        logging.info(f"Creating new git branch: {branch_name}")
        
        # Git操作
        subprocess.run(["git", "checkout", "-b", branch_name], check=True)
        subprocess.run(["git", "add", file_path], check=True)
        
        commit_message = f"fix: 自動修復エージェントによる {os.path.basename(file_path)} の修正"
        subprocess.run(["git", "commit", "-m", commit_message], check=True)
        
        logging.info(f"Pushing branch {branch_name} to origin...")
        subprocess.run(["git", "push", "origin", branch_name], check=True)
        
        # PRの作成
        pr_title = f"fix(auto-heal): {os.path.basename(file_path)} のエラー自動修復"
        pr_body = f"""## 概要
自動修復エージェントによる自動コード修正です。

### 発生していたエラー
```
{error_log}
```

### 修正理由
{explanation}
"""
        logging.info("Creating GitHub Pull Request...")
        subprocess.run([
            "gh", "pr", "create",
            "--title", pr_title,
            "--body", pr_body,
            "--head", branch_name,
            "--base", "main"
        ], check=True)
        
        logging.info("Successfully created GitHub Pull Request!")
        
        # 元のブランチ（main）に戻る
        subprocess.run(["git", "checkout", "main"], check=True)
        return True
        
    except Exception as e:
        logging.error(f"Failed to create GitHub PR: {e}")
        # 念のため main に戻す
        subprocess.run(["git", "checkout", "main"], check=True)
        return False

async def heal_code(file_path: str, error_log: str) -> bool:
    logging.info(f"Initiating self-healing for file: {file_path}")
    
    if not os.path.exists(file_path):
        logging.error(f"Target file not found: {file_path}")
        return False
        
    with open(file_path, 'r', encoding='utf-8') as f:
        original_content = f.read()

    prompt = f"""
Pythonスクリプト `{file_path}` で以下のエラーが発生しました。

【エラーログ】
{error_log}

【現在のソースコード】
```python
{original_content}
```

このエラーの原因を分析し、修正されたコードを生成してください。
"""

    config = LocalAgentConfig(
        response_schema=CodeFixProposal,
    )

    try:
        async with Agent(config) as agent:
            response = await agent.chat(prompt)
            proposal = await response.structured_output()
            
            if not proposal:
                logging.error("Failed to generate structured proposal from agent.")
                return False
                
            fix_path = proposal.get("file_path")
            explanation = proposal.get("explanation")
            modified_code = proposal.get("modified_code")
            
            logging.info(f"Agent explanation: {explanation}")
            logging.info(f"Applying fix to {file_path}...")
            
            # 修正コードの書き込み
            with open(file_path, 'w', encoding='utf-8') as f_out:
                f_out.write(modified_code)
                
            logging.info(f"Successfully applied fix to {file_path}.")
            
            # Git および GitHub PR 送信
            return create_github_pull_request(file_path, explanation, error_log)
            
    except Exception as e:
        logging.error(f"Error during self-healing agent turn: {e}")
        return False

async def monitor_log_file(log_path: str):
    logging.info(f"Started monitoring log file: {log_path}")
    
    # ログチェック用ポインタ
    last_position = 0
    if os.path.exists(log_path):
        last_position = os.path.getsize(log_path)
        
    # 既に処理したエラーのキャッシュ（同一エラーの連続処理防止）
    processed_errors = set()

    while True:
        await asyncio.sleep(5)
        
        if not os.path.exists(log_path):
            continue
            
        current_size = os.path.getsize(log_path)
        if current_size < last_position:
            # ログがクリアまたはローテートされた
            last_position = 0
            
        if current_size > last_position:
            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                f.seek(last_position)
                new_logs = f.read()
            last_position = current_size
            
            # 例外（Traceback）の検出
            if "Traceback (most recent call last):" in new_logs:
                logging.warning("Python Exception detected in logs!")
                
                # エラーログ部分を切り出す
                tb_start = new_logs.find("Traceback (most recent call last):")
                error_segment = new_logs[tb_start:]
                
                # エラーのユニークなキー（ハッシュやメッセージ）
                lines = [l for l in error_segment.split('\n') if l.strip()]
                if not lines:
                    continue
                error_key = lines[-1]
                
                if error_key in processed_errors:
                    logging.info(f"Error already processed: {error_key}. Skipping.")
                    continue
                    
                processed_errors.add(error_key)
                
                # エラーが発生したファイル名をログから検出
                file_match = re.findall(r'File "([^"]+\.py)", line \d+', error_segment)
                if file_match:
                    target_file = None
                    for f_name in reversed(file_match):
                        # プロジェクト配下のファイルが存在するか確認
                        if os.path.exists(f_name):
                            target_file = f_name
                            break
                    
                    if target_file:
                        success = await heal_code(target_file, error_segment)
                        if success:
                            logging.info("Healing workflow completed successfully.")
                        else:
                            logging.error("Healing workflow failed.")
                    else:
                        logging.error("Could not find local source file for the error.")
                else:
                    logging.error("Could not extract file name from traceback.")

async def main():
    log_path = "./sync_docs.log"
    if len(sys.argv) > 1:
        log_path = sys.argv[1]
    
    await monitor_log_file(log_path)

if __name__ == "__main__":
    asyncio.run(main())
