pub mod app;
pub mod ui;
pub mod api;

use app::{App, TuiMode, ChatMessage};
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

    // 非同期イベントチャネル (Python 同期処理のログ用)
    let (tx, mut rx) = mpsc::channel::<String>(100);

    // 非同期チャット回答チャネル
    let (chat_tx, mut chat_rx) = mpsc::channel::<String>(100);

    let mut last_redis_tick = std::time::Instant::now();

    loop {
        // 非同期ログの受信
        while let Ok(msg) = rx.try_recv() {
            app.add_log(msg);
        }

        // 非同期チャット回答の受信
        while let Ok(reply) = chat_rx.try_recv() {
            if reply.starts_with("[STATUS]") {
                app.chat_status = reply.trim_start_matches("[STATUS]").to_string();
            } else {
                app.chat_history.push(ChatMessage {
                    is_user: false,
                    content: reply,
                });
                app.is_loading_chat = false;
                app.chat_status.clear();
                app.status_message = "RAG reply received.".to_string();
            }
        }

        // 定期的に Redis 状態を更新 (5秒おき)
        if last_redis_tick.elapsed() >= Duration::from_secs(5) {
            app.fetch_redis_stats().await;
            app.load_project_metadata();
            last_redis_tick = std::time::Instant::now();
        }

        terminal.draw(|f| ui::draw(f, &mut app))?;

        // イベントポーリング
        if event::poll(Duration::from_millis(50))? {
            if let Event::Key(key) = event::read()? {
                match app.mode {
                    TuiMode::ProjectList => {
                        match key.code {
                            KeyCode::Char('q') | KeyCode::Char('Q') => {
                                break;
                            }
                            KeyCode::Tab => {
                                app.active_tab = (app.active_tab + 1) % 2;
                                app.status_message = format!("Switched view to tab {}.", app.active_tab + 1);
                            }
                            KeyCode::Char('j') | KeyCode::Down => {
                                if !app.projects.is_empty() {
                                    app.selected_project_index = (app.selected_project_index + 1) % app.projects.len();
                                }
                            }
                            KeyCode::Char('k') | KeyCode::Up => {
                                if !app.projects.is_empty() {
                                    app.selected_project_index = (app.selected_project_index + app.projects.len() - 1) % app.projects.len();
                                }
                            }
                            KeyCode::Char('d') => {
                                if !app.projects.is_empty() {
                                    app.mode = TuiMode::ConfirmDelete;
                                    app.status_message = "Confirm delete? Press 'y' to delete, 'n' to cancel.".to_string();
                                }
                            }
                            KeyCode::Enter => {
                                if !app.projects.is_empty() {
                                    app.mode = TuiMode::Chat;
                                    app.chat_history.clear();
                                    app.input_buffer.clear();
                                    app.status_message = "Entered NotebookLM Chat Mode. Type prompt and press Enter.".to_string();
                                }
                            }
                            KeyCode::Char('c') | KeyCode::Char('C') => {
                                app.add_log("Triggering cache clear...".to_string());
                                app.clear_project_cache().await;
                            }
                            KeyCode::Char('s') | KeyCode::Char('S') => {
                                app.add_log("Initiating document sync in background...".to_string());
                                let tx_clone = tx.clone();
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
                    TuiMode::ConfirmDelete => {
                        match key.code {
                            KeyCode::Char('y') | KeyCode::Char('Y') => {
                                app.status_message = "Deleting project dataset...".to_string();
                                let _ = app.delete_selected_project().await;
                                app.mode = TuiMode::ProjectList;
                            }
                            KeyCode::Char('n') | KeyCode::Char('N') | KeyCode::Esc => {
                                app.mode = TuiMode::ProjectList;
                                app.status_message = "Deletion cancelled.".to_string();
                            }
                            _ => {}
                        }
                    }
                    TuiMode::Chat => {
                        match key.code {
                            KeyCode::Esc => {
                                app.mode = TuiMode::ProjectList;
                                app.status_message = "Exited Chat Mode.".to_string();
                            }
                            KeyCode::Tab => {
                                app.chat_focus = match app.chat_focus {
                                    app::ChatFocus::Input => app::ChatFocus::History,
                                    app::ChatFocus::History => app::ChatFocus::Input,
                                };
                                app.status_message = format!("Switched focus to {:?}", app.chat_focus);
                            }
                            _ => {
                                match app.chat_focus {
                                    app::ChatFocus::Input => {
                                        match key.code {
                                            KeyCode::Enter => {
                                                let query = app.input_buffer.trim().to_string();
                                                if !query.is_empty() && !app.is_loading_chat {
                                                    app.input_buffer.clear();
                                                    app.status_message = "Retrieving context & generating answer...".to_string();
                                                    app.send_rag_chat(query, chat_tx.clone()).await;
                                                }
                                            }
                                            KeyCode::Backspace => {
                                                app.input_buffer.pop();
                                            }
                                            KeyCode::Char(c) => {
                                                app.input_buffer.push(c);
                                            }
                                            _ => {}
                                        }
                                    }
                                    app::ChatFocus::History => {
                                        match key.code {
                                            KeyCode::Char('j') | KeyCode::Down => {
                                                if app.chat_scroll_offset > 0 {
                                                    app.chat_scroll_offset -= 1;
                                                }
                                            }
                                            KeyCode::Char('k') | KeyCode::Up => {
                                                app.chat_scroll_offset += 1;
                                            }
                                            _ => {}
                                        }
                                    }
                                }
                            }
                        }
                    }
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
