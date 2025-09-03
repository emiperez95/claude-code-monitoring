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
    """Display comprehensive session tracking from all_events"""
    return render_template('all_tracking.html')

# API endpoints now exclusively use the all_events table for comprehensive tracking

@app.route('/session-timeline/<session_id>')
def session_timeline_page(session_id):
    """Display detailed timeline for a specific session"""
    return render_template('session_timeline.html', session_id=session_id)

@app.route('/agent/<agent_type>')
def agent_detail_page(agent_type):
    """Display detailed information for a specific agent"""
    return render_template('agent_detail.html', agent_type=agent_type)

@app.route('/api/tracking/current-session')
def get_current_session_tracking():
    """Get comprehensive tracking data for the current session"""
    conn = duckdb.connect(DB_PATH, read_only=True)
    
    # Get the most recent session
    current_session = conn.execute("""
        SELECT json_extract_string(data, '$.session_id') as session_id
        FROM all_events
        WHERE json_extract_string(data, '$.session_id') IS NOT NULL
        ORDER BY timestamp DESC
        LIMIT 1
    """).fetchone()
    
    if not current_session:
        conn.close()
        return jsonify({'error': 'No active session found'}), 404
    
    session_id = current_session[0]
    
    # Get session lifecycle
    lifecycle = conn.execute("""
        SELECT 
            timestamp,
            event_type,
            json_extract_string(data, '$.source') as source
        FROM all_events
        WHERE event_type IN ('SessionStart', 'SessionEnd', 'PreCompact')
            AND json_extract_string(data, '$.session_id') = ?
        ORDER BY timestamp ASC
    """, [session_id]).fetchall()
    
    # Get tool usage statistics
    tool_stats = conn.execute("""
        SELECT 
            json_extract_string(data, '$.tool_name') as tool_name,
            COUNT(*) FILTER (WHERE event_type = 'PreToolUse') as pre_count,
            COUNT(*) FILTER (WHERE event_type = 'PostToolUse') as post_count,
            COUNT(DISTINCT json_extract_string(data, '$.tool_input.command')) as unique_commands,
            COUNT(DISTINCT json_extract_string(data, '$.tool_input.file_path')) as unique_files
        FROM all_events
        WHERE json_extract_string(data, '$.session_id') = ?
            AND event_type IN ('PreToolUse', 'PostToolUse')
        GROUP BY json_extract_string(data, '$.tool_name')
        ORDER BY pre_count DESC
    """, [session_id]).fetchall()
    
    # Get timeline of all events
    timeline = conn.execute("""
        SELECT 
            timestamp,
            event_type,
            json_extract_string(data, '$.tool_name') as tool_name,
            json_extract_string(data, '$.tool_input.command') as command,
            json_extract_string(data, '$.tool_input.file_path') as file_path,
            json_extract_string(data, '$.tool_input.pattern') as pattern,
            json_extract_string(data, '$.tool_input.url') as url,
            json_extract_string(data, '$.tool_input.description') as description
        FROM all_events
        WHERE json_extract_string(data, '$.session_id') = ?
        ORDER BY timestamp DESC
        LIMIT 100
    """, [session_id]).fetchall()
    
    conn.close()
    
    return jsonify({
        'session_id': session_id,
        'lifecycle': [{
            'timestamp': event[0].isoformat() if event[0] else None,
            'event_type': event[1],
            'source': event[2]
        } for event in lifecycle],
        'tool_stats': [{
            'tool_name': stat[0] or 'Unknown',
            'pre_count': stat[1],
            'post_count': stat[2],
            'unique_commands': stat[3],
            'unique_files': stat[4]
        } for stat in tool_stats],
        'timeline': [{
            'timestamp': event[0].isoformat() if event[0] else None,
            'event_type': event[1],
            'tool_name': event[2],
            'command': event[3],
            'file_path': event[4],
            'pattern': event[5],
            'url': event[6],
            'description': event[7]
        } for event in timeline]
    })

