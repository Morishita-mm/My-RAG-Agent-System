use clap::{Parser, Subcommand};

#[derive(Parser)]
#[command(name = "ragy")]
#[command(about = "RAG Agent System Management CLI & TUI Dashboard", long_about = None)]
pub struct Cli {
    #[command(subcommand)]
    pub command: Commands,
}

#[derive(Subcommand)]
pub enum Commands {
    /// Start all RAG services (Docker containers)
    Start,
    
    /// Stop all RAG services
    Stop,
    
    /// Show service and document synchronization status
    Status,
    
    /// Trigger manual document synchronization immediately
    Sync,
    
    /// Start the interactive TUI Dashboard
    Tui,
}
