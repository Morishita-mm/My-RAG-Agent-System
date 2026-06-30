import os
import subprocess

def get_current_project():
    # 1. 最優先：親ディレクトリを遡って .rag-project ファイルを探索・読込
    try:
        curr = os.getcwd()
        while True:
            local_config = os.path.join(curr, ".rag-project")
            if os.path.exists(local_config):
                with open(local_config, "r", encoding="utf-8") as f:
                    val = f.read().strip()
                    if val:
                        return val
            parent = os.path.dirname(curr)
            if parent == curr:
                break
            curr = parent
    except Exception:
        pass

    # 2. カレントディレクトリが所属している Git リポジトリ名
    try:
        toplevel = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            text=True
        ).strip()
        repo_name = os.path.basename(toplevel)
        if repo_name:
            return repo_name
    except Exception:
        pass

    # 3. カレントディレクトリ名
    try:
        cwd_name = os.path.basename(os.getcwd())
        if cwd_name:
            return cwd_name
    except Exception:
        pass

    # 4. 環境変数名 (CURRENT_PROJECT or PROJECT_ID)
    return os.environ.get("CURRENT_PROJECT") or os.environ.get("PROJECT_ID") or os.path.basename(os.getcwd())
