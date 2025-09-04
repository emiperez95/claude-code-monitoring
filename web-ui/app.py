from flask import Flask, render_template, jsonify, request, send_from_directory
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

@app.route('/favicon.ico')
def favicon():
    """Serve favicon from static directory"""
    return send_from_directory(os.path.join(app.root_path, 'static'),
                               'favicon.ico', mimetype='image/vnd.microsoft.icon')

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
        ),
        subagent_data AS (
            SELECT 
                session_id,
                LIST(agent_type ORDER BY first_use) as agents_list,
                COUNT(DISTINCT agent_type) as unique_agents_count
            FROM (
                SELECT 
                    json_extract_string(data, '$.session_id') as session_id,
                    json_extract_string(data, '$.tool_input.subagent_type') as agent_type,
                    MIN(timestamp) as first_use
                FROM all_events
                WHERE event_type = 'PreToolUse'
                    AND json_extract_string(data, '$.tool_name') = 'Task'
                    AND json_extract_string(data, '$.tool_input.subagent_type') IS NOT NULL
                GROUP BY 
                    json_extract_string(data, '$.session_id'),
                    json_extract_string(data, '$.tool_input.subagent_type')
            ) agent_times
            GROUP BY session_id
        )
        SELECT 
            s.session_id,
            s.session_start,
            s.session_end,
            s.total_events,
            s.unique_tools,
            s.start_events,
            s.end_events,
            s.start_source,
            s.cwd,
            s.tmux_session,
            s.tools_used,
            CASE 
                WHEN s.end_events > 0 THEN 'completed'
                WHEN s.session_end > NOW() - INTERVAL '5 minutes' THEN 'active'
                ELSE 'inactive'
            END as status,
            COALESCE(sa.agents_list, []) as agents_used,
            COALESCE(sa.unique_agents_count, 0) as unique_agents
        FROM session_stats s
        LEFT JOIN subagent_data sa ON s.session_id = sa.session_id
        ORDER BY s.session_start DESC
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
        'agents_used': row[12] if row[12] else [],
        'unique_agents': row[13],
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
        ),
        subagent_data AS (
            SELECT 
                session_id,
                LIST(agent_type ORDER BY first_use) as agents_list
            FROM (
                SELECT 
                    json_extract_string(data, '$.session_id') as session_id,
                    json_extract_string(data, '$.tool_input.subagent_type') as agent_type,
                    MIN(timestamp) as first_use
                FROM all_events
                WHERE event_type = 'PreToolUse'
                    AND json_extract_string(data, '$.tool_name') = 'Task'
                    AND json_extract_string(data, '$.tool_input.subagent_type') IS NOT NULL
                GROUP BY 
                    json_extract_string(data, '$.session_id'),
                    json_extract_string(data, '$.tool_input.subagent_type')
            ) agent_times
            GROUP BY session_id
        )
        SELECT 
            se.session_id,
            se.session_start,
            se.last_event,
            se.total_events,
            se.cwd,
            se.tmux_session,
            EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - se.last_event)) as seconds_since_last,
            COALESCE(sa.agents_list, []) as agents_used
        FROM session_events se
        LEFT JOIN subagent_data sa ON se.session_id = sa.session_id
        WHERE EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - se.last_event)) < 3600  -- Active within last hour
        ORDER BY se.last_event DESC
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
        'agents_used': row[7] if row[7] else [],
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

@app.route('/tmux-sessions')
def tmux_sessions_page():
    """Display tmux sessions dashboard with timeline visualization"""
    return render_template('tmux_sessions.html')

@app.route('/tmux-session/<path:tmux_name>')
def tmux_session_detail_page(tmux_name):
    """Display detailed view for a specific tmux session"""
    return render_template('tmux_session_detail.html', tmux_name=tmux_name)

