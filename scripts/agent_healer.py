import asyncio
import os
import sys
import re
import subprocess
import logging
import uuid
import pydantic
import dotenv
import yaml
import requests
from google.antigravity import Agent, LocalAgentConfig

# 環境変数のロード
dotenv.load_dotenv()

# litellm_config.yaml のグローバルパス定義
script_dir = os.path.dirname(os.path.abspath(__file__))
LITELLM_CONFIG_PATH = os.path.abspath(os.path.join(script_dir, "../litellm_config.yaml"))

# ログ設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class CodeFixProposal(pydantic.BaseModel):
    file_path: str
    explanation: str
    modified_code: str

class PromptFixProposal(pydantic.BaseModel):
    model_name: str
    explanation: str
    optimized_prompt: str

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
            attempts = 3
            current_error = error_log
            current_code = original_content
            proposal = None
            
            for attempt in range(1, attempts + 1):
                logging.info(f"Self-healing attempt {attempt}/{attempts} for {file_path}...")
                
                # 2回目以降はエラーをコンテキストに含めて再度LLMに問い合わせる
                if attempt > 1:
                    retry_prompt = f"""
PythonスクリプトまたはRustコード `{file_path}` で修正を試みましたが、ビルド・構文検証でエラーが発生しました。

【発生したコンパイラ/インタープリタのエラー内容】
{current_error}

【直前のソースコード】
```
{current_code}
```

このエラーの原因を分析し、エラーが発生しないよう修正されたコードを再生成してください。
修正コードは、ファイル全体の完全なコードにしてください。
"""
                    response = await agent.chat(retry_prompt)
                    proposal = await response.structured_output()
                else:
                    response = await agent.chat(prompt)
                    proposal = await response.structured_output()
                
                if not proposal:
                    logging.error("Failed to generate structured proposal from agent.")
                    return False
                    
                explanation = proposal.get("explanation")
                modified_code = proposal.get("modified_code")
                
                logging.info(f"Attempt {attempt}: Agent explanation: {explanation}")
                logging.info(f"Applying proposed fix to {file_path}...")
                
                # 修正コードの書き込み
                with open(file_path, 'w', encoding='utf-8') as f_out:
                    f_out.write(modified_code)
                    
                # ビルド・構文検証の実行
                validation_success = True
                validation_error_log = ""
                
                if file_path.endswith(".py"):
                    res = subprocess.run([sys.executable, "-m", "py_compile", file_path], capture_output=True, text=True)
                    if res.returncode != 0:
                        validation_success = False
                        validation_error_log = res.stderr
                        logging.error(f"Syntax validation failed for {file_path}:\n{res.stderr}")
                elif file_path.endswith(".rs"):
                    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    res = subprocess.run(["cargo", "check"], cwd=project_root, capture_output=True, text=True)
                    if res.returncode != 0:
                        validation_success = False
                        validation_error_log = res.stderr
                        logging.error(f"Cargo check failed:\n{res.stderr}")
                
                if validation_success:
                    logging.info(f"Successfully validated applied fix for {file_path} on attempt {attempt}.")
                    # 検証がパスしたため、PRを作成
                    return create_github_pull_request(file_path, explanation, error_log)
                else:
                    current_error = f"Validation failed. Compiler/syntax checker output:\n{validation_error_log}"
                    current_code = modified_code
            
            # 全ての試行が失敗した場合、元の状態に復元して終了
            logging.error(f"Failed to automatically heal and validate {file_path} after {attempts} attempts. Restoring original content.")
            with open(file_path, 'w', encoding='utf-8') as f_restore:
                f_restore.write(original_content)
            return False
            
    except Exception as e:
        logging.error(f"Error during self-healing agent turn: {e}")
        return False

