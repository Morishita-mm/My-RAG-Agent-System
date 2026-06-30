use crate::tui::app::{App, TuiMode};
use ratatui::{
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph, Row, Table, Tabs, Gauge, Clear},
    Frame,
};

pub fn draw(f: &mut Frame, app: &mut App) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3), // Title
            Constraint::Length(3), // Tabs
            Constraint::Min(10),   // Main Pane (Tables & Logs)
            Constraint::Length(3), // Status Bar
        ])
        .split(f.size());

    // 1. タイトル
    let title_style = Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD);
    let title = Paragraph::new(vec![
        Line::from(vec![
            Span::styled(" 🚀 RAGY MCP CLIENT - TUI NotebookLM PANEL v2.0.0 ", title_style),
        ])
    ])
    .block(Block::default().borders(Borders::ALL).border_style(Style::default().fg(Color::DarkGray)));
    f.render_widget(title, chunks[0]);

    // 2. タブ
    let tab_titles = vec![" [1] Project Dashboard ", " [2] Cache & Performance "];
    let tabs = Tabs::new(tab_titles)
        .select(app.active_tab)
        .block(Block::default().borders(Borders::ALL).border_style(Style::default().fg(Color::DarkGray)))
        .style(Style::default().fg(Color::Gray))
        .highlight_style(Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD));
    f.render_widget(tabs, chunks[1]);

    // 3. メインペイン
    let main_chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage(60), // メインデータ / チャット
            Constraint::Percentage(40), // ログメッセージ
        ])
        .split(chunks[2]);

    match app.active_tab {
        0 => {
            match app.mode {
                TuiMode::ProjectList | TuiMode::ConfirmDelete => {
                    // タブ 0: 同期ステータス (Vim移動でハイライト)
                    let project_rows: Vec<Row> = app
                        .projects
                        .iter()
                        .enumerate()
                        .map(|(i, p)| {
                            let style = if i == app.selected_project_index {
                                Style::default().bg(Color::DarkGray).fg(Color::Cyan).add_modifier(Modifier::BOLD)
                            } else {
                                Style::default()
                            };
                            Row::new(vec![
                                p.name.clone(),
                                p.synced_files.to_string(),
                                if p.pending_files == 0 { "Synced (OK)".to_string() } else { format!("{} Pending", p.pending_files) }
                            ]).style(style)
                        })
                        .collect();

                    let project_table = Table::new(
                        project_rows,
                        [
                            Constraint::Percentage(50),
                            Constraint::Percentage(25),
                            Constraint::Percentage(25),
                        ]
                    )
                    .header(Row::new(vec!["Project Name", "Synced Files", "Sync Status"]).style(Style::default().fg(Color::Yellow).add_modifier(Modifier::BOLD)))
                    .block(Block::default().title(" Project List ").borders(Borders::ALL).border_style(Style::default().fg(Color::Cyan)));
                    
                    f.render_widget(project_table, main_chunks[0]);

                    // 削除確認ダイアログのポップアップ描画
                    if app.mode == TuiMode::ConfirmDelete {
                        if let Some(proj) = app.projects.get(app.selected_project_index) {
                            let area = centered_rect(60, 25, main_chunks[0]);
                            f.render_widget(Clear, area); // 背景クリア
                            
                            let confirm_text = vec![
                                Line::from(""),
                                Line::from(vec![
                                    Span::raw("Are you sure you want to delete "),
                                    Span::styled(format!("'{}'", proj.name), Style::default().fg(Color::Red).add_modifier(Modifier::BOLD)),
                                ]),
                                Line::from("from Dify and local configuration?"),
                                Line::from(""),
                                Line::from(vec![
                                    Span::styled("  [y] Yes, delete   ", Style::default().fg(Color::Red).add_modifier(Modifier::BOLD)),
                                    Span::styled("  [n/Esc] No, cancel", Style::default().fg(Color::Green)),
                                ]),
                            ];
                            
                            let confirm_box = Paragraph::new(confirm_text)
                                .block(Block::default().title(" Confirm Deletion ").borders(Borders::ALL).border_style(Style::default().fg(Color::Red)))
                                .alignment(ratatui::layout::Alignment::Center);
                            f.render_widget(confirm_box, area);
                        }
                    }
                }
                TuiMode::Chat => {
                    // タブ 0: チャット画面 (NotebookLM風)
                    let chat_chunks = Layout::default()
                        .direction(Direction::Vertical)
                        .constraints([
                            Constraint::Min(5),    // チャット履歴
                            Constraint::Length(3), // プロンプト入力欄
                        ])
                        .split(main_chunks[0]);

                    // 履歴の描画 (スクロール対応で直近のチャットを表示)
                    let history_height = chat_chunks[0].height as usize - 2; // ボーダー分引く
                    let mut chat_lines = Vec::new();
                    
                    for msg in &app.chat_history {
                        if msg.is_user {
                            chat_lines.push(Line::from(vec![
                                Span::styled("👤 You: ", Style::default().fg(Color::Green).add_modifier(Modifier::BOLD)),
                                Span::raw(&msg.content),
                            ]));
                        } else {
                            chat_lines.push(Line::from(vec![
                                Span::styled("🤖 AI : ", Style::default().fg(Color::Magenta).add_modifier(Modifier::BOLD)),
                                Span::raw(&msg.content),
                            ]));
                        }
                        chat_lines.push(Line::from("")); // 空行挟む
                    }

                    // 高さ調整
                    let total_lines = chat_lines.len();
                    let start_idx = if total_lines > history_height {
                        total_lines - history_height
                    } else {
                        0
                    };
                    let visible_lines = chat_lines[start_idx..].to_vec();

                    let project_name = app.projects.get(app.selected_project_index).map(|p| p.name.as_str()).unwrap_or("RAG Chat");
                    let history_box = Paragraph::new(visible_lines)
                        .block(Block::default().title(format!(" NotebookLM RAG Chat: {} ", project_name)).borders(Borders::ALL).border_style(Style::default().fg(Color::Green)))
                        .wrap(ratatui::widgets::Wrap { trim: true });
                    f.render_widget(history_box, chat_chunks[0]);

                    // 入力欄の描画
                    let cursor_char = if app.is_loading_chat { "⏳ Loading..." } else { "_" };
                    let input_paragraph = Paragraph::new(format!("> {}{}", app.input_buffer, cursor_char))
                        .block(Block::default().title(" Ask Question (Press Enter to Send, Esc to Exit Chat) ").borders(Borders::ALL).border_style(Style::default().fg(Color::Yellow)));
                    f.render_widget(input_paragraph, chat_chunks[1]);
                }
            }
        }
        _ => {
            // タブ 1: キャッシュ詳細 (従来通り)
            let redis_status = if app.redis_connected {
                Span::styled("CONNECTED", Style::default().fg(Color::Green).add_modifier(Modifier::BOLD))
            } else {
                Span::styled("DISCONNECTED", Style::default().fg(Color::Red).add_modifier(Modifier::BOLD))
            };

            let stats_text = vec![
                Line::from(vec![Span::raw("Redis Status: "), redis_status]),
                Line::from(vec![Span::raw("Exact Cache Count: "), Span::styled(app.exact_cache_count.to_string(), Style::default().fg(Color::Cyan))]),
                Line::from(vec![Span::raw("Semantic Cache Count: "), Span::styled(app.semantic_cache_count.to_string(), Style::default().fg(Color::Cyan))]),
                Line::from(vec![Span::raw("")]),
                Line::from(vec![Span::raw("Cache Performance Hit Rate:")]),
            ];

            let stats_paragraph = Paragraph::new(stats_text)
                .block(Block::default().title(" Cache Stats ").borders(Borders::ALL).border_style(Style::default().fg(Color::Cyan)));
            
            let cache_sub_chunks = Layout::default()
                .direction(Direction::Vertical)
                .constraints([
                    Constraint::Length(8),
                    Constraint::Length(3),
                    Constraint::Min(2),
                ])
                .split(main_chunks[0]);

            f.render_widget(stats_paragraph, cache_sub_chunks[0]);

            let gauge = Gauge::default()
                .block(Block::default().title(" Hit Rate ").borders(Borders::ALL).border_style(Style::default().fg(Color::Cyan)))
                .gauge_style(Style::default().fg(Color::Green).bg(Color::Black).add_modifier(Modifier::BOLD))
                .percent(app.hit_rate as u16);
            f.render_widget(gauge, cache_sub_chunks[1]);
        }
    }

    // ログエリア
    let log_lines: Vec<Line> = app
        .logs
        .iter()
        .map(|log| Line::from(vec![Span::raw(log)]))
        .collect();

    let logs_paragraph = Paragraph::new(log_lines)
        .block(Block::default().title(" System Logs ").borders(Borders::ALL).border_style(Style::default().fg(Color::Magenta)))
        .wrap(ratatui::widgets::Wrap { trim: true });
    
    f.render_widget(logs_paragraph, main_chunks[1]);

    // 4. ステータスバー
    let status_style = Style::default().fg(Color::Gray);
    let status_bar = Paragraph::new(vec![
        Line::from(vec![
            Span::styled(format!(" Status: {}", app.status_message), status_style),
        ])
    ])
    .block(Block::default().borders(Borders::ALL).border_style(Style::default().fg(Color::DarkGray)));
    f.render_widget(status_bar, chunks[3]);
}

fn centered_rect(percent_x: u16, percent_y: u16, r: Rect) -> Rect {
    let popup_layout = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Percentage((100 - percent_y) / 2),
            Constraint::Percentage(percent_y),
            Constraint::Percentage((100 - percent_y) / 2),
        ])
        .split(r);

    Layout::default()
        .direction(Direction::Horizontal)
        .constraints([
            Constraint::Percentage((100 - percent_x) / 2),
            Constraint::Percentage(percent_x),
            Constraint::Percentage((100 - percent_x) / 2),
        ])
        .split(popup_layout[1])[1]
}