@app.route('/api/tracking/tmux-sessions')
def get_tmux_sessions():
    """Get all tmux sessions with aggregated statistics"""
    conn = duckdb.connect(DB_PATH, read_only=True)
    
    # Get tmux sessions with their statistics
    sessions = conn.execute("""
        WITH tmux_stats AS (
            SELECT 
                json_extract_string(data, '$.tmux_session') as tmux_session,
                json_extract_string(data, '$.session_id') as session_id,
                MIN(timestamp) as session_start,
                MAX(timestamp) as session_end,
                COUNT(*) as event_count
            FROM all_events
            WHERE json_extract_string(data, '$.tmux_session') IS NOT NULL 
                AND json_extract_string(data, '$.tmux_session') != ''
            GROUP BY 
                json_extract_string(data, '$.tmux_session'),
                json_extract_string(data, '$.session_id')
        ),
        tmux_aggregated AS (
            SELECT 
                tmux_session,
                COUNT(DISTINCT session_id) as total_sessions,
                MIN(session_start) as first_activity,
                MAX(session_end) as last_activity,
                SUM(event_count) as total_events,
                SUM(EXTRACT(EPOCH FROM (session_end - session_start))) as total_duration_seconds,
                LIST(DISTINCT session_id) as session_ids
            FROM tmux_stats
            GROUP BY tmux_session
        )
        SELECT 
            tmux_session,
            total_sessions,
            first_activity,
            last_activity,
            total_events,
            total_duration_seconds,
            session_ids,
            CASE 
                WHEN last_activity > CURRENT_TIMESTAMP - INTERVAL '1 hour' THEN 'active'
                WHEN last_activity > CURRENT_TIMESTAMP - INTERVAL '24 hours' THEN 'recent'
                ELSE 'inactive'
            END as status
        FROM tmux_aggregated
        ORDER BY last_activity DESC
    """).fetchall()
    
    conn.close()
    
    return jsonify([{
        'tmux_session': row[0],
        'total_sessions': row[1],
        'first_activity': row[2].isoformat() if row[2] else None,
        'last_activity': row[3].isoformat() if row[3] else None,
        'total_events': row[4],
        'total_duration_seconds': row[5],
        'session_ids': row[6] if row[6] else [],
        'status': row[7]
    } for row in sessions])

@app.route('/api/tracking/tmux-session/<path:tmux_name>/timeline')
def get_tmux_session_timeline(tmux_name):
    """Get detailed timeline for a specific tmux session with activity gaps"""
    conn = duckdb.connect(DB_PATH, read_only=True)
    
    # Get all events for this tmux session with gap analysis
    timeline = conn.execute("""
        WITH session_events AS (
            SELECT 
                timestamp,
                json_extract_string(data, '$.session_id') as session_id,
                event_type,
                json_extract_string(data, '$.tool_name') as tool_name,
                json_extract_string(data, '$.tool_input.description') as description,
                json_extract_string(data, '$.tool_input.command') as command,
                json_extract_string(data, '$.tool_input.file_path') as file_path,
                LEAD(timestamp) OVER (
                    PARTITION BY json_extract_string(data, '$.session_id') 
                    ORDER BY timestamp
                ) as next_timestamp
            FROM all_events
            WHERE json_extract_string(data, '$.tmux_session') = ?
        ),
        events_with_gaps AS (
            SELECT 
                *,
                EXTRACT(EPOCH FROM (next_timestamp - timestamp)) as gap_seconds,
                CASE 
                    WHEN next_timestamp IS NULL THEN 'session_end'
                    WHEN EXTRACT(EPOCH FROM (next_timestamp - timestamp)) > 30 THEN 'waiting'
                    WHEN EXTRACT(EPOCH FROM (next_timestamp - timestamp)) > 5 THEN 'idle'
                    ELSE 'active'
                END as activity_state
            FROM session_events
        )
        SELECT 
            timestamp,
            session_id,
            event_type,
            tool_name,
            description,
            command,
            file_path,
            next_timestamp,
            gap_seconds,
            activity_state
        FROM events_with_gaps
        ORDER BY timestamp ASC
        LIMIT 1000
    """, [tmux_name]).fetchall()
    
    # Get session-level summary
    sessions_summary = conn.execute("""
        WITH session_stats AS (
            SELECT 
                json_extract_string(data, '$.session_id') as session_id,
                MIN(timestamp) as start_time,
                MAX(timestamp) as end_time,
                COUNT(*) as event_count
            FROM all_events
            WHERE json_extract_string(data, '$.tmux_session') = ?
            GROUP BY json_extract_string(data, '$.session_id')
        )
        SELECT 
            session_id,
            start_time,
            end_time,
            event_count,
            EXTRACT(EPOCH FROM (end_time - start_time)) as duration_seconds
        FROM session_stats
        ORDER BY start_time ASC
    """, [tmux_name]).fetchall()
    
    conn.close()
    
    return jsonify({
        'tmux_session': tmux_name,
        'timeline': [{
            'timestamp': event[0].isoformat() if event[0] else None,
            'session_id': event[1],
            'event_type': event[2],
            'tool_name': event[3],
            'description': event[4],
            'command': event[5],
            'file_path': event[6],
            'next_timestamp': event[7].isoformat() if event[7] else None,
            'gap_seconds': event[8],
            'activity_state': event[9]
        } for event in timeline],
        'sessions': [{
            'session_id': sess[0],
            'start_time': sess[1].isoformat() if sess[1] else None,
            'end_time': sess[2].isoformat() if sess[2] else None,
            'event_count': sess[3],
            'duration_seconds': sess[4]
        } for sess in sessions_summary]
    })

