mod cli;
mod tui;

use cli::{Cli, Commands};
use clap::Parser;
use std::process::{Command, ExitStatus};
use std::io;

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
        Commands::Status => {
            println!("=== Docker Container Status ===");
            let _ = run_shell_command("docker", &["compose", "ps"]);
            println!("\n=== Document Synchronization Status ===");
            let _ = run_shell_command("python3", &["scripts/sync_status.py"]);
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