def get_current_system_prompt(model_name: str) -> str:
    if os.path.exists(LITELLM_CONFIG_PATH):
        try:
            with open(LITELLM_CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            for model in data.get("model_list", []):
                if model.get("model_name") == model_name:
                    return model.get("litellm_params", {}).get("system_prompt", "")
        except Exception as e:
            logging.error(f"Failed to read current prompt: {e}")
    return ""

def update_litellm_config_prompt(model_name: str, new_prompt: str) -> bool:
    if not os.path.exists(LITELLM_CONFIG_PATH):
        logging.error(f"litellm_config.yaml not found at: {LITELLM_CONFIG_PATH}")
        return False
        
    try:
        with open(LITELLM_CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        updated = False
        for model in data.get("model_list", []):
            if model.get("model_name") == model_name:
                model.setdefault("litellm_params", {})["system_prompt"] = new_prompt
                updated = True
                break
                
        if updated:
            with open(LITELLM_CONFIG_PATH, 'w', encoding='utf-8') as f:
                yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
            logging.info(f"Successfully updated system prompt for model '{model_name}' in litellm_config.yaml")
            return True
        else:
            logging.error(f"Model '{model_name}' not found in litellm_config.yaml")
    except Exception as e:
        logging.error(f"Failed to update litellm_config.yaml: {e}")
    return False

async def optimize_prompt_with_dify_or_sdk(current_prompt: str, error_log: str, model_name: str) -> PromptFixProposal:
    dify_api_base = os.environ.get("DIFY_WORKFLOW_API_BASE", "http://localhost:8080/v1")
    dify_api_key = os.environ.get("DIFY_WORKFLOW_API_KEY")
    
    # 1. DifyワークフローAPIが設定されている場合は呼び出し
    if dify_api_key:
        logging.info("Initiating prompt optimization using Dify Workflow API...")
        url = f"{dify_api_base.rstrip('/')}/workflows/run"
        headers = {
            "Authorization": f"Bearer {dify_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "inputs": {
                "current_prompt": current_prompt,
                "error_log": error_log,
                "model_name": model_name
            },
            "response_mode": "blocking",
            "user": "agent-healer"
        }
        try:
            response = await asyncio.to_thread(
                requests.post, url, headers=headers, json=payload, timeout=30
            )
            if response.status_code == 200:
                res_data = response.json()
                outputs = res_data.get("data", {}).get("outputs", {})
                optimized = outputs.get("optimized_prompt") or outputs.get("result")
                explanation = outputs.get("explanation", "Optimized via Dify Workflow.")
                if optimized:
                    return PromptFixProposal(
                        model_name=model_name,
                        explanation=explanation,
                        optimized_prompt=optimized
                    )
            logging.error(f"Dify Workflow API returned status {response.status_code}: {response.text}")
        except Exception as e:
            logging.error(f"Error calling Dify Workflow API: {e}")
            
    # 2. フォールバック: Antigravity SDK Agent による自己プロンプト修復
    logging.info("Using Antigravity SDK Agent for prompt optimization...")
    prompt = f"""
モデル `{model_name}` のシステムプロンプトを使用して推論を実行した際、出力フォーマット等のエラーが発生しました。

【エラーログ】
{error_log}

【現在のシステムプロンプト】
{current_prompt}

このエラーを解消するため、指示をより厳密かつ明瞭にし、エラーを回避できる改善されたシステムプロンプトを提案してください。
XMLタグの厳密な出力、JSONフォーマットの遵守など、エラーログの原因にフォーカスして指示を補強してください。
"""
    config = LocalAgentConfig(
        response_schema=PromptFixProposal,
    )
    try:
        async with Agent(config) as agent:
            response = await agent.chat(prompt)
            proposal = await response.structured_output()
            if proposal:
                return PromptFixProposal(**proposal)
    except Exception as e:
        logging.error(f"Failed to optimize prompt via Antigravity SDK Agent: {e}")
        
    return None

async def heal_prompt(model_name: str, error_log: str) -> bool:
    logging.info(f"Initiating prompt self-healing for model: {model_name}")
    current_prompt = get_current_system_prompt(model_name)
    
    proposal = await optimize_prompt_with_dify_or_sdk(current_prompt, error_log, model_name)
    if not proposal:
        logging.error("Failed to generate prompt fix proposal.")
        return False
        
    logging.info(f"Optimized Prompt Explanation: {proposal.explanation}")
    
    success = update_litellm_config_prompt(model_name, proposal.optimized_prompt)
    if success:
        return create_github_pull_request(
            LITELLM_CONFIG_PATH, 
            f"Model: {model_name}\n\nExplanation: {proposal.explanation}", 
            error_log
        )
    return False

def detect_prompt_error(log_segment: str) -> bool:
    patterns = [
        r"XML parsing failed", 
        r"Invalid XML format", 
        r"Failed to parse XML", 
        r"Invalid JSON format", 
        r"Output must contain XML tags", 
        r"does not match response schema"
    ]
    for pattern in patterns:
        if re.search(pattern, log_segment, re.IGNORECASE):
            return True
    return False

def extract_model_from_log(log_segment: str) -> str:
    model_name = "gemini-3.5-flash"
    model_match = re.search(r"model[\"'\s:=]+([a-zA-Z0-9\.\-_]+)", log_segment)
    if model_match:
        model_name = model_match.group(1)
    return model_name

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
            
            # プロンプト起因のエラーパターン検出
            is_prompt_error = detect_prompt_error(new_logs)
                    
            if is_prompt_error:
                logging.warning("Prompt output formatting error detected in logs!")
                lines = [l for l in new_logs.split('\n') if l.strip()]
                error_key = lines[-1] if lines else "prompt_error"
                
                if error_key not in processed_errors:
                    processed_errors.add(error_key)
                    # ログからモデル名を抽出
                    model_name = extract_model_from_log(new_logs)
                    
                    success = await heal_prompt(model_name, new_logs)
                    if success:
                        logging.info("Prompt healing workflow completed successfully.")
                    else:
                        logging.error("Prompt healing workflow failed.")
                        
            # 例外（Traceback）の検出
            elif "Traceback (most recent call last):" in new_logs:
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
    log_path = "./logs/sync_docs.log"
    if len(sys.argv) > 1:
        log_path = sys.argv[1]
    
    await monitor_log_file(log_path)

if __name__ == "__main__":
    asyncio.run(main())
