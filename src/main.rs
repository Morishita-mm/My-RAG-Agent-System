mod cli;
mod tui;

use cli::{Cli, Commands};
use clap::Parser;
use std::process::{Command, ExitStatus};
use std::io;
use std::net::TcpStream;
use std::time::Duration;

fn check_tcp_port(addr: &str) -> bool {
    use std::net::ToSocketAddrs;
    if let Ok(mut addrs) = addr.to_socket_addrs() {
        if let Some(socket_addr) = addrs.next() {
            return TcpStream::connect_timeout(&socket_addr, Duration::from_millis(500)).is_ok();
        }
    }
    false
}

fn check_process(name: &str) -> bool {
    if let Ok(output) = Command::new("pgrep").args(&["-f", name]).output() {
        output.status.success() && !output.stdout.is_empty()
    } else {
        false
    }
}



use crate::tui::app::get_project_root;

fn run_core_command(subcmd: &str, args: &[&str]) -> io::Result<ExitStatus> {
    let project_root = get_project_root();
    let script_path = project_root.join("scripts/ragy_core.sh");
    
    let mut cmd_args = vec![script_path.to_string_lossy().to_string()];
    cmd_args.push(subcmd.to_string());
    for arg in args {
        cmd_args.push(arg.to_string());
    }
    
    Command::new("bash")
        .args(&cmd_args)
        .status()
}

#[tokio::main]
async fn main() -> io::Result<()> {
    // 1. プロジェクトルートを特定し、.env の環境変数をロード
    let _ = dotenvy::from_path(get_project_root().join(".env"));

    let args = Cli::parse();

    match args.command {
        Commands::Start => {
            let _ = run_core_command("start", &[]);
        }
        Commands::Stop => {
            let _ = run_core_command("stop", &[]);
        }
        Commands::Restart => {
            let _ = run_core_command("restart", &[]);
        }
        Commands::Status { detail, docs } => {
            println!("=== RAG System Status ===");
            
            let ollama_status = if check_tcp_port("127.0.0.1:11434") {
                "RUNNING (127.0.0.1:11434)"
            } else {
                "STOPPED"
            };
            println!("Ollama          : {}", ollama_status);

            let redis_status = if check_tcp_port("127.0.0.1:6379") {
                "RUNNING (127.0.0.1:6379)"
            } else {
                "STOPPED"
            };
            println!("Redis           : {}", redis_status);

            let litellm_status = if check_tcp_port("127.0.0.1:4000") {
                "RUNNING (127.0.0.1:4000)"
            } else {
                "STOPPED"
            };
            println!("LiteLLM Proxy   : {}", litellm_status);

            let dify_status = if check_tcp_port("127.0.0.1:8080") {
                "RUNNING (127.0.0.1:8080)"
            } else {
                "STOPPED"
            };
            println!("Dify Gateway    : {}", dify_status);

            let watchdog_status = if check_process("sync_docs.py") {
                "RUNNING"
            } else {
                "STOPPED"
            };
            println!("Sync Watchdog   : {}", watchdog_status);

            let listener_status = if check_process("deploy_listener.py") {
                "RUNNING"
            } else {
                "STOPPED"
            };
            println!("Deploy Listener : {}", listener_status);

            let worker_status = if check_process("worker.py") {
                "RUNNING"
            } else {
                "STOPPED"
            };
            println!("Queue Worker    : {}", worker_status);

            let ngrok_status = if check_process("ngrok http") {
                "RUNNING"
            } else {
                "STOPPED"
            };
            println!("Ngrok Tunnel    : {}", ngrok_status);

            if detail {
                println!("\n=== Detailed Docker Containers ===");
                let mut cmd = Command::new("docker");
                cmd.args(&["compose", "ps"]);
                let _ = cmd.status();
            }

            let project_root = get_project_root();
            let sync_script = project_root.join("scripts/sync_status.py");
            
            let mut sync_args = vec![sync_script.to_string_lossy().to_string()];
            if docs {
                sync_args.push("--docs".to_string());
            }
            let mut cmd = Command::new("python3");
            cmd.args(&sync_args);
            let _ = cmd.status();
        }
        Commands::Sync => {
            let _ = run_core_command("sync", &[]);
        }
        Commands::Tui => {
            if let Err(e) = tui::run_tui().await {
                eprintln!("TUI Error: {}", e);
            }
        }
        Commands::Doctor => {
            run_doctor_diagnosis();
        }
        Commands::Init { dataset_id } => {
            let args_vec = if let Some(ref id) = dataset_id {
                vec![id.as_str()]
            } else {
                vec![]
            };
            let _ = run_core_command("init", &args_vec);
        }
    }

    Ok(())
}

