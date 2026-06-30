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


fn run_shell_command(cmd: &str, args: &[&str]) -> io::Result<ExitStatus> {
    Command::new(cmd)
        .args(args)
        .status()
}

#[tokio::main]
async fn main() -> io::Result<()> {
    let args = Cli::parse();

    match args.command {
        Commands::Start => {
            println!("Starting RAG Services via Docker Compose...");
            match run_shell_command("docker", &["compose", "up", "-d"]) {
                Ok(status) if status.success() => {
                    println!("Services started successfully.");
                }
                _ => eprintln!("Failed to start services via Docker Compose."),
            }
        }
        Commands::Stop => {
            println!("Stopping RAG Services...");
            match run_shell_command("docker", &["compose", "down"]) {
                Ok(status) if status.success() => {
                    println!("Services stopped successfully.");
                }
                _ => eprintln!("Failed to stop services."),
            }
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

            if detail {
                println!("\n=== Detailed Docker Containers ===");
                let _ = run_shell_command("docker", &["compose", "ps"]);
            }

            let mut sync_args = vec!["scripts/sync_status.py"];
            if docs {
                sync_args.push("--docs");
            }
            let _ = run_shell_command("python3", &sync_args);
        }
        Commands::Sync => {
            println!("Triggering document synchronization...");
            match run_shell_command("python3", &["scripts/sync_docs.py"]) {
                Ok(status) if status.success() => {
                    println!("Synchronization complete.");
                }
                _ => eprintln!("Synchronization failed."),
            }
        }
        Commands::Tui => {
            if let Err(e) = tui::run_tui().await {
                eprintln!("TUI Error: {}", e);
            }
        }
    }

    Ok(())
}