@app.route('/api/tracking/file-operations')
def get_file_operations():
    """Get all file operations from current session"""
    conn = duckdb.connect(DB_PATH, read_only=True)
    
    results = conn.execute("""
        SELECT 
            timestamp,
            json_extract_string(data, '$.tool_name') as tool_name,
            json_extract_string(data, '$.tool_input.file_path') as file_path,
            event_type
        FROM all_events
        WHERE json_extract_string(data, '$.tool_name') IN ('Read', 'Write', 'Edit', 'MultiEdit')
            AND json_extract_string(data, '$.tool_input.file_path') IS NOT NULL
        ORDER BY timestamp DESC
        LIMIT 50
    """).fetchall()
    
    conn.close()
    
    return jsonify([{
        'timestamp': row[0].isoformat() if row[0] else None,
        'tool_name': row[1],
        'file_path': row[2],
        'event_type': row[3]
    } for row in results])

@app.route('/api/tracking/all-sessions')
def get_all_sessions_tracking():
    """Get all sessions with their lifecycle and statistics"""
    conn = duckdb.connect(DB_PATH, read_only=True)
    
    # Get all unique sessions with their lifecycle events
    sessions = conn.execute("""
        WITH session_stats AS (
            SELECT 
                json_extract_string(data, '$.session_id') as session_id,
                MIN(timestamp) as session_start,
                MAX(timestamp) as session_end,
                COUNT(*) as total_events,
                COUNT(DISTINCT json_extract_string(data, '$.tool_name')) as unique_tools,
                COUNT(*) FILTER (WHERE event_type = 'SessionStart') as start_events,
                COUNT(*) FILTER (WHERE event_type = 'SessionEnd') as end_events,
                MAX(CASE WHEN event_type = 'SessionStart' 
                    THEN json_extract_string(data, '$.source') END) as start_source,
                MAX(json_extract_string(data, '$.cwd')) as cwd,
                MAX(json_extract_string(data, '$.tmux_session')) as tmux_session,
                STRING_AGG(DISTINCT json_extract_string(data, '$.tool_name'), ', ') as tools_used
            FROM all_events
            WHERE json_extract_string(data, '$.session_id') IS NOT NULL
            GROUP BY session_id
        )
        SELECT 
            session_id,
            session_start,
            session_end,
            total_events,
            unique_tools,
            start_events,
            end_events,
            start_source,
            cwd,
            tmux_session,
            tools_used,
            CASE 
                WHEN end_events > 0 THEN 'completed'
                WHEN session_end > NOW() - INTERVAL '5 minutes' THEN 'active'
                ELSE 'inactive'
            END as status
        FROM session_stats
        ORDER BY session_start DESC
    """).fetchall()
    
    conn.close()
    
    return jsonify([{
        'session_id': row[0],
        'session_start': row[1].isoformat() if row[1] else None,
        'session_end': row[2].isoformat() if row[2] else None,
        'total_events': row[3],
        'unique_tools': row[4],
        'start_events': row[5],
        'end_events': row[6],
        'start_source': row[7],
        'cwd': row[8],
        'tmux_session': row[9],
        'tools_used': row[10],
        'status': row[11],
        'duration_seconds': (row[2] - row[1]).total_seconds() if row[1] and row[2] else None
    } for row in sessions])

