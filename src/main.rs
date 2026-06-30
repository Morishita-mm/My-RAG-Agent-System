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



fn run_core_command(subcmd: &str, args: &[&str]) -> io::Result<ExitStatus> {
    let mut cmd_args = vec![subcmd];
    for arg in args {
        cmd_args.push(arg);
    }
    Command::new("bash")
        .arg("scripts/ragy_core.sh")
        .args(&cmd_args)
        .status()
}

#[tokio::main]
async fn main() -> io::Result<()> {
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

            let mut sync_args = vec!["scripts/sync_status.py"];
            if docs {
                sync_args.push("--docs");
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
