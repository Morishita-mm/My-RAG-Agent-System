use crate::tui::app::{App, TuiMode, ChatFocus};
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
                    let history_width = (chat_chunks[0].width as usize).saturating_sub(2);
                    let mut chat_lines = Vec::new();
                    
                    for msg in &app.chat_history {
                        let prefix = if msg.is_user { "👤 You: " } else { "🤖 AI : " };
                        let prefix_len = prefix.chars().count();
                        let prefix_color = if msg.is_user { Color::Green } else { Color::Magenta };
                        
                        let raw_lines: Vec<&str> = msg.content.lines().collect();
                        let mut is_first_line = true;
                        
                        for raw_line in raw_lines {
                            let current_width = if is_first_line {
                                history_width.saturating_sub(prefix_len)
                            } else {
                                history_width
                            };
                            
                            let wrapped = wrap_text(raw_line, current_width);
                            
                            for (i, w_line) in wrapped.into_iter().enumerate() {
                                if is_first_line && i == 0 {
                                    chat_lines.push(Line::from(vec![
                                        Span::styled(prefix, Style::default().fg(prefix_color).add_modifier(Modifier::BOLD)),
                                        Span::raw(w_line),
                                    ]));
                                } else {
                                    let indent = if is_first_line {
                                        " ".repeat(prefix_len)
                                    } else {
                                        String::new()
                                    };
                                    chat_lines.push(Line::from(vec![
                                        Span::raw(format!("{}{}", indent, w_line)),
                                    ]));
                                }
                            }
                            is_first_line = false;
                        }
                        chat_lines.push(Line::from("")); // 空行挟む
                    }

                    // スクロールオフセットを考慮した切り出し
                    let total_lines = chat_lines.len();
                    let max_offset = if total_lines > history_height {
                        total_lines - history_height
                    } else {
                        0
                    };
                    let current_offset = app.chat_scroll_offset.min(max_offset);

                    let start_idx = if total_lines > history_height {
                        total_lines - history_height - current_offset
                    } else {
                        0
                    };
                    let end_idx = if total_lines > history_height {
                        total_lines - current_offset
                    } else {
                        total_lines
                    };
                    let visible_lines = chat_lines[start_idx..end_idx].to_vec();

                    let project_name = app.projects.get(app.selected_project_index).map(|p| p.name.as_str()).unwrap_or("RAG Chat");
                    
                    // フォーカスに応じた枠線色とタイトルの切り替え
                    let (history_border_color, history_title, input_border_color, input_title) = match app.chat_focus {
                        ChatFocus::History => (
                            Color::Cyan,
                            format!(" 📖 NotebookLM RAG Chat: {} [SCROLL MODE - j/k to scroll, Tab to edit] ", project_name),
                            Color::DarkGray,
                            " Ask Question (Press Tab to Edit Prompt) ".to_string(),
                        ),
                        ChatFocus::Input => (
                            Color::DarkGray,
                            format!(" 📖 NotebookLM RAG Chat: {} [Press Tab to scroll history] ", project_name),
                            Color::Yellow,
                            " Ask Question (Type and Press Enter to Send, Tab to Scroll History) ".to_string(),
                        ),
                    };

                    let history_box = Paragraph::new(visible_lines)
                        .block(Block::default()
                            .title(history_title)
                            .borders(Borders::ALL)
                            .border_style(Style::default().fg(history_border_color).add_modifier(if app.chat_focus == ChatFocus::History { Modifier::BOLD } else { Modifier::empty() })));
                    f.render_widget(history_box, chat_chunks[0]);

                    // 入力欄の描画
                    let input_text = if app.is_loading_chat {
                        let ms = std::time::SystemTime::now()
                            .duration_since(std::time::SystemTime::UNIX_EPOCH)
                            .unwrap_or_default()
                            .as_millis();
                        let spinner_idx = (ms / 150) % 4;
                        let spinner = match spinner_idx {
                            0 => "⠋",
                            1 => "⠙",
                            2 => "⠹",
                            _ => "⠸",
                        };
                        let status = if app.chat_status.is_empty() {
                            "Processing..."
                        } else {
                            &app.chat_status
                        };
                        format!(" {} {} ", spinner, status)
                    } else {
                        format!("> {}{}", app.input_buffer, "_")
                    };

                    let input_paragraph = Paragraph::new(input_text)
                        .block(Block::default()
                            .title(input_title)
                            .borders(Borders::ALL)
                            .border_style(Style::default().fg(input_border_color).add_modifier(if app.chat_focus == ChatFocus::Input { Modifier::BOLD } else { Modifier::empty() })));
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

fn wrap_text(text: &str, width: usize) -> Vec<String> {
    if width == 0 {
        return vec![text.to_string()];
    }
    let mut lines = Vec::new();
    let mut current_line = String::new();
    let mut current_width = 0;

    for c in text.chars() {
        let char_width = if c as u32 > 0x7F { 2 } else { 1 };
        
        if current_width + char_width > width {
            if !current_line.is_empty() {
                lines.push(current_line.clone());
                current_line.clear();
                current_width = 0;
            }
        }
        current_line.push(c);
        current_width += char_width;
    }
    
    if !current_line.is_empty() {
        lines.push(current_line);
    }
    
    if lines.is_empty() {
        lines.push(String::new());
    }
    
    lines
}
