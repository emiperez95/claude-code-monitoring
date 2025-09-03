# Claude Code Monitoring Dashboard

Comprehensive monitoring and analytics dashboard for all Claude Code activities with DuckDB storage and simplified web UI.

## Features

### 📊 Web Dashboard
- **Comprehensive event tracking** for ALL tools and session events
- **Session tracking** with detailed timeline views and context (cwd, tmux)
- **Agent (subagent) performance metrics** with execution time distribution
- **Real-time monitoring** with auto-refresh capabilities
- **Simplified interface** focused on comprehensive tracking

### 🪝 Event Capture
- **Comprehensive tracking** via `all_events` table for ALL tools and events
- Captures `PreToolUse`, `PostToolUse`, `SessionStart`, `SessionEnd`, `SubagentStop` events
- Records full context including prompts, responses, and metadata
- **Session context**: Working directory and tmux session name
- Dual storage: DuckDB for analytics + text logs for redundancy
- Legacy `claude_events` table maintained for backward compatibility

### 📈 Analytics
- Session duration and token usage tracking
- Subagent invocation frequency and performance
- **Tool usage patterns** across all Claude Code tools
- Response time analysis with min/avg/max metrics
- **Session lifecycle tracking** with start/end events
- **File operations monitoring** (Read, Write, Edit)
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

For subagent-only tracking:
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

For comprehensive tracking (ALL tools and events):
```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "bash /path/to/claude-code-monitoring/hooks/log-all-events.sh PreToolUse"
      }]
    }],
    "PostToolUse": [{
      "matcher": "*",
      "hooks": [{
        "type": "command",
        "command": "bash /path/to/claude-code-monitoring/hooks/log-all-events.sh PostToolUse"
      }]
    }],
    "SessionStart": [{
      "hooks": [{
        "type": "command",
        "command": "bash /path/to/claude-code-monitoring/hooks/log-all-events.sh SessionStart"
      }]
    }],
    "SessionEnd": [{
      "hooks": [{
        "type": "command",
        "command": "bash /path/to/claude-code-monitoring/hooks/log-all-events.sh SessionEnd"
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
│   ├── log-subagent.sh      # Subagent-focused tracking
│   └── log-all-events.sh    # Comprehensive event tracking
├── logs/
│   ├── claude_events.duckdb # DuckDB database (both tables)
│   ├── subagent.log         # Subagent text log
│   └── all_events.log       # All events text log
├── web-ui/
│   ├── app.py               # Flask backend
│   ├── requirements.txt     # Python dependencies
│   └── templates/
│       ├── all_tracking.html    # Main dashboard (comprehensive view)
│       ├── session_timeline.html # Detailed session timeline
│       └── agent_detail.html    # Agent performance analytics
├── telemetry.md            # OpenTelemetry setup guide
└── CLAUDE.md               # Project context for Claude Code
```

## Web UI Pages

### Main Dashboard (`/`)
- **Comprehensive session overview** with context (cwd, tmux)
- **Summary statistics** for 7-day and 24-hour periods
- **All sessions list** with status tracking
- **Agent usage patterns** and performance metrics
- **Active sessions monitor** with real-time updates
- Click any session for detailed timeline

### Session Timeline (`/session-timeline/<id>`)
- **Complete event timeline** for any session
- **Tool usage breakdown** with Pre/Post event merging
- **Collapsible details** for edit operations
- **Raw JSON viewer** for deep inspection
- **Session metadata** display

### Agent Detail (`/agent/<type>`)
- **Performance range** (min, median, p95, max)
- **Recent invocations** with descriptions
- **Sessions using this agent**
- **Usage statistics** and trends

## Database Schema

### Subagent Events Table (`claude_events`)
Focused tracking of Task tool (subagent) invocations:

```sql
CREATE TABLE claude_events (
    timestamp TIMESTAMP,
    event_type VARCHAR,      -- 'pre', 'post', or 'stop'
    data JSON                -- Full event payload
);
```

### Comprehensive Events Table (`all_events`)
Tracks ALL Claude Code tool usage and session events:

```sql
CREATE TABLE all_events (
    timestamp TIMESTAMP,
    event_type VARCHAR,      -- 'PreToolUse', 'PostToolUse', 'SessionStart', etc.
    tool_name VARCHAR,       -- Tool that was invoked
    matcher VARCHAR,         -- Hook matcher that triggered
    data JSON                -- Full event payload with session context
);
```

Key JSON fields:
- `session_id` - Unique session identifier
- `cwd` - Working directory where session is running
- `tmux_session` - Tmux session name (if in tmux)
- `tool_name` - Tool being invoked (Bash, Edit, Read, Task, etc.)
- `tool_input.subagent_type` - Type of subagent (for Task tool)
- `tool_input.prompt` - Input prompt
- `tool_response.content[0].text` - Response text
- `tool_response.totalDurationMs` - Execution time
- `tool_response.totalTokens` - Token usage

## Exploring Data

### Using DuckDB CLI
```bash
duckdb logs/claude_events.duckdb

-- Recent subagent events
SELECT * FROM claude_events ORDER BY timestamp DESC LIMIT 10;

-- All tool usage across sessions
SELECT 
    json_extract_string(data, '$.tool_name') as tool,
    COUNT(*) as usage_count
FROM all_events 
WHERE event_type = 'PreToolUse'
GROUP BY tool
ORDER BY usage_count DESC;

-- Sessions with context
SELECT 
    json_extract_string(data, '$.session_id') as session,
    MAX(json_extract_string(data, '$.cwd')) as working_dir,
    MAX(json_extract_string(data, '$.tmux_session')) as tmux,
    COUNT(*) as events
FROM all_events 
GROUP BY session
ORDER BY MAX(timestamp) DESC;
```

### API Endpoints

All endpoints use the comprehensive `all_events` table:

- `GET /api/tracking/all-sessions` - All sessions with context (cwd, tmux)
- `GET /api/tracking/current-session` - Current session comprehensive data
- `GET /api/tracking/session/<id>/timeline` - Full timeline for any session
- `GET /api/tracking/agents` - Agent (subagent) usage statistics
- `GET /api/agent/<agent_type>` - Detailed statistics for a specific agent
- `GET /api/tracking/active-sessions` - Currently active sessions
- `GET /api/tracking/stats/7days` - 7-day and 24-hour statistics
- `GET /api/tracking/file-operations` - File operations from current session

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