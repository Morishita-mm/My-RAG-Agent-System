use crate::tui::app::App;
use ratatui::{
    layout::{Constraint, Direction, Layout},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Paragraph, Row, Table, Tabs, Gauge},
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
            Span::styled(" 🚀 RAGY MCP CLIENT - TUI CONTROL PANEL v1.7.0 ", title_style),
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
            Constraint::Percentage(60), // メインデータ
            Constraint::Percentage(40), // ログメッセージ
        ])
        .split(chunks[2]);

    match app.active_tab {
        0 => {
            // タブ 0: 同期ステータス
            let project_rows: Vec<Row> = app
                .projects
                .iter()
                .map(|p| {
                    Row::new(vec![
                        p.name.clone(),
                        p.synced_files.to_string(),
                        if p.pending_files == 0 { "Synced (OK)".to_string() } else { format!("{} Pending", p.pending_files) }
                    ])
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
        }
        _ => {
            // タブ 1: キャッシュ詳細
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
            
            // Hit Rate ゲージ
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
