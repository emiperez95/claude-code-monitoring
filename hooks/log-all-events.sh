#!/bin/bash

# Log ALL Claude Code events to DuckDB for exploration
# Usage: log-all-events.sh <event_type> [tool_name] [matcher]

EVENT_TYPE="${1:-unknown}"
TOOL_NAME="${2:-}"
MATCHER="${3:-}"

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB_FILE="$SCRIPT_DIR/../logs/claude_events.duckdb"
LOG_FILE="$SCRIPT_DIR/../logs/all_events.log"

# Read JSON from stdin
JSON_INPUT=$(cat)

# Get tmux session name if in tmux
TMUX_SESSION=""
if [ -n "$TMUX" ]; then
    TMUX_SESSION=$(tmux display-message -p '#S' 2>/dev/null || echo "")
fi

# Add tmux session to JSON if we have it
if [ -n "$TMUX_SESSION" ]; then
    JSON_INPUT=$(echo "$JSON_INPUT" | jq --arg tmux "$TMUX_SESSION" '. + {tmux_session: $tmux}')
fi

# Create timestamp
TIMESTAMP=$(date -u +"%Y-%m-%d %H:%M:%S")

# Log to text file for debugging
echo "====================================" >> "$LOG_FILE"
echo "[$TIMESTAMP] Event: $EVENT_TYPE | Tool: $TOOL_NAME | Matcher: $MATCHER" >> "$LOG_FILE"
echo "$JSON_INPUT" | jq '.' >> "$LOG_FILE" 2>/dev/null || echo "$JSON_INPUT" >> "$LOG_FILE"

# Ensure database and table exist
duckdb "$DB_FILE" <<EOF 2>/dev/null
CREATE TABLE IF NOT EXISTS all_events (
    timestamp TIMESTAMP,
    event_type VARCHAR,
    tool_name VARCHAR,
    matcher VARCHAR,
    data JSON
);
EOF

# Escape JSON for SQL insertion
JSON_ESCAPED=$(echo "$JSON_INPUT" | sed "s/'/''/g")

# Insert into DuckDB
duckdb "$DB_FILE" <<EOF 2>/dev/null
INSERT INTO all_events (timestamp, event_type, tool_name, matcher, data)
VALUES ('$TIMESTAMP', '$EVENT_TYPE', '$TOOL_NAME', '$MATCHER', '$JSON_ESCAPED'::JSON);
EOF

# Return success
exit 0