@app.route('/api/tracking/tmux-session/<path:tmux_name>/activity')
def get_tmux_session_activity(tmux_name):
    """Get activity periods and idle gaps for a tmux session - ONLY for sessions with Stop events"""
    conn = duckdb.connect(DB_PATH, read_only=True)
    
    # ONLY analyze sessions that have Stop events - no estimation
    stop_based_analysis = conn.execute("""
        WITH session_events AS (
            SELECT 
                timestamp,
                event_type,
                json_extract_string(data, '$.session_id') as session_id,
                LEAD(timestamp) OVER (
                    PARTITION BY json_extract_string(data, '$.session_id') 
                    ORDER BY timestamp
                ) as next_timestamp,
                LEAD(event_type) OVER (
                    PARTITION BY json_extract_string(data, '$.session_id') 
                    ORDER BY timestamp
                ) as next_event_type
            FROM all_events
            WHERE json_extract_string(data, '$.tmux_session') = ?
              AND json_extract_string(data, '$.session_id') IN (
                  SELECT DISTINCT json_extract_string(data, '$.session_id')
                  FROM all_events
                  WHERE event_type = 'Stop'
                    AND json_extract_string(data, '$.tmux_session') = ?
              )
        ),
        work_periods AS (
            SELECT 
                session_id,
                -- Working time: UserPromptSubmit/SessionStart to Stop
                SUM(CASE 
                    WHEN event_type IN ('UserPromptSubmit', 'SessionStart') 
                         AND next_event_type = 'Stop'
                    THEN EXTRACT(EPOCH FROM (next_timestamp - timestamp))
                    ELSE 0 
                END) as working_time_seconds,
                -- Waiting time: Stop to UserPromptSubmit
                SUM(CASE 
                    WHEN event_type = 'Stop' 
                         AND next_event_type = 'UserPromptSubmit'
                    THEN EXTRACT(EPOCH FROM (next_timestamp - timestamp))
                    ELSE 0 
                END) as waiting_time_seconds,
                COUNT(CASE WHEN event_type = 'Stop' THEN 1 END) as stop_count,
                COUNT(CASE WHEN event_type = 'UserPromptSubmit' THEN 1 END) as prompt_count
            FROM session_events
            GROUP BY session_id
        )
        SELECT 
            session_id,
            working_time_seconds,
            waiting_time_seconds,
            working_time_seconds + waiting_time_seconds as total_time_seconds,
            CASE 
                WHEN (working_time_seconds + waiting_time_seconds) > 0 
                THEN (working_time_seconds * 100.0) / (working_time_seconds + waiting_time_seconds)
                ELSE 0 
            END as active_percentage,
            stop_count,
            prompt_count
        FROM work_periods
        WHERE working_time_seconds IS NOT NULL OR waiting_time_seconds IS NOT NULL
    """, [tmux_name, tmux_name]).fetchall()
    
    
    # Get significant gaps (> 60 seconds) for visualization
    significant_gaps = conn.execute("""
        WITH session_events AS (
            SELECT 
                timestamp,
                json_extract_string(data, '$.session_id') as session_id,
                json_extract_string(data, '$.tool_name') as last_tool,
                LEAD(timestamp) OVER (
                    PARTITION BY json_extract_string(data, '$.session_id') 
                    ORDER BY timestamp
                ) as next_timestamp,
                LEAD(json_extract_string(data, '$.tool_name')) OVER (
                    PARTITION BY json_extract_string(data, '$.session_id') 
                    ORDER BY timestamp
                ) as next_tool
            FROM all_events
            WHERE json_extract_string(data, '$.tmux_session') = ?
        )
        SELECT 
            session_id,
            timestamp as gap_start,
            next_timestamp as gap_end,
            EXTRACT(EPOCH FROM (next_timestamp - timestamp)) as gap_seconds,
            last_tool,
            next_tool
        FROM session_events
        WHERE EXTRACT(EPOCH FROM (next_timestamp - timestamp)) > 60
        ORDER BY gap_seconds DESC
        LIMIT 50
    """, [tmux_name]).fetchall()
    
    conn.close()
    
    # Only return stop-based analysis - no estimation
    activity_summary = []
    
    # Add stop-based analysis (accurate)
    for row in stop_based_analysis:
        working_seconds = row[1] or 0
        waiting_seconds = row[2] or 0
        
        # For gap distribution, categorize the waiting periods
        short_waits = 0
        medium_waits = 0
        long_waits = 0
        
        if waiting_seconds > 0:
            # If we have waiting time, categorize it
            if waiting_seconds <= 60:
                short_waits = 1
            elif waiting_seconds <= 300:
                medium_waits = 1
            else:
                long_waits = 1
        
        activity_summary.append({
            'session_id': row[0],
            'has_accurate_data': True,
            'data_source': 'stop_events',
            'working_time_seconds': working_seconds,
            'waiting_time_seconds': waiting_seconds,
            'total_time_seconds': row[3] or 0,
            'active_percentage': row[4] or 0,
            'stop_count': row[5],
            'prompt_count': row[6],
            # Legacy fields for compatibility
            'active_time_seconds': working_seconds,
            'active_periods': row[5] if working_seconds > 0 else 0,  # Only count if there's work
            'idle_periods': 0,
            'short_waits': short_waits,
            'medium_waits': medium_waits,
            'long_waits': long_waits,
            'longest_gap_seconds': waiting_seconds,
            'avg_gap_seconds': waiting_seconds / row[5] if row[5] > 0 else 0,
            'median_gap_seconds': waiting_seconds / row[5] if row[5] > 0 else 0
        })
    
    return jsonify({
        'tmux_session': tmux_name,
        'activity_summary': activity_summary,
        'significant_gaps': [{
            'session_id': gap[0],
            'gap_start': gap[1].isoformat() if gap[1] else None,
            'gap_end': gap[2].isoformat() if gap[2] else None,
            'gap_seconds': gap[3],
            'last_tool': gap[4],
            'next_tool': gap[5]
        } for gap in significant_gaps]
    })

