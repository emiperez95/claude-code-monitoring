#!/bin/bash
# Hook script to log Claude Code events (Task tool and other events)
# Receives JSON data via stdin from Claude Code hooks

EVENT_TYPE=$1
DB_FILE="/Users/emilianoperez/Projects/00-Personal/claude-logging/logs/claude_events.duckdb"
LOG_FILE="/Users/emilianoperez/Projects/00-Personal/claude-logging/logs/subagent.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Create logs directory if it doesn't exist
mkdir -p "$(dirname "$DB_FILE")"

# Read JSON from stdin
JSON_DATA=$(cat)

# Escape single quotes in JSON for SQL
JSON_ESCAPED=$(echo "$JSON_DATA" | sed "s/'/''/g")

# Create table if not exists (simple schema for all Claude events)
duckdb "$DB_FILE" <<EOF 2>/dev/null
CREATE TABLE IF NOT EXISTS claude_events (
    id INTEGER PRIMARY KEY DEFAULT nextval('seq_claude_events'),
    timestamp TIMESTAMP,
    event_type VARCHAR,
    data JSON
);

CREATE SEQUENCE IF NOT EXISTS seq_claude_events START 1;
EOF

# Insert into DuckDB
duckdb "$DB_FILE" <<EOF 2>/dev/null
INSERT INTO claude_events (timestamp, event_type, data)
VALUES ('$TIMESTAMP', '$EVENT_TYPE', '$JSON_ESCAPED'::JSON);
EOF

# Log the event with clear separation (keep existing log file behavior)
echo "========================================" >> "$LOG_FILE"
echo "[$TIMESTAMP] Event: $EVENT_TYPE" >> "$LOG_FILE"
echo "----------------------------------------" >> "$LOG_FILE"

# Pretty print JSON if jq is available, otherwise raw output
if command -v jq &> /dev/null; then
    echo "$JSON_DATA" | jq '.' >> "$LOG_FILE" 2>/dev/null || echo "$JSON_DATA" >> "$LOG_FILE"
else
    echo "$JSON_DATA" >> "$LOG_FILE"
fi

echo "" >> "$LOG_FILE"

# Always exit successfully to not block Claude Code
exit 0