@app.route('/api/tracking/stats/7days')
def get_seven_day_stats():
    """Get statistics for the last 7 days and 24 hours"""
    conn = duckdb.connect(DB_PATH, read_only=True)
    
    # Get 7-day stats
    stats_7d = conn.execute("""
        WITH last_7_days AS (
            SELECT *
            FROM all_events
            WHERE timestamp >= CURRENT_TIMESTAMP - INTERVAL '7 days'
        )
        SELECT 
            COUNT(*) as total_events,
            COUNT(DISTINCT json_extract_string(data, '$.tmux_session')) FILTER (
                WHERE json_extract_string(data, '$.tmux_session') IS NOT NULL 
                AND json_extract_string(data, '$.tmux_session') != ''
            ) as unique_tmux_sessions,
            COUNT(DISTINCT json_extract_string(data, '$.tool_input.subagent_type')) FILTER (
                WHERE event_type = 'PreToolUse' 
                AND json_extract_string(data, '$.tool_name') = 'Task'
                AND json_extract_string(data, '$.tool_input.subagent_type') IS NOT NULL
            ) as unique_agents
        FROM last_7_days
    """).fetchone()
    
    # Get 24-hour stats
    stats_24h = conn.execute("""
        WITH last_24_hours AS (
            SELECT *
            FROM all_events
            WHERE timestamp >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
        )
        SELECT 
            COUNT(*) as total_events,
            COUNT(DISTINCT json_extract_string(data, '$.tmux_session')) FILTER (
                WHERE json_extract_string(data, '$.tmux_session') IS NOT NULL 
                AND json_extract_string(data, '$.tmux_session') != ''
            ) as unique_tmux_sessions,
            COUNT(DISTINCT json_extract_string(data, '$.tool_input.subagent_type')) FILTER (
                WHERE event_type = 'PreToolUse' 
                AND json_extract_string(data, '$.tool_name') = 'Task'
                AND json_extract_string(data, '$.tool_input.subagent_type') IS NOT NULL
            ) as unique_agents
        FROM last_24_hours
    """).fetchone()
    
    conn.close()
    
    return jsonify({
        'total_events_7d': stats_7d[0] if stats_7d else 0,
        'unique_tmux_sessions_7d': stats_7d[1] if stats_7d else 0,
        'unique_agents_7d': stats_7d[2] if stats_7d else 0,
        'total_events_24h': stats_24h[0] if stats_24h else 0,
        'unique_tmux_sessions_24h': stats_24h[1] if stats_24h else 0,
        'unique_agents_24h': stats_24h[2] if stats_24h else 0
    })

@app.route('/api/tracking/agents')
def get_agent_statistics():
    """Get statistics about agent (subagent) usage across all sessions"""
    conn = duckdb.connect(DB_PATH, read_only=True)
    
    # Get agent usage statistics
    agents = conn.execute("""
        SELECT 
            json_extract_string(data, '$.tool_input.subagent_type') as agent_type,
            COUNT(*) as usage_count,
            COUNT(DISTINCT json_extract_string(data, '$.session_id')) as sessions_used,
            MIN(timestamp) as first_used,
            MAX(timestamp) as last_used
        FROM all_events 
        WHERE event_type = 'PreToolUse' 
          AND json_extract_string(data, '$.tool_name') = 'Task'
          AND json_extract_string(data, '$.tool_input.subagent_type') IS NOT NULL
        GROUP BY agent_type
        ORDER BY usage_count DESC
    """).fetchall()
    
    conn.close()
    
    return jsonify([{
        'agent_type': row[0],
        'usage_count': row[1],
        'sessions_used': row[2],
        'first_used': row[3].isoformat() if row[3] else None,
        'last_used': row[4].isoformat() if row[4] else None
    } for row in agents])