@app.route('/api/tracking/session/<session_id>/agents')
def get_session_agents_timeline(session_id):
    """Get agent execution timeline for a specific session"""
    conn = duckdb.connect(DB_PATH, read_only=True)
    
    # Get all agent invocations with timing data
    agents_data = conn.execute("""
        WITH agent_events AS (
            SELECT 
                json_extract_string(data, '$.tool_input.subagent_type') as agent_type,
                json_extract_string(data, '$.tool_input.description') as description,
                event_type,
                timestamp,
                json_extract_string(data, '$.tool_response.token_usage.total_tokens') as total_tokens
            FROM all_events
            WHERE json_extract_string(data, '$.session_id') = ?
                AND json_extract_string(data, '$.tool_name') = 'Task'
                AND json_extract_string(data, '$.tool_input.subagent_type') IS NOT NULL
        ),
        -- First get all PreToolUse events
        pre_events AS (
            SELECT 
                agent_type,
                description,
                timestamp as pre_time,
                ROW_NUMBER() OVER (PARTITION BY agent_type ORDER BY timestamp) as rn
            FROM agent_events
            WHERE event_type = 'PreToolUse'
        ),
        -- Then get all PostToolUse events  
        post_events AS (
            SELECT 
                agent_type,
                description,
                timestamp as post_time,
                total_tokens,
                ROW_NUMBER() OVER (PARTITION BY agent_type ORDER BY timestamp) as rn
            FROM agent_events
            WHERE event_type = 'PostToolUse'
        ),
        -- Combine them, including orphaned PostToolUse events
        paired_events AS (
            SELECT 
                COALESCE(pre.agent_type, post.agent_type) as agent_type,
                COALESCE(pre.description, post.description) as description,
                COALESCE(pre.pre_time, post.post_time) as start_time,
                post.post_time as end_time,
                CASE 
                    WHEN pre.pre_time IS NOT NULL AND post.post_time IS NOT NULL 
                    THEN EXTRACT(EPOCH FROM (post.post_time - pre.pre_time))
                    ELSE NULL
                END as duration_seconds,
                post.total_tokens
            FROM pre_events pre
            FULL OUTER JOIN post_events post 
                ON pre.agent_type = post.agent_type 
                AND pre.rn = post.rn
        ),
        with_ordering AS (
            SELECT 
                *,
                ROW_NUMBER() OVER (ORDER BY start_time) as execution_order,
                LAG(start_time) OVER (ORDER BY start_time) as prev_start_time
            FROM paired_events
        ),
        with_groups AS (
            SELECT 
                *,
                SUM(CASE 
                    WHEN prev_start_time IS NULL 
                        OR start_time - prev_start_time > INTERVAL '1 second'
                    THEN 1 
                    ELSE 0 
                END) OVER (ORDER BY start_time) as group_id
            FROM with_ordering
        )
        SELECT 
            agent_type,
            description,
            start_time,
            end_time,
            duration_seconds,
            total_tokens,
            execution_order,
            group_id,
            COUNT(*) OVER (PARTITION BY group_id) as group_size,
            ROW_NUMBER() OVER (PARTITION BY group_id ORDER BY start_time) as position_in_group
        FROM with_groups
        ORDER BY start_time ASC
    """, [session_id]).fetchall()
    
    # Get summary statistics
    stats = conn.execute("""
        SELECT 
            COUNT(DISTINCT json_extract_string(data, '$.tool_input.subagent_type')) as unique_agents,
            COUNT(DISTINCT 
                CASE WHEN event_type IN ('PreToolUse', 'PostToolUse') 
                THEN json_extract_string(data, '$.tool_input.subagent_type') || event_type 
                END
            ) as total_events,
            NULL as avg_duration_seconds  -- Will calculate from agents_data
        FROM all_events
        WHERE json_extract_string(data, '$.session_id') = ?
            AND json_extract_string(data, '$.tool_name') = 'Task'
            AND json_extract_string(data, '$.tool_input.subagent_type') IS NOT NULL
    """, [session_id]).fetchone()
    
    conn.close()
    
    # Format the response
    agents = []
    for row in agents_data:
        agents.append({
            'agent_type': row[0],
            'description': row[1],
            'start_time': row[2].isoformat() if row[2] else None,
            'end_time': row[3].isoformat() if row[3] else None,
            'duration_seconds': row[4],
            'total_tokens': int(row[5]) if row[5] else None,
            'execution_order': row[6],
            'group_id': row[7],
            'group_size': row[8],
            'position_in_group': row[9],
            'is_parallel': row[8] > 1
        })
    
    # Calculate average duration from agents that have it
    durations = [a['duration_seconds'] for a in agents if a['duration_seconds'] is not None]
    avg_duration = sum(durations) / len(durations) if durations else None
    
    return jsonify({
        'agents': agents,
        'stats': {
            'unique_agents': stats[0] if stats else 0,
            'total_invocations': len(agents),  # Count actual agent invocations
            'avg_duration_seconds': avg_duration,
            'parallel_groups': len(set(a['group_id'] for a in agents if a['is_parallel']))
        }
    })

# All API endpoints use the all_events table

if __name__ == '__main__':
    # Check if database exists
    if not os.path.exists(DB_PATH):
        print(f"Warning: Database not found at {DB_PATH}")
        print("Make sure to run the hooks to generate some data first!")
    
    app.run(debug=True, port=8090, host='0.0.0.0')