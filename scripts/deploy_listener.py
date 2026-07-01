import os
import sys
import json
import hmac
import hashlib
import logging
import subprocess
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
import uvicorn
import dotenv

# 環境変数のロード
dotenv.load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = FastAPI(title="Deploy Webhook Listener")

WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET")
PORT = int(os.environ.get("DEPLOY_LISTENER_PORT", 8000))

def verify_signature(payload_body: bytes, signature_header: str) -> bool:
    if not WEBHOOK_SECRET:
        ragy_env = os.environ.get("RAGY_ENV", "production").lower()
        if ragy_env == "production":
            logging.error("GITHUB_WEBHOOK_SECRET is not configured. Rejecting request in production mode.")
            return False
        logging.warning("GITHUB_WEBHOOK_SECRET is not configured. Skipping signature verification (Not secure for production).")
        return True
        
    if not signature_header:
        return False
        
    try:
        sha_name, signature = signature_header.split('=')
        if sha_name != 'sha256':
            return False
    except ValueError:
        return False
        
    mac = hmac.new(WEBHOOK_SECRET.encode(), msg=payload_body, digestmod=hashlib.sha256)
    return hmac.compare_digest(mac.hexdigest(), signature)

def trigger_deploy_script():
    try:
        logging.info("Starting automated deploy workflow...")
        
        # 完全に親プロセスとセッション・シグナルを切り離すため、nohup と & を用いてバックグラウンド実行します。
        # 親が即座に os._exit(0) してポート 8000 を解放した後、1秒後にデプロイ処理を開始します。
        deploy_cmd = (
            "nohup sh -c '"
            "sleep 1 && "
            "echo \"\\n--- Automated Deploy Triggered ---\" >> logs/deploy.log 2>&1 && "
            "git checkout main >> logs/deploy.log 2>&1 && "
            "git pull origin main >> logs/deploy.log 2>&1 && "
            "chmod +x ./ragy >> logs/deploy.log 2>&1 && "
            "xattr -d com.apple.quarantine ./ragy 2>/dev/null || true && "
            "AUTO_DEPLOY=1 bash scripts/ragy_core.sh restart >> logs/deploy.log 2>&1"
            "' >/dev/null 2>&1 &"
        )
        
        subprocess.Popen(
            ["sh", "-c", deploy_cmd],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        logging.info("Deploy command triggered. Self-exiting immediately to release port 8000...")
        os._exit(0)
    except Exception as e:
        logging.error(f"Failed to trigger deploy command: {e}")

@app.post("/webhook")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    payload_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    
    if not verify_signature(payload_body, signature):
        logging.error("Invalid GitHub webhook signature.")
        raise HTTPException(status_code=401, detail="Invalid signature")

    event_type = request.headers.get("X-GitHub-Event", "ping")
    logging.info(f"Received GitHub webhook event: {event_type}")

    if event_type == "ping":
        return {"status": "pong"}

    try:
        payload = json.loads(payload_body.decode())
    except Exception as e:
        logging.error(f"Failed to parse json payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    should_deploy = False

    if event_type == "push":
        ref = payload.get("ref", "")
        if ref == "refs/heads/main":
            should_deploy = True
            logging.info("Detected push to main branch.")

    elif event_type == "pull_request":
        action = payload.get("action", "")
        pr = payload.get("pull_request", {})
        merged = pr.get("merged", False)
        base_ref = pr.get("base", {}).get("ref", "")
        
        if action == "closed" and merged and base_ref == "main":
            should_deploy = True
            logging.info("Detected merged Pull Request to main branch.")

    if should_deploy:
        logging.info("Scheduling deployment task...")
        background_tasks.add_task(trigger_deploy_script)
        return {"status": "deployment_triggered"}

    return {"status": "ignored", "reason": "event_not_applicable"}

if __name__ == "__main__":
    # PIDファイルの書き出し
    pid_file = "logs/deploy_listener.pid"
    os.makedirs(os.path.dirname(pid_file), exist_ok=True)
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))
        
    # GITHUB_WEBHOOK_SECRETの必須チェック (RAGY_ENV=productionかつ未設定ならエラー終了)
    ragy_env = os.environ.get("RAGY_ENV", "production").lower()
    if not WEBHOOK_SECRET:
        if ragy_env == "production":
            logging.critical("FATAL: GITHUB_WEBHOOK_SECRET is not configured in production environment. Aborting startup for safety.")
            sys.exit(1)
        else:
            logging.warning("WARNING: GITHUB_WEBHOOK_SECRET is not configured. Skipping signature verification (Running in INSECURE development mode).")
        
    try:
        uvicorn.run(app, host="0.0.0.0", port=PORT)
    finally:
        # 終了時にPIDファイルを削除
        if os.path.exists(pid_file):
            os.remove(pid_file)
