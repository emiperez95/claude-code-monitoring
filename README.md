# Claude Code Monitoring Dashboard

Real-time monitoring and analytics dashboard for Claude Code subagent invocations with DuckDB storage and web UI.

## Features

### 📊 Web Dashboard
- **Real-time monitoring** of Claude Code events
- **Session tracking** with detailed timeline views
- **Subagent performance metrics** and analytics
- **Searchable and sortable** session history
- **Auto-refresh** capabilities

### 🪝 Event Capture
- Captures `PreToolUse`, `PostToolUse`, and `SubagentStop` events
- Records full context including prompts, responses, and metadata
- Dual storage: DuckDB for analytics + text logs for redundancy

### 📈 Analytics
- Session duration and token usage tracking
- Subagent invocation frequency and performance
- Response time analysis with min/avg/max metrics
- Agent usage patterns across sessions

## Quick Start

### Prerequisites
- Python 3.8+
- Claude Code with hooks support
- DuckDB (installed automatically via pip)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/emiperez95/claude-code-monitoring.git
cd claude-code-monitoring
```

2. Install Python dependencies:
```bash
cd web-ui
pip install -r requirements.txt
```

3. Configure Claude Code hooks in `~/.claude/settings.json`:
```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Task",
      "hooks": [{
        "type": "command",
        "command": "bash /path/to/claude-code-monitoring/hooks/log-subagent.sh pre"
      }]
    }],
    "PostToolUse": [{
      "matcher": "Task",
      "hooks": [{
        "type": "command",
        "command": "bash /path/to/claude-code-monitoring/hooks/log-subagent.sh post"
      }]
    }],
    "SubagentStop": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "bash /path/to/claude-code-monitoring/hooks/log-subagent.sh stop"
      }]
    }]
  }
}
```

4. Restart Claude Code for hooks to take effect

5. Start the web dashboard:
```bash
python web-ui/app.py
```

6. Open your browser to: http://localhost:8090

## Project Structure

```
claude-code-monitoring/
├── hooks/
│   └── log-subagent.sh      # Hook script for capturing events
├── logs/
│   ├── claude_events.duckdb # DuckDB database
│   └── subagent.log         # Text log backup
├── web-ui/
│   ├── app.py               # Flask backend
│   ├── requirements.txt     # Python dependencies
│   ├── static/
│   │   └── dashboard.js     # Frontend JavaScript
│   └── templates/
│       ├── index.html       # Main dashboard
│       ├── session_detail.html
│       ├── sessions.html    # All sessions list
│       └── subagents.html   # Subagent analytics
└── telemetry.md            # OpenTelemetry setup guide
```

## Web UI Pages

### Dashboard (`/`)
- Summary statistics cards
- Recent events feed
- Top subagent performance table
- Recent sessions overview

### Sessions (`/sessions`)
- Full session history with pagination
- Sortable by date, duration, events, or agents
- Quick access to session details
- Aggregate statistics

### Session Detail (`/session/<id>`)
- Complete event timeline
- Expandable prompts and responses
- Performance metrics per subagent
- Token usage breakdown

### Subagents (`/subagents`)
- Grid view of all subagents
- Performance statistics
- Recent invocation history
- Min/avg/max response times

## Database Schema

Events are stored in DuckDB with flexible JSON columns:

```sql
CREATE TABLE claude_events (
    timestamp TIMESTAMP,
    event_type VARCHAR,      -- 'pre', 'post', or 'stop'
    data JSON                -- Full event payload
);
```

Key JSON fields:
- `session_id` - Unique session identifier
- `tool_input.subagent_type` - Type of subagent invoked
- `tool_input.prompt` - Input prompt
- `tool_response.content[0].text` - Response text
- `tool_response.totalDurationMs` - Execution time
- `tool_response.totalTokens` - Token usage

## Exploring Data

### Using DuckDB CLI
```bash
duckdb logs/claude_events.duckdb

-- Recent events
SELECT * FROM claude_events ORDER BY timestamp DESC LIMIT 10;

-- Session summary
SELECT 
    json_extract_string(data, '$.session_id') as session,
    COUNT(*) as events,
    MIN(timestamp) as start_time
FROM claude_events 
GROUP BY session
ORDER BY start_time DESC;
```

### API Endpoints

- `GET /api/summary` - Overall statistics
- `GET /api/subagents` - Subagent performance metrics
- `GET /api/sessions` - Session list with pagination
- `GET /api/session/<id>` - Detailed session data
- `GET /api/subagent/<type>` - Individual subagent analytics
- `GET /api/recent-events` - Recent event stream

## OpenTelemetry Integration

For advanced telemetry with Prometheus, Loki, Grafana, and Tempo, see [telemetry.md](telemetry.md).

Recommended stack: [ColeMurray/claude-code-otel](https://github.com/ColeMurray/claude-code-otel)

## Troubleshooting

### Hooks not triggering
1. Ensure Claude Code was restarted after modifying settings.json
2. Check hook paths are absolute, not relative
3. Verify bash is available in your PATH

### No data in dashboard
1. Check DuckDB exists: `ls logs/claude_events.duckdb`
2. Verify hooks are writing: `tail -f logs/subagent.log`
3. Trigger a subagent invocation in Claude Code

### Port conflicts
Default port is 8090. To change:
```bash
python web-ui/app.py --port 5000
```

## Contributing

Contributions welcome! Please feel free to submit issues or pull requests.

## License

MIT