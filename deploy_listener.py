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
        
        # AUTO_DEPLOY=1 を設定して ragy を実行させ、親のキルによるシグナル強制終了を回避します。
        deploy_cmd = (
            "sleep 2 && "
            "echo '\\n--- Automated Deploy Triggered ---' >> deploy.log 2>&1 && "
            "git checkout main >> deploy.log 2>&1 && "
            "git pull origin main >> deploy.log 2>&1 && "
            "AUTO_DEPLOY=1 ./ragy restart >> deploy.log 2>&1"
        )
        
        subprocess.Popen(
            ["sh", "-c", deploy_cmd],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        logging.info("Deploy command triggered. Self-exiting to release port 8000...")
        
        # Uvicornがクライアント（GitHub）へ 200 OK レレスポンスを返し終えるのを待ってから自身を即座に終了する
        import time
        time.sleep(1.5)
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
    pid_file = "deploy_listener.pid"
    with open(pid_file, "w") as f:
        f.write(str(os.getpid()))
        
    try:
        uvicorn.run(app, host="0.0.0.0", port=PORT)
    finally:
        # 終了時にPIDファイルを削除
        if os.path.exists(pid_file):
            os.remove(pid_file)
