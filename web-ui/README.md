# Claude Events Web UI

A simple web dashboard to visualize and analyze Claude Code events stored in DuckDB.

## Features

- **Summary Statistics**: Total events, unique sessions, and unique agents
- **Subagent Performance**: View invocation counts, average duration, and token usage
- **Recent Sessions**: Track session activity and duration
- **Recent Events**: Live feed of Claude Code events
- **Auto-refresh**: Updates every 30 seconds (toggleable)

## Setup

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Run the Flask server:
```bash
python app.py
```

3. Open your browser to:
```
http://localhost:5000
```

## API Endpoints

- `GET /` - Main dashboard page
- `GET /api/summary` - Summary statistics
- `GET /api/subagents` - Subagent performance metrics
- `GET /api/recent-events` - Recent events (supports pagination with `limit` and `offset`)
- `GET /api/sessions` - Recent session statistics
- `GET /api/timeline` - Timeline data for charts (future feature)

## Requirements

- Python 3.8+
- DuckDB database at `../logs/claude_events.duckdb`
- Flask 3.0.0
- DuckDB Python library

## Development

The web UI is built with:
- **Backend**: Flask (Python web framework)
- **Frontend**: Alpine.js (reactive framework) + Tailwind CSS (styling)
- **Database**: DuckDB (analytics database)

All frontend dependencies are loaded from CDN, so no build process is required.

## Troubleshooting

If you see "No data available" messages:
1. Ensure the DuckDB database exists at `../logs/claude_events.duckdb`
2. Check that Claude Code hooks are configured and generating events
3. Verify the database contains data: `duckdb ../logs/claude_events.duckdb "SELECT COUNT(*) FROM claude_events;"`

## Future Enhancements

- Timeline charts with Chart.js
- Export data to CSV
- Filter by date range
- Search in prompts/responses
- Session replay visualization
- Cost calculator based on token usage