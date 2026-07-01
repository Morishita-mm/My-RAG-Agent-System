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
    
    /// Restart all RAG services
    Restart,
    
    /// Show service and document synchronization status
    Status {
        /// Show detailed Docker container list
        #[arg(long)]
        detail: bool,

        /// Show full list of synchronized documents and their paths
        #[arg(long)]
        docs: bool,
    },
    
    /// Trigger manual document synchronization immediately
    Sync,
    
    /// Start the interactive TUI Dashboard
    Tui,

    /// Diagnose system environment and dependencies
    Doctor,

    /// Initialize current directory for RAG (Creates dataset & symlink)
    Init {
        /// Optional pre-existing Dify dataset ID. If not provided, a new dataset will be created dynamically via Dify API.
        dataset_id: Option<String>,
    },
}