@app.route('/api/agent/<agent_type>')
def get_agent_detail(agent_type):
    """Get detailed statistics and sessions for a specific agent"""
    conn = duckdb.connect(DB_PATH, read_only=True)
    
    # Get agent statistics including performance range
    # Note: Duration data is in PostToolUse events
    stats = conn.execute("""
        SELECT 
            COUNT(*) as total_invocations,
            COUNT(DISTINCT json_extract_string(data, '$.session_id')) as unique_sessions,
            MIN(timestamp) as first_used,
            MAX(timestamp) as last_used,
            AVG(CAST(json_extract_string(data, '$.tool_response.totalDurationMs') AS DOUBLE)) as avg_duration_ms,
            MIN(CAST(json_extract_string(data, '$.tool_response.totalDurationMs') AS DOUBLE)) as min_duration_ms,
            MAX(CAST(json_extract_string(data, '$.tool_response.totalDurationMs') AS DOUBLE)) as max_duration_ms,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY CAST(json_extract_string(data, '$.tool_response.totalDurationMs') AS DOUBLE)) as median_duration_ms,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY CAST(json_extract_string(data, '$.tool_response.totalDurationMs') AS DOUBLE)) as p95_duration_ms
        FROM all_events 
        WHERE event_type = 'PostToolUse' 
          AND json_extract_string(data, '$.tool_name') = 'Task'
          AND json_extract_string(data, '$.tool_input.subagent_type') = ?
    """, [agent_type]).fetchone()
    
    # Get recent invocations with session details
    invocations = conn.execute("""
        SELECT 
            timestamp,
            json_extract_string(data, '$.session_id') as session_id,
            json_extract_string(data, '$.tool_input.description') as description,
            json_extract_string(data, '$.cwd') as cwd,
            json_extract_string(data, '$.tmux_session') as tmux_session
        FROM all_events 
        WHERE event_type = 'PreToolUse' 
          AND json_extract_string(data, '$.tool_name') = 'Task'
          AND json_extract_string(data, '$.tool_input.subagent_type') = ?
        ORDER BY timestamp DESC
        LIMIT 50
    """, [agent_type]).fetchall()
    
    # Get sessions that used this agent
    sessions = conn.execute("""
        WITH agent_sessions AS (
            SELECT DISTINCT 
                json_extract_string(data, '$.session_id') as session_id
            FROM all_events 
            WHERE event_type = 'PreToolUse' 
              AND json_extract_string(data, '$.tool_name') = 'Task'
              AND json_extract_string(data, '$.tool_input.subagent_type') = ?
        )
        SELECT 
            s.session_id,
            MIN(e.timestamp) as session_start,
            MAX(e.timestamp) as session_end,
            COUNT(*) as total_events,
            MAX(json_extract_string(e.data, '$.cwd')) as cwd,
            MAX(json_extract_string(e.data, '$.tmux_session')) as tmux_session
        FROM agent_sessions s
        JOIN all_events e ON json_extract_string(e.data, '$.session_id') = s.session_id
        GROUP BY s.session_id
        ORDER BY MAX(e.timestamp) DESC
        LIMIT 20
    """, [agent_type]).fetchall()
    
    conn.close()
    
    return jsonify({
        'agent_type': agent_type,
        'stats': {
            'total_invocations': stats[0] if stats else 0,
            'unique_sessions': stats[1] if stats else 0,
            'first_used': stats[2].isoformat() if stats and stats[2] else None,
            'last_used': stats[3].isoformat() if stats and stats[3] else None,
            'avg_duration_ms': round(stats[4]) if stats and stats[4] else None,
            'min_duration_ms': round(stats[5]) if stats and stats[5] else None,
            'max_duration_ms': round(stats[6]) if stats and stats[6] else None,
            'median_duration_ms': round(stats[7]) if stats and stats[7] else None,
            'p95_duration_ms': round(stats[8]) if stats and stats[8] else None
        },
        'recent_invocations': [{
            'timestamp': row[0].isoformat() if row[0] else None,
            'session_id': row[1],
            'description': row[2],
            'cwd': row[3],
            'tmux_session': row[4]
        } for row in invocations],
        'sessions': [{
            'session_id': row[0],
            'session_start': row[1].isoformat() if row[1] else None,
            'session_end': row[2].isoformat() if row[2] else None,
            'total_events': row[3],
            'cwd': row[4],
            'tmux_session': row[5],
            'duration_seconds': (row[2] - row[1]).total_seconds() if row[1] and row[2] else None
        } for row in sessions]
    })

