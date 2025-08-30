# Claude Code Project Context

This document provides context for Claude Code when working on this monitoring dashboard project.

## Project Overview

This is a **real-time monitoring and analytics dashboard** for Claude Code subagent invocations. It captures and visualizes all Task tool invocations (subagents) with their inputs, outputs, performance metrics, and token usage.

## Current Setup Status

### ✅ Monitoring Active
- Hooks are configured in `~/.claude/settings.json`
- Events are being logged to:
  - **Database**: `logs/claude_events.duckdb`
  - **Text log**: `logs/subagent.log`
- Capturing: `PreToolUse`, `PostToolUse`, and `SubagentStop` events for Task tool

### 📊 Web Dashboard
- **URL**: http://localhost:8090
- **Start server**: `python web-ui/app.py`
- **Pages**:
  - `/` - Main dashboard with summary stats
  - `/sessions` - All sessions with pagination
  - `/session/<id>` - Detailed session timeline
  - `/subagents` - Subagent performance analytics

## Quick Commands

### View recent events in database:
```bash
duckdb logs/claude_events.duckdb "SELECT * FROM claude_events ORDER BY timestamp DESC LIMIT 10"
```

### Check if hooks are working:
```bash
tail -f logs/subagent.log
```

### Start web UI:
```bash
cd web-ui && python app.py
```

### View session summary:
```bash
duckdb logs/claude_events.duckdb "
SELECT 
    json_extract_string(data, '$.session_id') as session,
    COUNT(*) as events,
    MIN(timestamp) as start,
    MAX(timestamp) as end
FROM claude_events 
GROUP BY session
ORDER BY start DESC
LIMIT 5"
```

## What's Being Captured

Each event includes:
- **Session ID**: Unique identifier for the Claude Code session
- **Subagent Type**: Which specialized agent was invoked
- **Description**: Task description provided
- **Prompt**: Full prompt sent to the subagent
- **Response**: Complete response text from the subagent
- **Performance**: Duration in milliseconds
- **Tokens**: Token usage for the invocation
- **Timestamp**: When the event occurred

## Project Structure

```
claude-logging/
├── hooks/
│   └── log-subagent.sh      # Hook script that captures events
├── logs/
│   ├── claude_events.duckdb # Main database
│   └── subagent.log         # Text backup
├── web-ui/
│   ├── app.py               # Flask backend
│   ├── templates/           # HTML templates
│   └── static/              # JavaScript
└── CLAUDE.md               # This file
```

## Development Notes

### Adding More Hooks
To capture other Claude Code events, update `~/.claude/settings.json`:
- `EditTool` - Track file modifications
- `BashTool` - Monitor command executions
- `ReadTool` - See file access patterns

### Database Schema
Single table `claude_events` with:
- `timestamp` (TIMESTAMP)
- `event_type` (VARCHAR) - 'pre', 'post', or 'stop'
- `data` (JSON) - Full event payload

### API Endpoints
All endpoints return JSON:
- `/api/summary` - Overall statistics
- `/api/sessions` - Paginated session list
- `/api/session/<id>` - Session details
- `/api/subagents` - Subagent metrics
- `/api/subagent/<type>` - Individual subagent stats

## GitHub Repository
https://github.com/emiperez95/claude-code-monitoring

## Troubleshooting

If events aren't being captured:
1. Check hooks are configured: `cat ~/.claude/settings.json | grep -A5 hooks`
2. Restart Claude Code after changing settings
3. Verify hook script is executable: `ls -la hooks/log-subagent.sh`
4. Check for errors in: `tail logs/test-hook.log`

If web UI shows no data:
1. Verify database exists: `ls -la logs/claude_events.duckdb`
2. Check recent events: `tail logs/subagent.log`
3. Ensure Flask is running on port 8090