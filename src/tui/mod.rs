pub mod app;
pub mod ui;

use app::App;
use crossterm::{
    event::{self, DisableMouseCapture, EnableMouseCapture, Event, KeyCode},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::{backend::CrosstermBackend, Terminal};
use std::{error::Error, io, time::Duration};
use std::process::Command;
use tokio::sync::mpsc;

pub async fn run_tui() -> Result<(), Box<dyn Error>> {
    // ターミナル初期化
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen, EnableMouseCapture)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    // アプリ状態
    let mut app = App::new();
    app.load_project_metadata();
    app.fetch_redis_stats().await;

    // 非同期イベントチャネル (Python 同期処理のログ受け渡し用)
    let (tx, mut rx) = mpsc::channel::<String>(100);

    let mut last_redis_tick = std::time::Instant::now();

    loop {
        // 非同期ログの受信
        while let Ok(msg) = rx.try_recv() {
            app.add_log(msg);
        }

        // 定期的に Redis 状態を更新 (5秒おき)
        if last_redis_tick.elapsed() >= Duration::from_secs(5) {
            app.fetch_redis_stats().await;
            app.load_project_metadata();
            last_redis_tick = std::time::Instant::now();
        }

        terminal.draw(|f| ui::draw(f, &mut app))?;

        // イベントポーリング
        if event::poll(Duration::from_millis(100))? {
            if let Event::Key(key) = event::read()? {
                match key.code {
                    KeyCode::Char('q') | KeyCode::Char('Q') => {
                        break;
                    }
                    KeyCode::Tab => {
                        app.active_tab = (app.active_tab + 1) % 2;
                        app.status_message = format!("Switched view to tab {}.", app.active_tab + 1);
                    }
                    KeyCode::Char('c') | KeyCode::Char('C') => {
                        app.add_log("Triggering cache clear...".to_string());
                        app.clear_project_cache().await;
                    }
                    KeyCode::Char('s') | KeyCode::Char('S') => {
                        app.add_log("Initiating document sync in background...".to_string());
                        let tx_clone = tx.clone();
                        // バックグラウンドで Python 同期スクリプトを実行し、出力を非同期チャネル経由でTUIに反映
                        tokio::spawn(async move {
                            let output = Command::new("python3")
                                .arg("scripts/sync_docs.py")
                                .output();
                            match output {
                                Ok(out) => {
                                    let stdout_str = String::from_utf8_lossy(&out.stdout).to_string();
                                    for line in stdout_str.lines() {
                                        if !line.trim().is_empty() {
                                            let _ = tx_clone.send(line.to_string()).await;
                                        }
                                    }
                                    let _ = tx_clone.send("=== Sync finished successfully ===".to_string()).await;
                                }
                                Err(e) => {
                                    let _ = tx_clone.send(format!("Sync launch failed: {}", e)).await;
                                }
                            }
                        });
                    }
                    _ => {}
                }
            }
        }
    }

    // ターミナル復元
    disable_raw_mode()?;
    execute!(
        terminal.backend_mut(),
        LeaveAlternateScreen,
        DisableMouseCapture
    )?;
    terminal.show_cursor()?;

    Ok(())
}
