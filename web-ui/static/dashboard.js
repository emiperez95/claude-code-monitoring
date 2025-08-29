function dashboard() {
    return {
        summary: { total_events: 0, unique_sessions: 0, unique_agents: 0 },
        subagents: [],
        recentEvents: [],
        sessions: [],
        autoRefresh: true,
        refreshInterval: null,
        
        async init() {
            await this.loadAllData();
            
            // Set up auto-refresh
            this.refreshInterval = setInterval(() => {
                if (this.autoRefresh) {
                    this.loadAllData();
                }
            }, 30000); // 30 seconds
        },
        
        async loadAllData() {
            await Promise.all([
                this.loadSummary(),
                this.loadSubagents(),
                this.loadRecentEvents(),
                this.loadSessions()
            ]);
        },
        
        async loadSummary() {
            try {
                const response = await fetch('/api/summary');
                if (response.ok) {
                    this.summary = await response.json();
                }
            } catch (error) {
                console.error('Error loading summary:', error);
            }
        },
        
        async loadSubagents() {
            try {
                const response = await fetch('/api/subagents');
                if (response.ok) {
                    this.subagents = await response.json();
                }
            } catch (error) {
                console.error('Error loading subagents:', error);
            }
        },
        
        async loadRecentEvents() {
            try {
                const response = await fetch('/api/recent-events?limit=20');
                if (response.ok) {
                    this.recentEvents = await response.json();
                }
            } catch (error) {
                console.error('Error loading recent events:', error);
            }
        },
        
        async loadSessions() {
            try {
                const response = await fetch('/api/sessions?limit=10');
                if (response.ok) {
                    const data = await response.json();
                    // Handle both old array format and new paginated format
                    this.sessions = Array.isArray(data) ? data : (data.sessions || []);
                }
            } catch (error) {
                console.error('Error loading sessions:', error);
            }
        },
        
        formatTime(timestamp) {
            if (!timestamp) return '-';
            const date = new Date(timestamp);
            const now = new Date();
            const diff = now - date;
            
            // If less than 1 hour ago, show relative time
            if (diff < 3600000) {
                const minutes = Math.floor(diff / 60000);
                if (minutes < 1) return 'just now';
                return `${minutes}m ago`;
            }
            
            // If today, show time
            if (date.toDateString() === now.toDateString()) {
                return date.toLocaleTimeString('en-US', { 
                    hour: '2-digit', 
                    minute: '2-digit' 
                });
            }
            
            // Otherwise show date and time
            return date.toLocaleDateString('en-US', { 
                month: 'short', 
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit'
            });
        },
        
        formatDuration(seconds) {
            if (!seconds || seconds < 1) return '-';
            
            if (seconds < 60) {
                return `${Math.round(seconds)}s`;
            } else if (seconds < 3600) {
                const minutes = Math.floor(seconds / 60);
                const secs = Math.round(seconds % 60);
                return `${minutes}m ${secs}s`;
            } else {
                const hours = Math.floor(seconds / 3600);
                const minutes = Math.floor((seconds % 3600) / 60);
                return `${hours}h ${minutes}m`;
            }
        }
    }
}