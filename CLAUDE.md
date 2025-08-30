# Claude Code Project Context

This document provides context for Claude Code when working on this monitoring dashboard project.

## Project Overview

This is a **comprehensive monitoring and analytics dashboard** for Claude Code activities. It features:
- **Subagent tracking**: Detailed monitoring of Task tool (subagent) invocations
- **Complete event tracking**: ALL tools and session events via `all_events` table
- **Session context**: Working directory and tmux session tracking
- **Real-time visualization**: Multiple web UI pages for different views

## Current Setup Status

### ✅ Monitoring Active
- Hooks are configured in `~/.claude/settings.json`
- **Two tracking systems**:
  - **Subagent-focused**: `claude_events` table + `logs/subagent.log`
  - **Comprehensive**: `all_events` table + `logs/all_events.log`
- Capturing: `PreToolUse`, `PostToolUse`, `SessionStart`, `SessionEnd`, `SubagentStop` events
- **Session context captured**: Working directory (`cwd`) and tmux session name

### 📊 Web Dashboard
- **URL**: http://localhost:8090
- **Start server**: `python web-ui/app.py`
- **Pages**:
  - `/` - Main dashboard with summary stats
  - `/sessions` - All sessions with pagination (subagent-focused)
  - `/session/<id>` - Detailed session timeline (subagent-focused)
  - `/subagents` - Subagent performance analytics
  - `/tracking` - Current session comprehensive tracking
  - `/all-tracking` - ALL sessions with full context and timeline

## Quick Commands

### View recent events in database:
```bash
# Subagent events
duckdb logs/claude_events.duckdb "SELECT * FROM claude_events ORDER BY timestamp DESC LIMIT 10"

# All events with context
duckdb logs/claude_events.duckdb "SELECT * FROM all_events ORDER BY timestamp DESC LIMIT 10"
```

### Check if hooks are working:
```bash
# Subagent events
tail -f logs/subagent.log

# All events
tail -f logs/all_events.log
```

### Start web UI:
```bash
cd web-ui && python app.py
```

### View sessions with context:
```bash
duckdb logs/claude_events.duckdb "
SELECT 
    json_extract_string(data, '$.session_id') as session,
    MAX(json_extract_string(data, '$.cwd')) as working_dir,
    MAX(json_extract_string(data, '$.tmux_session')) as tmux,
    COUNT(*) as events
FROM all_events 
GROUP BY session
ORDER BY MAX(timestamp) DESC
LIMIT 5"
```

## What's Being Captured

### Subagent Events (`claude_events` table):
- **Session ID**: Unique identifier for the Claude Code session
- **Subagent Type**: Which specialized agent was invoked
- **Description**: Task description provided
- **Prompt**: Full prompt sent to the subagent
- **Response**: Complete response text from the subagent
- **Performance**: Duration in milliseconds
- **Tokens**: Token usage for the invocation

### All Events (`all_events` table):
- **Session context**: Working directory and tmux session name
- **Tool usage**: ALL tools (Bash, Edit, Read, Write, Grep, etc.)
- **Session lifecycle**: SessionStart, SessionEnd events
- **Edit operations**: Old and new strings for file modifications
- **Command executions**: Full bash commands and their context
- **File operations**: Paths and patterns for file access

## Project Structure

```
claude-logging/
├── hooks/
│   ├── log-subagent.sh      # Subagent-focused tracking
│   └── log-all-events.sh    # Comprehensive event tracking
├── logs/
│   ├── claude_events.duckdb # Database with both tables
│   ├── subagent.log         # Subagent text log
│   └── all_events.log       # All events text log
├── web-ui/
│   ├── app.py               # Flask backend
│   ├── templates/           # HTML templates (6 pages)
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
Two tables for different tracking needs:

**`claude_events`** (Subagent-focused):
- `timestamp` (TIMESTAMP)
- `event_type` (VARCHAR) - 'pre', 'post', or 'stop'
- `data` (JSON) - Full event payload

**`all_events`** (Comprehensive):
- `timestamp` (TIMESTAMP)
- `event_type` (VARCHAR) - 'PreToolUse', 'PostToolUse', 'SessionStart', etc.
- `tool_name` (VARCHAR) - Tool that was invoked
- `matcher` (VARCHAR) - Hook matcher that triggered
- `data` (JSON) - Full event payload with session context

### API Endpoints
All endpoints return JSON:
- `/api/summary` - Overall statistics
- `/api/sessions` - Paginated session list
- `/api/session/<id>` - Session details
- `/api/subagents` - Subagent metrics
- `/api/subagent/<type>` - Individual subagent stats
- `/api/tracking/current-session` - Current session comprehensive data
- `/api/tracking/all-sessions` - All sessions with context
- `/api/tracking/session/<id>/timeline` - Full timeline for any session

## GitHub Repository
https://github.com/emiperez95/claude-code-monitoring

## Known Limitations

- **Cannot distinguish subagent tool calls**: When a subagent uses tools (Bash, Edit, etc.), they appear with the same session_id as the parent Claude session
- **Tmux session tracking requires tmux**: Sessions outside tmux won't have tmux_session data
- **Session context is best-effort**: Working directory and tmux info are captured at event time

## Troubleshooting

If events aren't being captured:
1. Check hooks are configured: `cat ~/.claude/settings.json | grep -A5 hooks`
2. Restart Claude Code after changing settings
3. Verify hook scripts are executable: `ls -la hooks/*.sh`
4. Check for errors in: `tail logs/all_events.log`

If web UI shows no data:
1. Verify database exists: `ls -la logs/claude_events.duckdb`
2. Check recent events: `tail logs/subagent.log` or `tail logs/all_events.log`
3. Ensure Flask is running on port 8090
4. For new sessions, check tmux detection: `echo $TMUX`