@app.route('/api/tracking/active-sessions')
def get_active_sessions():
    """Get currently active sessions (sessions without SessionEnd events)"""
    conn = duckdb.connect(DB_PATH, read_only=True)
    
    # Get active sessions with their details
    active = conn.execute("""
        WITH session_events AS (
            SELECT 
                json_extract_string(data, '$.session_id') as session_id,
                MIN(timestamp) as session_start,
                MAX(timestamp) as last_event,
                COUNT(*) as total_events,
                MAX(json_extract_string(data, '$.cwd')) as cwd,
                MAX(json_extract_string(data, '$.tmux_session')) as tmux_session,
                COUNT(*) FILTER (WHERE event_type = 'SessionEnd') as end_events
            FROM all_events
            WHERE json_extract_string(data, '$.session_id') IS NOT NULL
            GROUP BY session_id
            HAVING end_events = 0  -- Only sessions without SessionEnd
        )
        SELECT 
            session_id,
            session_start,
            last_event,
            total_events,
            cwd,
            tmux_session,
            EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - last_event)) as seconds_since_last
        FROM session_events
        WHERE EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - last_event)) < 3600  -- Active within last hour
        ORDER BY last_event DESC
        LIMIT 10
    """).fetchall()
    
    conn.close()
    
    return jsonify([{
        'session_id': row[0],
        'session_start': row[1].isoformat() if row[1] else None,
        'last_event': row[2].isoformat() if row[2] else None,
        'total_events': row[3],
        'cwd': row[4],
        'tmux_session': row[5],
        'seconds_since_last': row[6],
        'duration_seconds': (row[2] - row[1]).total_seconds() if row[1] and row[2] else None
    } for row in active])

@app.route('/api/tracking/session/<session_id>/timeline')
def get_session_timeline(session_id):
    """Get detailed timeline for a specific session"""
    conn = duckdb.connect(DB_PATH, read_only=True)
    
    # Get all events for this session with full data
    events = conn.execute("""
        SELECT 
            timestamp,
            event_type,
            json_extract_string(data, '$.tool_name') as tool_name,
            json_extract_string(data, '$.tool_input.command') as command,
            json_extract_string(data, '$.tool_input.file_path') as file_path,
            json_extract_string(data, '$.tool_input.pattern') as pattern,
            json_extract_string(data, '$.tool_input.description') as description,
            json_extract_string(data, '$.source') as source,
            json_extract_string(data, '$.permission_mode') as permission_mode,
            json_extract_string(data, '$.tool_input.url') as url,
            json_extract_string(data, '$.tool_input.query') as query,
            json_extract_string(data, '$.tool_input.old_string') as old_string,
            json_extract_string(data, '$.tool_input.new_string') as new_string,
            json_extract_string(data, '$.tool_input.subagent_type') as subagent_type,
            data as full_data
        FROM all_events
        WHERE json_extract_string(data, '$.session_id') = ?
        ORDER BY timestamp ASC
    """, [session_id]).fetchall()
    
    conn.close()
    
    return jsonify([{
        'timestamp': event[0].isoformat() if event[0] else None,
        'event_type': event[1],
        'tool_name': event[2],
        'command': event[3],
        'file_path': event[4],
        'pattern': event[5],
        'description': event[6],
        'source': event[7],
        'permission_mode': event[8],
        'url': event[9],
        'query': event[10],
        'old_string': event[11],
        'new_string': event[12],
        'subagent_type': event[13],
        'full_data': json.loads(event[14]) if event[14] else None
    } for event in events])

# All API endpoints use the all_events table

if __name__ == '__main__':
    # Check if database exists
    if not os.path.exists(DB_PATH):
        print(f"Warning: Database not found at {DB_PATH}")
        print("Make sure to run the hooks to generate some data first!")
    
    app.run(debug=True, port=8090, host='0.0.0.0')