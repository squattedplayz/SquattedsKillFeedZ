from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import sqlite3

app = FastAPI(title="SquattedsKillFeedZ API")
DB_NAME = "dayz_stats.db"

@app.get("/", response_class=HTMLResponse)
def read_root():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>SquattedsKillFeedZ | Server Dashboard</title>
        <style>
            :root {
                --bg-deep: #0a080f;
                --bg-panel: #13101c;
                --bg-hover: #1f1a2e;
                --neon-purple: #c084fc;
                --neon-glow: rgba(192, 132, 252, 0.4);
                --text-main: #f3f4f6;
                --text-muted: #9ca3af;
                --border-color: #2e2640;
            }

            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: var(--bg-deep);
                color: var(--text-main);
                margin: 0;
                padding: 0;
                display: flex;
                height: 100vh;
            }

            /* Sidebar Styling */
            sidebar {
                width: 260px;
                background-color: var(--bg-panel);
                border-right: 1px solid var(--border-color);
                display: flex;
                flex-direction: column;
                padding: 24px;
            }

            .brand {
                font-size: 1.1rem;
                font-weight: bold;
                color: var(--neon-purple);
                margin-bottom: 30px;
                letter-spacing: 1.5px;
                text-shadow: 0 0 10px var(--neon-glow);
            }

            .nav-links {
                list-style: none;
                padding: 0;
                margin: 0;
            }

            .nav-links li {
                padding: 12px 16px;
                margin-bottom: 8px;
                border-radius: 6px;
                cursor: pointer;
                color: var(--text-muted);
                transition: all 0.2s ease;
            }

            .nav-links li.active, .nav-links li:hover {
                background-color: var(--bg-hover);
                color: var(--neon-purple);
                border-left: 3px solid var(--neon-purple);
            }

            /* Main Content Area */
            .main-content {
                flex: 1;
                padding: 40px;
                overflow-y: auto;
            }

            header h1 {
                margin: 0 0 5px 0;
                color: var(--text-main);
                font-size: 1.8rem;
            }

            header p {
                color: var(--text-muted);
                margin-top: 0;
            }

            /* Dashboard Card */
            .card {
                background-color: var(--bg-panel);
                border: 1px solid var(--border-color);
                border-radius: 8px;
                padding: 24px;
                margin-top: 25px;
                box-shadow: 0 8px 16px rgba(0, 0, 0, 0.4);
            }

            .card h2 {
                margin-top: 0;
                font-size: 1.2rem;
                color: var(--neon-purple);
                border-bottom: 1px solid var(--border-color);
                padding-bottom: 12px;
                text-shadow: 0 0 8px var(--neon-glow);
            }

            /* Table Styling */
            table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 15px;
            }

            th, td {
                padding: 14px 16px;
                text-align: left;
                border-bottom: 1px solid var(--border-color);
            }

            th {
                color: var(--text-muted);
                font-weight: 600;
                font-size: 0.85rem;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }

            tr:hover td {
                background-color: var(--bg-hover);
            }

            .rank-badge {
                font-weight: bold;
                color: var(--neon-purple);
            }

            .hidden {
                display: none;
            }
        </style>
    </head>
    <body>

        <sidebar>
            <div class="brand">SquattedsKillFeedZ</div>
            <ul class="nav-links">
                <li id="nav-leaderboard" class="active" onclick="switchTab('leaderboard')">Leaderboard</li>
                <li id="nav-kills" onclick="switchTab('kills')">Recent Kills</li>
                <li onclick="alert('Server Info coming soon!')">Server Info</li>
            </ul>
        </sidebar>

        <div class="main-content">
            <header>
                <h1>Server Telemetry</h1>
                <p>Live session analytics and combat stats tracker.</p>
            </header>

            <!-- Leaderboard View -->
            <div id="section-leaderboard" class="card">
                <h2>Top Killers Leaderboard</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Rank</th>
                            <th>Player</th>
                            <th>Kills</th>
                        </tr>
                    </thead>
                    <tbody id="leaderboard-body">
                        <!-- Populated via JS -->
                    </tbody>
                </table>
            </div>

            <!-- Recent Kills View -->
            <div id="section-kills" class="card hidden">
                <h2>Recent Combat Feed</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Killer</th>
                            <th>Victim</th>
                        </tr>
                    </thead>
                    <tbody id="kills-body">
                        <!-- Populated via JS -->
                    </tbody>
                </table>
            </div>
        </div>

        <script>
            function switchTab(tab) {
                document.getElementById('nav-leaderboard').classList.remove('active');
                document.getElementById('nav-kills').classList.remove('active');
                document.getElementById('section-leaderboard').classList.add('hidden');
                document.getElementById('section-kills').classList.add('hidden');

                if (tab === 'leaderboard') {
                    document.getElementById('nav-leaderboard').classList.add('active');
                    document.getElementById('section-leaderboard').classList.remove('hidden');
                } else if (tab === 'kills') {
                    document.getElementById('nav-kills').classList.add('active');
                    document.getElementById('section-kills').classList.remove('hidden');
                }
            }

            // Fetch Leaderboard Data
            fetch('/leaderboard')
                .then(response => response.json())
                .then(data => {
                    const tbody = document.getElementById('leaderboard-body');
                    tbody.innerHTML = "";
                    data.leaderboard.forEach((entry, index) => {
                        tbody.innerHTML += `<tr>
                            <td class="rank-badge">#${index + 1}</td>
                            <td>${entry.player}</td>
                            <td>${entry.kills}</td>
                        </tr>`;
                    });
                });

            // Fetch Recent Kills Data
            fetch('/recent-kills')
                .then(response => response.json())
                .then(data => {
                    const tbody = document.getElementById('kills-body');
                    tbody.innerHTML = "";
                    data.recent_kills.forEach((entry) => {
                        tbody.innerHTML += `<tr>
                            <td class="rank-badge">${entry.killer}</td>
                            <td>${entry.victim}</td>
                        </tr>`;
                    });
                });
        </script>

    </body>
    </html>
    """

@app.get("/leaderboard")
def get_leaderboard():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT killer, COUNT(*) as kill_count 
        FROM kills 
        GROUP BY killer 
        ORDER BY kill_count DESC
    ''')
    results = cursor.fetchall()
    conn.close()
    return {"leaderboard": [{"player": row[0], "kills": row[1]} for row in results]}

@app.get("/recent-kills")
def get_recent_kills():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Adjust column names here if your table uses different names for victim/killer
    cursor.execute('''
        SELECT killer, victim 
        FROM kills 
        ORDER BY rowid DESC 
        LIMIT 25
    ''')
    results = cursor.fetchall()
    conn.close()
    return {"recent_kills": [{"killer": row[0], "victim": row[1]} for row in results]}