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
    """Get session statistics with pagination and filtering"""
    # Get query parameters
    limit = request.args.get('limit', 20, type=int)
    offset = request.args.get('offset', 0, type=int)
    sort_by = request.args.get('sort', 'session_start')
    order = request.args.get('order', 'desc')
    
    conn = duckdb.connect(DB_PATH, read_only=True)
    
    # Map sort parameters to SQL columns
    sort_mapping = {
        'session_start': 'MIN(timestamp)',
        'event_count': 'COUNT(*)',
        'duration': 'MAX(timestamp) - MIN(timestamp)',
        'unique_agents': 'COUNT(DISTINCT json_extract_string(data, \'$.tool_input.subagent_type\'))'
    }
    
    sort_column = sort_mapping.get(sort_by, 'MIN(timestamp)')
    order_clause = 'DESC' if order == 'desc' else 'ASC'
    
    # Get total count for pagination
    total_count = conn.execute("""
        SELECT COUNT(DISTINCT json_extract_string(data, '$.session_id'))
        FROM claude_events 
        WHERE json_extract_string(data, '$.session_id') IS NOT NULL
    """).fetchone()[0]
    
    # Get paginated results
    results = conn.execute(f"""
        SELECT 
            json_extract_string(data, '$.session_id') as session_id,
            COUNT(*) as event_count,
            MIN(timestamp) as session_start,
            MAX(timestamp) as session_end,
            COUNT(DISTINCT json_extract_string(data, '$.tool_input.subagent_type')) as unique_agents,
            SUM(CAST(json_extract(data, '$.tool_response.totalTokens') AS INTEGER)) as total_tokens,
            LIST(DISTINCT json_extract_string(data, '$.tool_input.subagent_type')) as agent_list
        FROM claude_events 
        WHERE json_extract_string(data, '$.session_id') IS NOT NULL
        GROUP BY session_id
        ORDER BY {sort_column} {order_clause}
        LIMIT ? OFFSET ?
    """, [limit, offset]).fetchall()
    
    conn.close()
    
    return jsonify({
        'total': total_count,
        'limit': limit,
        'offset': offset,
        'sessions': [{
            'session_id': row[0],
            'event_count': row[1],
            'session_start': row[2].isoformat() if row[2] else None,
            'session_end': row[3].isoformat() if row[3] else None,
            'duration_seconds': (row[3] - row[2]).total_seconds() if row[2] and row[3] else 0,
            'unique_agents': row[4],
            'total_tokens': row[5] or 0,
            'agent_list': row[6] if row[6] else []
        } for row in results]
    })

@app.route('/session/<session_id>')
def session_detail(session_id):
    """Display detailed view of a specific session"""
    return render_template('session_detail.html', session_id=session_id)

@app.route('/subagents')
def subagents_page():
    """Display subagents overview page"""
    return render_template('subagents.html')

@app.route('/sessions')
def sessions_page():
    """Display all sessions page"""
    return render_template('sessions.html')

@app.route('/api/session/<session_id>')
def get_session_detail(session_id):
    """Get detailed data for a specific session"""
    conn = duckdb.connect(DB_PATH, read_only=True)
    
    # Get session summary
    summary = conn.execute("""
        SELECT 
            json_extract_string(data, '$.session_id') as session_id,
            COUNT(*) as event_count,
            MIN(timestamp) as session_start,
            MAX(timestamp) as session_end,
            COUNT(DISTINCT json_extract_string(data, '$.tool_input.subagent_type')) as unique_agents,
            SUM(CAST(json_extract(data, '$.tool_response.totalTokens') AS INTEGER)) as total_tokens,
            SUM(CAST(json_extract(data, '$.tool_response.totalDurationMs') AS INTEGER)) as total_duration_ms
        FROM claude_events 
        WHERE json_extract_string(data, '$.session_id') = ?
        GROUP BY session_id
    """, [session_id]).fetchone()
    
    if not summary:
        conn.close()
        return jsonify({'error': 'Session not found'}), 404
    
    # Get all events for this session
    events = conn.execute("""
        SELECT 
            timestamp,
            event_type,
            json_extract_string(data, '$.tool_name') as tool_name,
            json_extract_string(data, '$.tool_input.subagent_type') as subagent_type,
            json_extract_string(data, '$.tool_input.description') as description,
            json_extract_string(data, '$.tool_input.prompt') as prompt,
            json_extract(data, '$.tool_response.totalDurationMs') as duration_ms,
            json_extract(data, '$.tool_response.totalTokens') as tokens,
            json_extract_string(data, '$.tool_response.result') as result,
            json_extract_string(data, '$.tool_response.content[0].text') as response_text,
            data as full_data
        FROM claude_events 
        WHERE json_extract_string(data, '$.session_id') = ?
        ORDER BY timestamp ASC
    """, [session_id]).fetchall()
    
    # Get subagent breakdown
    subagents = conn.execute("""
        SELECT 
            json_extract_string(data, '$.tool_input.subagent_type') as subagent_type,
            COUNT(*) as invocations,
            AVG(CAST(json_extract(data, '$.tool_response.totalDurationMs') AS INTEGER)) as avg_duration_ms,
            SUM(CAST(json_extract(data, '$.tool_response.totalTokens') AS INTEGER)) as total_tokens
        FROM claude_events 
        WHERE json_extract_string(data, '$.session_id') = ?
            AND event_type = 'post'
        GROUP BY subagent_type
        ORDER BY invocations DESC
    """, [session_id]).fetchall()
    
    conn.close()
    
    return jsonify({
        'summary': {
            'session_id': summary[0],
            'event_count': summary[1],
            'session_start': summary[2].isoformat() if summary[2] else None,
            'session_end': summary[3].isoformat() if summary[3] else None,
            'duration_seconds': (summary[3] - summary[2]).total_seconds() if summary[2] and summary[3] else 0,
            'unique_agents': summary[4],
            'total_tokens': summary[5] or 0,
            'total_duration_ms': summary[6] or 0
        },
        'events': [{
            'timestamp': event[0].isoformat() if event[0] else None,
            'event_type': event[1],
            'tool_name': event[2],
            'subagent_type': event[3],
            'description': event[4],
            'prompt': event[5],
            'duration_ms': event[6],
            'tokens': event[7],
            'result': event[8],
            'response_text': event[9],
            'full_data': json.loads(event[10]) if event[10] else None
        } for event in events],
        'subagents': [{
            'subagent_type': agent[0] or 'Unknown',
            'invocations': agent[1],
            'avg_duration_ms': round(agent[2]) if agent[2] else 0,
            'total_tokens': agent[3] or 0
        } for agent in subagents]
    })

