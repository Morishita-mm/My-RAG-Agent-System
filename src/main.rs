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
    }

    Ok(())
}
