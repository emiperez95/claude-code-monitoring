from flask import Flask, render_template, jsonify, request
import duckdb
from datetime import datetime
import json
import os

app = Flask(__name__)

# Path to DuckDB file (relative to web-ui folder)
DB_PATH = os.path.join(os.path.dirname(__file__), '../logs/claude_events.duckdb')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/summary')
def get_summary():
    """Get summary statistics"""
    conn = duckdb.connect(DB_PATH, read_only=True)
    
    summary = conn.execute("""
        SELECT 
            COUNT(*) as total_events,
            COUNT(DISTINCT json_extract_string(data, '$.session_id')) as unique_sessions,
            COUNT(DISTINCT json_extract_string(data, '$.tool_input.subagent_type')) as unique_agents
        FROM claude_events
    """).fetchone()
    
    conn.close()
    
    return jsonify({
        'total_events': summary[0],
        'unique_sessions': summary[1],
        'unique_agents': summary[2]
    })

@app.route('/api/subagents')
def get_subagent_stats():
    """Get subagent performance statistics"""
    conn = duckdb.connect(DB_PATH, read_only=True)
    
    results = conn.execute("""
        SELECT 
            json_extract_string(data, '$.tool_input.subagent_type') as subagent_type,
            COUNT(*) as invocations,
            AVG(CAST(json_extract(data, '$.tool_response.totalDurationMs') AS INTEGER)) as avg_duration_ms,
            SUM(CAST(json_extract(data, '$.tool_response.totalTokens') AS INTEGER)) as total_tokens
        FROM claude_events 
        WHERE event_type = 'post' 
            AND json_extract(data, '$.tool_response.totalDurationMs') IS NOT NULL
        GROUP BY subagent_type
        ORDER BY invocations DESC
    """).fetchall()
    
    conn.close()
    
    return jsonify([{
        'subagent_type': row[0] or 'Unknown',
        'invocations': row[1],
        'avg_duration_ms': round(row[2]) if row[2] else 0,
        'total_tokens': row[3] or 0
    } for row in results])

@app.route('/api/recent-events')
def get_recent_events():
    """Get recent events with pagination"""
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    
    conn = duckdb.connect(DB_PATH, read_only=True)
    
    results = conn.execute("""
        SELECT 
            timestamp,
            event_type,
            json_extract_string(data, '$.tool_name') as tool_name,
            json_extract_string(data, '$.tool_input.subagent_type') as subagent_type,
            json_extract_string(data, '$.tool_input.description') as description,
            json_extract(data, '$.tool_response.totalDurationMs') as duration_ms,
            json_extract_string(data, '$.session_id') as session_id
        FROM claude_events 
        ORDER BY timestamp DESC
        LIMIT ? OFFSET ?
    """, [limit, offset]).fetchall()
    
    conn.close()
    
    return jsonify([{
        'timestamp': row[0].isoformat() if row[0] else None,
        'event_type': row[1],
        'tool_name': row[2],
        'subagent_type': row[3],
        'description': row[4],
        'duration_ms': row[5],
        'session_id': row[6]
    } for row in results])

@app.route('/api/timeline')
def get_timeline():
    """Get timeline data for chart"""
    conn = duckdb.connect(DB_PATH, read_only=True)
    
    results = conn.execute("""
        SELECT 
            DATE_TRUNC('hour', timestamp) as hour,
            event_type,
            COUNT(*) as count
        FROM claude_events
        GROUP BY hour, event_type
        ORDER BY hour DESC
        LIMIT 168  -- Last 7 days worth of hours
    """).fetchall()
    
    conn.close()
    
    return jsonify([{
        'hour': row[0].isoformat() if row[0] else None,
        'event_type': row[1],
        'count': row[2]
    } for row in results])

@app.route('/api/sessions')
def get_sessions():
    """Get session statistics"""
    conn = duckdb.connect(DB_PATH, read_only=True)
    
    results = conn.execute("""
        SELECT 
            json_extract_string(data, '$.session_id') as session_id,
            COUNT(*) as event_count,
            MIN(timestamp) as session_start,
            MAX(timestamp) as session_end,
            COUNT(DISTINCT json_extract_string(data, '$.tool_input.subagent_type')) as unique_agents
        FROM claude_events 
        WHERE json_extract_string(data, '$.session_id') IS NOT NULL
        GROUP BY session_id
        ORDER BY session_start DESC
        LIMIT 20
    """).fetchall()
    
    conn.close()
    
    return jsonify([{
        'session_id': row[0],
        'event_count': row[1],
        'session_start': row[2].isoformat() if row[2] else None,
        'session_end': row[3].isoformat() if row[3] else None,
        'duration_seconds': (row[3] - row[2]).total_seconds() if row[2] and row[3] else 0,
        'unique_agents': row[4]
    } for row in results])

if __name__ == '__main__':
    # Check if database exists
    if not os.path.exists(DB_PATH):
        print(f"Warning: Database not found at {DB_PATH}")
        print("Make sure to run the hooks to generate some data first!")
    
    app.run(debug=True, port=8090, host='0.0.0.0')