fn run_doctor_diagnosis() {
    println!("=== Ragy Environment Diagnostics (Doctor) ===");

    // 1. CLI ツールの存在確認
    println!("\n[1] Checking Required CLI Tools...");
    let cli_tools = vec![
        ("docker", "--version"),
        ("gh", "--version"),
        ("ngrok", "--version"),
        ("python3", "--version"),
    ];

    for (tool, version_flag) in cli_tools {
        match Command::new("which").arg(tool).output() {
            Ok(output) if output.status.success() => {
                let version = if let Ok(v_out) = Command::new(tool).arg(version_flag).output() {
                    let v_str = String::from_utf8_lossy(&v_out.stdout).trim().to_string();
                    v_str.lines().next().unwrap_or("").to_string()
                } else {
                    "Unknown version".to_string()
                };
                println!("  \x1b[32m✔\x1b[0m {:<10}: Found ({})", tool, version);
            }
            _ => {
                println!("  \x1b[31m✘\x1b[0m {:<10}: NOT Found", tool);
            }
        }
    }

    // 2. Python パッケージの依存チェック
    println!("\n[2] Checking Python Library Dependencies...");
    let python_libs = vec![
        "fastapi",
        "uvicorn",
        "redis",
        "langsmith",
        "google.antigravity",
    ];

    for lib in python_libs {
        let check_cmd = format!("import {}; print('OK')", lib);
        match Command::new("python3").args(&["-c", &check_cmd]).output() {
            Ok(output) if output.status.success() => {
                println!("  \x1b[32m✔\x1b[0m {:<20}: Available", lib);
            }
            _ => {
                println!("  \x1b[31m✘\x1b[0m {:<20}: NOT Available (Install via 'pip install' or 'uv pip install')", lib);
            }
        }
    }

    // 3. バインドポート競合チェック
    println!("\n[3] Checking Bound Port Conflict (TCP)...");
    let ports = vec![
        ("LiteLLM Proxy", 4000),
        ("Valkey/Redis", 6379),
        ("Deploy Webhook", 8000),
        ("Dify Gateway", 8080),
    ];

    for (name, port) in ports {
        let addr = format!("127.0.0.1:{}", port);
        if check_tcp_port(&addr) {
            println!("  \x1b[33m⚠\x1b[0m Port {:<4} ({:<15}): Bound (Service running or port in use)", port, name);
        } else {
            println!("  \x1b[32m✔\x1b[0m Port {:<4} ({:<15}): Available", port, name);
        }
    }

    // 4. 環境変数ファイルと必須項目の確認
    println!("\n[4] Validating Configuration Files & Envs...");
    let project_root = get_project_root();
    let dotenv_path = project_root.join(".env");
    if dotenv_path.exists() {
        println!("  \x1b[32m✔\x1b[0m .env File : Found ({})", dotenv_path.to_string_lossy());
        let env_keys = vec![
            "REDIS_PASSWORD",
            "DIFY_API_BASE",
            "GITHUB_WEBHOOK_SECRET",
        ];
        for key in env_keys {
            if let Ok(val) = std::env::var(key) {
                if val.is_empty() {
                    println!("    \x1b[33m⚠\x1b[0m Env {:<25}: Found, but value is EMPTY", key);
                } else {
                    println!("    \x1b[32m✔\x1b[0m Env {:<25}: Configured", key);
                }
            } else {
                println!("    \x1b[31m✘\x1b[0m Env {:<25}: NOT Configured", key);
            }
        }
    } else {
        println!("  \x1b[31m✘\x1b[0m .env File : NOT Found (Prepare from envs/middleware.env.example)");
    }

    let home = std::env::var("HOME").unwrap_or_else(|_| "/Users/mzk".to_string());
    let global_env_path = std::path::PathBuf::from(home).join(".ragy/env");
    if global_env_path.exists() {
        println!("  \x1b[32m✔\x1b[0m ~/.ragy/env File: Found");
    } else {
        println!("  \x1b[33m⚠\x1b[0m ~/.ragy/env File: NOT Found (Global config missing, using defaults)");
    }

    println!("\n=== Diagnostics Completed ===");
}