@app.route('/api/subagent/<subagent_type>')
def get_subagent_detail(subagent_type):
    """Get detailed data for a specific subagent type"""
    conn = duckdb.connect(DB_PATH, read_only=True)
    
    # Get subagent summary
    summary = conn.execute("""
        SELECT 
            json_extract_string(data, '$.tool_input.subagent_type') as subagent_type,
            COUNT(*) as total_invocations,
            COUNT(DISTINCT json_extract_string(data, '$.session_id')) as unique_sessions,
            AVG(CAST(json_extract(data, '$.tool_response.totalDurationMs') AS INTEGER)) as avg_duration_ms,
            MIN(CAST(json_extract(data, '$.tool_response.totalDurationMs') AS INTEGER)) as min_duration_ms,
            MAX(CAST(json_extract(data, '$.tool_response.totalDurationMs') AS INTEGER)) as max_duration_ms,
            SUM(CAST(json_extract(data, '$.tool_response.totalTokens') AS INTEGER)) as total_tokens,
            AVG(CAST(json_extract(data, '$.tool_response.totalTokens') AS INTEGER)) as avg_tokens
        FROM claude_events 
        WHERE json_extract_string(data, '$.tool_input.subagent_type') = ?
            AND event_type = 'post'
        GROUP BY subagent_type
    """, [subagent_type]).fetchone()
    
    if not summary:
        conn.close()
        return jsonify({'error': 'Subagent not found'}), 404
    
    # Get recent invocations
    invocations = conn.execute("""
        SELECT 
            timestamp,
            json_extract_string(data, '$.session_id') as session_id,
            json_extract_string(data, '$.tool_input.description') as description,
            json_extract(data, '$.tool_response.totalDurationMs') as duration_ms,
            json_extract(data, '$.tool_response.totalTokens') as tokens,
            json_extract_string(data, '$.tool_response.content[0].text') as response_text
        FROM claude_events 
        WHERE json_extract_string(data, '$.tool_input.subagent_type') = ?
            AND event_type = 'post'
        ORDER BY timestamp DESC
        LIMIT 50
    """, [subagent_type]).fetchall()
    
    # Get performance over time (last 24 hours, hourly buckets)
    performance = conn.execute("""
        SELECT 
            DATE_TRUNC('hour', timestamp) as hour,
            COUNT(*) as invocations,
            AVG(CAST(json_extract(data, '$.tool_response.totalDurationMs') AS INTEGER)) as avg_duration_ms
        FROM claude_events 
        WHERE json_extract_string(data, '$.tool_input.subagent_type') = ?
            AND event_type = 'post'
            AND timestamp > NOW() - INTERVAL '24 hours'
        GROUP BY hour
        ORDER BY hour ASC
    """, [subagent_type]).fetchall()
    
    conn.close()
    
    return jsonify({
        'summary': {
            'subagent_type': summary[0],
            'total_invocations': summary[1],
            'unique_sessions': summary[2],
            'avg_duration_ms': round(summary[3]) if summary[3] else 0,
            'min_duration_ms': summary[4] or 0,
            'max_duration_ms': summary[5] or 0,
            'total_tokens': summary[6] or 0,
            'avg_tokens': round(summary[7]) if summary[7] else 0
        },
        'invocations': [{
            'timestamp': inv[0].isoformat() if inv[0] else None,
            'session_id': inv[1],
            'description': inv[2],
            'duration_ms': inv[3],
            'tokens': inv[4],
            'response_preview': inv[5][:200] + '...' if inv[5] and len(inv[5]) > 200 else inv[5]
        } for inv in invocations],
        'performance': [{
            'hour': perf[0].isoformat() if perf[0] else None,
            'invocations': perf[1],
            'avg_duration_ms': round(perf[2]) if perf[2] else 0
        } for perf in performance]
    })

if __name__ == '__main__':
    # Check if database exists
    if not os.path.exists(DB_PATH):
        print(f"Warning: Database not found at {DB_PATH}")
        print("Make sure to run the hooks to generate some data first!")
    
    app.run(debug=True, port=8090, host='0.0.0.0')