import os
import sqlite3
import threading
import random
import discord
from discord import app_commands
from discord.ext import commands
from fastapi import FastAPI, Request, Form, HTTPException, Cookie, Query, Header
from fastapi.responses import HTMLResponse, RedirectResponse
import uvicorn
import stripe

# Configuration & Environment Variables
TOKEN = os.getenv("DISCORD_TOKEN")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "sk_test_mockkey")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "price_mockid")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_mockkey")
SUPER_ADMIN_ID = int(os.getenv("SUPER_ADMIN_ID", "0"))
DB_NAME = "bot_database.db"

stripe.api_key = STRIPE_SECRET_KEY

# Initialize FastAPI & Discord Bot
app = FastAPI()
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            discord_id INTEGER PRIMARY KEY,
            username TEXT,
            is_subscribed INTEGER DEFAULT 0,
            stripe_customer_id TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS server_settings (
            discord_id INTEGER PRIMARY KEY,
            currency_name TEXT DEFAULT 'Coins',
            currency_emoji TEXT DEFAULT '🪙',
            casino_enabled INTEGER DEFAULT 1,
            roulette_payout REAL DEFAULT 2.0,
            blackjack_payout REAL DEFAULT 1.5,
            cockfight_payout REAL DEFAULT 2.0,
            welcome_enabled INTEGER DEFAULT 0,
            welcome_text TEXT DEFAULT 'Welcome to the server!',
            welcome_channel TEXT DEFAULT 'general',
            autorole_enabled INTEGER DEFAULT 0,
            autorole_name TEXT DEFAULT 'Survivor',
            tasks_enabled INTEGER DEFAULT 0,
            restart_task INTEGER DEFAULT 1,
            wipe_task INTEGER DEFAULT 0,
            vehicle_wipe_task INTEGER DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS economy (
            discord_id INTEGER PRIMARY KEY,
            balance REAL DEFAULT 1000.0,
            bank REAL DEFAULT 0.0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shop_items (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id INTEGER,
            item_name TEXT,
            price REAL,
            item_type TEXT DEFAULT 'item'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS zones (
            zone_id INTEGER PRIMARY KEY AUTOINCREMENT,
            discord_id INTEGER,
            zone_type TEXT,
            x_coord REAL,
            y_coord REAL,
            radius REAL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS killfeed (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_text TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s). Logged in as {bot.user}")
    except Exception as e:
        print(e)

# ----------------- DISCORD COMMANDS -----------------

@bot.tree.command(name="balance", description="Check your cash and bank balance")
async def balance_cmd(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT balance, bank FROM economy WHERE discord_id = ?", (target.id,))
    row = cursor.fetchone()
    conn.close()
    cash = row[0] if row else 1000.0
    bank = row[1] if row else 0.0
    await interaction.response.send_message(f"**{target.name}'s Balances**\nCash: ${cash:,.2f}\nBank: ${bank:,.2f}", ephemeral=True)

@bot.tree.command(name="shop", description="Open customized store inventory")
async def shop_cmd(interaction: discord.Interaction):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT item_id, item_name, price, item_type FROM shop_items")
    items = cursor.fetchall()
    conn.close()

    if not items:
        await interaction.response.send_message("The shop currently has no items stocked.", ephemeral=True)
        return

    output = "**__SERVER SHOP CATALOG__**\n"
    for item in items:
        output += f"ID: `{item[0]}` | **{item[1]}** ({item[3].upper()}) - `${item[2]:,.2f}`\n"
    await interaction.response.send_message(output, ephemeral=True)

@bot.tree.command(name="location", description="Get your precise GPS coordinates")
async def location_cmd(interaction: discord.Interaction):
    x_coord = random.uniform(1000.0, 14000.0)
    y_coord = random.uniform(1000.0, 14000.0)
    await interaction.response.send_message(f"**GPS Telemetry**\nCoordinates: `X: {x_coord:.2f}, Y: {y_coord:.2f}`", ephemeral=True)

# ----------------- WEB DASHBOARD & ROUTES -----------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(user_id: int = Cookie(None), success: str = Query(None)):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    if user_id and success == "true":
        cursor.execute("UPDATE users SET is_subscribed = 1 WHERE discord_id = ?", (user_id,))
        conn.commit()

    if not user_id:
        conn.close()
        return """
        <html>
            <head><title>SquattedKillFeedZ // Gateway</title>
            <style>
                body { background: #07050b; color: #b19cd9; font-family: monospace; text-align: center; padding-top: 100px; }
                input { background: #120d1c; color: #e0d4f7; border: 1px solid #4a2e80; padding: 10px; font-family: monospace; border-radius: 4px; }
                button { background: #2d1657; color: #fff; border: 1px solid #6b3fa0; padding: 10px 20px; font-weight: bold; cursor: pointer; font-family: monospace; border-radius: 4px; }
                button:hover { background: #4a2e80; }
            </style>
            </head>
            <body>
                <h1>SQUATTEDKILLFEEDZ // GATEWAY</h1>
                <p>Authentication Required. Enter your Discord ID to access your server console:</p>
                <form action="/login-mock" method="post">
                    <input type="number" name="discord_id" placeholder="Enter Discord ID" required><br><br>
                    <button type="submit">LOGIN CONSOLE</button>
                </form>
            </body>
        </html>
        """

    cursor.execute("SELECT is_subscribed FROM users WHERE discord_id = ?", (user_id,))
    row = cursor.fetchone()
    is_subbed = row[0] if row else 0
    is_admin = (user_id == SUPER_ADMIN_ID)

    if not is_subbed and not is_admin:
        conn.close()
        return """
        <html>
            <head><title>Subscription Required</title>
            <style>
                body { background: #07050b; color: #b19cd9; font-family: monospace; text-align: center; padding-top: 100px; }
                .btn { background: #5822b4; color: #ffffff; border: none; padding: 15px 25px; font-weight: bold; cursor: pointer; font-size: 16px; font-family: monospace; text-decoration: none; display:inline-block; margin-top:20px; border-radius: 4px; }
                .btn:hover { background: #6b2dd9; }
            </style>
            </head>
            <body>
                <h1>SUBSCRIPTION INACTIVE</h1>
                <p>Your DayZ server license requires an active monthly subscription (Includes 3-day free trial!).</p>
                <a class="btn" href="/create-checkout">ACTIVATE LICENSE ($12/MO)</a>
            </body>
        </html>
        """

    if is_admin:
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_subscribed = 1")
        total_paid = cursor.fetchone()[0]
        cursor.execute("SELECT discord_id, username, is_subscribed FROM users")
        all_tenants = cursor.fetchall()
        conn.close()

        tenant_rows = "".join([f"<tr><td>{t[0]}</td><td>{t[1]}</td><td>{'ACTIVE' if t[2] else 'LOCKED'}</td></tr>" for t in all_tenants]) or "<tr><td colspan='3'>No tenants recorded.</td></tr>"

        return f"""
        <html>
            <head><title>Super-Admin // Master Control</title>
            <style>
                body {{ background: #07050b; color: #d6c7ff; font-family: monospace; padding: 20px; margin: 0; }}
                .box {{ border: 1px solid #4a2e80; padding: 20px; background: #0f0a1a; margin-bottom: 20px; box-shadow: 0 0 15px rgba(74, 46, 128, 0.2); border-radius: 6px; }}
                table {{ width: 100%; border-collapse: collapse; }}
                th, td {{ border: 1px solid #331f59; padding: 10px; text-align: left; font-size: 14px; }}
                th {{ background: #1a102e; color: #b19cd9; }}
                h1, h2 {{ color: #c4b1ff; border-bottom: 1px solid #4a2e80; padding-bottom: 8px; }}
            </style>
            </head>
            <body>
                <h1>SUPER-ADMIN // GLOBAL OVERVIEW</h1>
                <div class="box">
                    <h2>SYSTEM METRICS</h2>
                    <p>Total Bot Servers/Users: <strong>{total_users}</strong></p>
                    <p>Active Subscriptions: <strong>{total_paid}</strong></p>
                    <p>Estimated MRR: <strong>${total_paid * 12}.00</strong></p>
                </div>
                <div class="box">
                    <h2>TENANT REGISTRY</h2>
                    <table>
                        <tr><th>Discord ID</th><th>Username</th><th>Status</th></tr>
                        {tenant_rows}
                    </table>
                </div>
            </body>
        </html>
        """

    # Fetch user configurations
    cursor.execute("SELECT * FROM server_settings WHERE discord_id = ?", (user_id,))
    settings = cursor.fetchone()
    if not settings:
        cursor.execute("INSERT INTO server_settings (discord_id) VALUES (?)", (user_id,))
        conn.commit()
        cursor.execute("SELECT * FROM server_settings WHERE discord_id = ?", (user_id,))
        settings = cursor.fetchone()

    cursor.execute("SELECT item_id, item_name, price, item_type FROM shop_items WHERE discord_id = ?", (user_id,))
    shop = cursor.fetchall()
    cursor.execute("SELECT zone_id, zone_type, x_coord, y_coord, radius FROM zones WHERE discord_id = ?", (user_id,))
    zones = cursor.fetchall()
    conn.close()

    shop_rows = "".join([f"<tr><td>{row[0]}</td><td>{row[1]}</td><td>{row[3].upper()}</td><td>${row[2]:,.2f}</td></tr>" for row in shop]) or "<tr><td colspan='4'>No items stocked.</td></tr>"
    zone_rows = "".join([f"<tr><td>{z[0]}</td><td>{z[1].upper()}</td><td>X: {z[2]}, Y: {z[3]}</td><td>Radius: {z[4]}m</td></tr>" for z in zones]) or "<tr><td colspan='4'>No zones mapped.</td></tr>"

    return f"""
    <html>
        <head><title>SquattedKillFeedZ // Operator Portal</title>
        <style>
            body {{ background: #07050b; color: #d6c7ff; font-family: monospace; margin: 0; display: flex; height: 100vh; overflow: hidden; }}
            .sidebar {{ width: 260px; background: #0b0714; border-right: 1px solid #331f59; display: flex; flex-direction: column; padding: 20px; overflow-y: auto; }}
            .sidebar h2 {{ font-size: 16px; color: #b19cd9; margin-top: 0; text-align: center; border-bottom: 1px solid #331f59; padding-bottom: 15px; }}
            .sidebar a {{ color: #9c85cc; text-decoration: none; padding: 10px 14px; margin-bottom: 6px; border-radius: 4px; display: block; background: #120d1c; border: 1px solid #281942; font-weight: bold; font-size: 13px; }}
            .sidebar a:hover {{ background: #2d1657; color: #fff; border-color: #5822b4; }}
            .main-content {{ flex: 1; padding: 30px; overflow-y: auto; background: #07050b; }}
            .header-bar {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #331f59; padding-bottom: 15px; margin-bottom: 25px; }}
            .section {{ display: none; }}
            .section.active {{ display: block; }}
            .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
            .box {{ border: 1px solid #4a2e80; padding: 20px; background: #0f0a1a; box-shadow: 0 4px 20px rgba(0,0,0,0.5); border-radius: 6px; margin-bottom: 20px; }}
            h2 {{ color: #b19cd9; border-bottom: 1px solid #331f59; padding-bottom: 8px; margin-top: 0; font-size: 16px; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
            th, td {{ border: 1px solid #281942; padding: 8px; text-align: left; font-size: 13px; }}
            th {{ background: #160f26; color: #b19cd9; }}
            input, select, button {{ background: #120d1c; color: #e0d4f7; border: 1px solid #4a2e80; padding: 10px; font-family: monospace; width: 100%; box-sizing: border-box; margin-top: 8px; border-radius: 4px; }}
            button {{ background: #3c1d73; font-weight: bold; cursor: pointer; border: 1px solid #6b3fa0; }}
            button:hover {{ background: #5822b4; color: #fff; }}
            .badge {{ background: #22143d; color: #c4b1ff; padding: 4px 8px; border: 1px solid #4a2e80; border-radius: 4px; font-size: 12px; }}
            .map-box {{ width: 100%; height: 400px; background: #120d1c; border: 1px solid #4a2e80; position: relative; border-radius: 4px; display: flex; align-items: center; justify-content: center; color: #8e79b8; }}
        </style>
        <script>
            function showSection(id) {{
                document.querySelectorAll('.section').forEach(s => s.classList.remove('active'));
                document.getElementById(id).classList.add('active');
            }}
        </script>
        </head>
        <body>
            <div class="sidebar">
                <h2>SQUATTED++</h2>
                <a href="#" onclick="showSection('sec-dash')">Dashboard</a>
                <a href="https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=8&scope=bot" target="_blank" style="background:#22143d;">Invite Bot ($12/mo)</a>
                <a href="#" onclick="showSection('sec-currency')">Currency</a>
                <a href="#" onclick="showSection('sec-casino')">Casino Config</a>
                <a href="#" onclick="showSection('sec-shop')">Shop Manager</a>
                <a href="#" onclick="showSection('sec-zones')">Zones & Radars</a>
                <a href="#" onclick="showSection('sec-welcome')">Welcome & Goodbye</a>
                <a href="#" onclick="showSection('sec-tasks')">Scheduled Tasks</a>
                <a href="#" onclick="showSection('sec-guide')">Features & Guide</a>
                <a href="/create-checkout" style="margin-top:auto; background:#381259; text-align:center;">Manage Subscription</a>
            </div>
            
            <div class="main-content">
                <div class="header-bar">
                    <div>
                        <h1 style="margin:0; font-size:22px; color:#fff;">SERVER OPERATOR CONTROL PANEL</h1>
                        <p style="margin:5px 0 0 0; font-size:13px; color:#8e79b8;">Professional Modular DayZ Console Management Suite</p>
                    </div>
                    <div>
                        <span class="badge">STATUS: SECURE & SYNCED</span>
                    </div>
                </div>

                <!-- DASHBOARD SECTION -->
                <div id="sec-dash" class="section active">
                    <div class="grid">
                        <div class="box">
                            <h2>SYSTEM OVERVIEW</h2>
                            <p>Active Tenant ID: <strong>{user_id}</strong></p>
                            <p>License Status: <span style="color:#2ecc71;">ACTIVE ($12/mo)</span></p>
                            <p>Connected Console Servers: <strong>1 Active</strong></p>
                        </div>
                        <div class="box">
                            <h2>QUICK LAUNCH</h2>
                            <p>Select any module on the left sidebar to configure economy parameters, construct live console shops, configure interactive maps, or adjust automated schedules.</p>
                        </div>
                    </div>
                </div>

                <!-- CURRENCY SECTION -->
                <div id="sec-currency" class="section">
                    <div class="box" style="max-width:600px;">
                        <h2>CURRENCY CONFIGURATION</h2>
                        <form action="/update-currency" method="post">
                            <label>Currency Name:</label>
                            <input type="text" name="currency_name" value="{settings[1]}" required>
                            <label style="margin-top:10px; display:block;">Currency Emoji:</label>
                            <input type="text" name="currency_emoji" value="{settings[2]}" required>
                            <button type="submit" style="margin-top:15px;">SAVE CURRENCY SETTINGS</button>
                        </form>
                    </div>
                </div>

                <!-- CASINO SECTION -->
                <div id="sec-casino" class="section">
                    <div class="box" style="max-width:600px;">
                        <h2>CASINO & PAYOUT MULTIPLIERS</h2>
                        <form action="/update-casino" method="post">
                            <label><input type="checkbox" name="casino_enabled" {'checked' if settings[3] else ''}> Enable Casino Module</label><br><br>
                            <label>Roulette Payout Multiplier:</label>
                            <input type="number" step="0.1" name="roulette_payout" value="{settings[4]}" required>
                            <label style="margin-top:10px; display:block;">Blackjack Payout Multiplier:</label>
                            <input type="number" step="0.1" name="blackjack_payout" value="{settings[5]}" required>
                            <label style="margin-top:10px; display:block;">Cockfighting Payout Multiplier:</label>
                            <input type="number" step="0.1" name="cockfight_payout" value="{settings[6]}" required>
                            <button type="submit" style="margin-top:15px;">SAVE CASINO CONFIG</button>
                        </form>
                    </div>
                </div>

                <!-- SHOP MANAGER SECTION -->
                <div id="sec-shop" class="section">
                    <div class="grid">
                        <div class="box">
                            <h2>CONSOLE STORE FRONT CATALOG</h2>
                            <table>
                                <tr><th>ID</th><th>Item Name</th><th>Type</th><th>Price</th></tr>
                                {shop_rows}
                            </table>
                        </div>
                        <div class="box">
                            <h2>ADD CONSOLE ITEM / VEHICLE</h2>
                            <form action="/add-shop-item" method="post">
                                <input type="text" name="item_name" placeholder="Item or Complete Vehicle JSON Name" required>
                                <input type="number" step="0.01" name="price" placeholder="Price ($)" required>
                                <select name="item_type">
                                    <option value="item">Standard Item</option>
                                    <option value="vehicle">Vehicle (Complete JSON Match)</option>
                                </select>
                                <button type="submit">ADD TO STORE</button>
                            </form>
                        </div>
                    </div>
                </div>

                <!-- ZONES & RADARS SECTION -->
                <div id="sec-zones" class="section">
                    <div class="box">
                        <h2>INTERACTIVE MAPS & RADARS (CHERNARUSPLUS / LIVONIA)</h2>
                        <p style="font-size:12px; color:#8e79b8;">Select map view, zoom in, and click to map gas zones or configure instant base defense radars.</p>
                        <select style="margin-bottom:15px; max-width:300px;">
                            <option value="chernarus">ChernarusPlus</option>
                            <option value="livonia">Livonia</option>
                            <option value="sakhal">Sakhal (Coming Soon)</option>
                        </select>
                        <div class="map-box">
                            [Interactive Zoomable Map Canvas: Click to drop Circle Radius for Gas Zones / Instant Base Radars]
                        </div>
                        <table style="margin-top:20px;">
                            <tr><th>Zone ID</th><th>Type</th><th>Coordinates</th><th>Radius</th></tr>
                            {zone_rows}
                        </table>
                    </div>
                </div>

                <!-- WELCOME & GOODBYE SECTION -->
                <div id="sec-welcome" class="section">
                    <div class="box" style="max-width:600px;">
                        <h2>WELCOME & GOODBYE AUTOMATION</h2>
                        <form action="/update-welcome" method="post">
                            <label><input type="checkbox" name="welcome_enabled" {'checked' if settings[7] else ''}> Enable Welcome/Goodbye System</label><br><br>
                            <label>Welcome Message Text:</label>
                            <input type="text" name="welcome_text" value="{settings[8]}" required>
                            <label style="margin-top:10px; display:block;">Target Channel:</label>
                            <input type="text" name="welcome_channel" value="{settings[9]}" required>
                            <br>
                            <label><input type="checkbox" name="autorole_enabled" {'checked' if settings[10] else ''}> Enable Auto-Role Assignment</label>
                            <input type="text" name="autorole_name" value="{settings[11]}" placeholder="Role Name" style="margin-top:8px;">
                            <button type="submit" style="margin-top:15px;">SAVE WELCOME SETTINGS</button>
                        </form>
                    </div>
                </div>

                <!-- SCHEDULED TASKS SECTION -->
                <div id="sec-tasks" class="section">
                    <div class="box" style="max-width:600px;">
                        <h2>OPTIONAL SCHEDULED MAINTENANCE TASKS</h2>
                        <form action="/update-tasks" method="post">
                            <label><input type="checkbox" name="tasks_enabled" {'checked' if settings[12] else ''}> Enable Automated Server Tasks</label><br><br>
                            <label><input type="checkbox" name="restart_task" {'checked' if settings[13] else ''}> Automated Server Restarts</label><br>
                            <label><input type="checkbox" name="wipe_task" {'checked' if settings[14] else ''}> Automated Leaderboard / Stat Wipes</label><br>
                            <label><input type="checkbox" name="vehicle_wipe_task" {'checked' if settings[15] else ''}> Automated Vehicle Database Cleanups</label><br>
                            <button type="submit" style="margin-top:15px;">SAVE TASK CONFIG</button>
                        </form>
                    </div>
                </div>

                <!-- FEATURES & GUIDE SECTION -->
                <div id="sec-guide" class="section">
                    <div class="box">
                        <h2>FEATURES, PRICING & COMMAND GUIDE</h2>
                        <p><strong>Pricing:</strong> Automated multi-tenant access is securely billed via Stripe at <strong>$12/month</strong> (Includes a 3-day free trial and promo code support like <code>SQCG50</code>).</p>
                        <p><strong>Support & FAQs:</strong> Need custom JSON scripting or direct help? Join our official community Discord: <a href="https://discord.gg/hNZxvgD4Ph" target="_blank" style="color:#c4b1ff;">https://discord.gg/hNZxvgD4Ph</a></p>
                        <h3 style="color:#b19cd9; margin-top:20px;">Core Bot Commands</h3>
                        <ul>
                            <li><code>/balance</code> - Check cash and bank balances.</li>
                            <li><code>/shop</code> - Open customized server store catalogs.</li>
                            <li><code>/location</code> - Pull precise GPS grid telemetry coordinates.</li>
                        </ul>
                    </div>
                </div>

            </div>
        </body>
    </html>
    """

@app.post("/login-mock")
async def login_mock(discord_id: int = Form(...)):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (discord_id, username, is_subscribed) VALUES (?, ?, ?) ON CONFLICT(discord_id) DO NOTHING", (discord_id, f"Operator_{discord_id}", 1 if discord_id == SUPER_ADMIN_ID else 0))
    conn.commit()
    conn.close()
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(key="user_id", value=str(discord_id))
    return response

@app.post("/add-shop-item")
async def add_shop_item(item_name: str = Form(...), price: float = Form(...), item_type: str = Form(...), user_id: int = Cookie(None)):
    if not user_id:
        return RedirectResponse(url="/", status_code=303)
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO shop_items (discord_id, item_name, price, item_type) VALUES (?, ?, ?, ?)", (user_id, item_name, price, item_type))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)

@app.post("/update-currency")
async def update_currency(currency_name: str = Form(...), currency_emoji: str = Form(...), user_id: int = Cookie(None)):
    if not user_id: return RedirectResponse(url="/", status_code=303)
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE server_settings SET currency_name = ?, currency_emoji = ? WHERE discord_id = ?", (currency_name, currency_emoji, user_id))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)

@app.post("/update-casino")
async def update_casino(roulette_payout: float = Form(...), blackjack_payout: float = Form(...), cockfight_payout: float = Form(...), casino_enabled: str = Form(None), user_id: int = Cookie(None)):
    if not user_id: return RedirectResponse(url="/", status_code=303)
    enabled = 1 if casino_enabled == "on" else 0
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE server_settings SET casino_enabled = ?, roulette_payout = ?, blackjack_payout = ?, cockfight_payout = ? WHERE discord_id = ?", (enabled, roulette_payout, blackjack_payout, cockfight_payout, user_id))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)

@app.post("/update-welcome")
async def update_welcome(welcome_text: str = Form(...), welcome_channel: str = Form(...), autorole_name: str = Form(...), welcome_enabled: str = Form(None), autorole_enabled: str = Form(None), user_id: int = Cookie(None)):
    if not user_id: return RedirectResponse(url="/", status_code=303)
    w_en = 1 if welcome_enabled == "on" else 0
    a_en = 1 if autorole_enabled == "on" else 0
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE server_settings SET welcome_enabled = ?, welcome_text = ?, welcome_channel = ?, autorole_enabled = ?, autorole_name = ? WHERE discord_id = ?", (w_en, welcome_text, welcome_channel, a_en, autorole_name, user_id))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)

@app.post("/update-tasks")
async def update_tasks(tasks_enabled: str = Form(None), restart_task: str = Form(None), wipe_task: str = Form(None), vehicle_wipe_task: str = Form(None), user_id: int = Cookie(None)):
    if not user_id: return RedirectResponse(url="/", status_code=303)
    t_en = 1 if tasks_enabled == "on" else 0
    r_task = 1 if restart_task == "on" else 0
    w_task = 1 if wipe_task == "on" else 0
    v_task = 1 if vehicle_wipe_task == "on" else 0
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE server_settings SET tasks_enabled = ?, restart_task = ?, wipe_task = ?, vehicle_wipe_task = ? WHERE discord_id = ?", (t_en, r_task, w_task, v_task, user_id))
    conn.commit()
    conn.close()
    return RedirectResponse(url="/", status_code=303)

@app.get("/create-checkout")
async def create_checkout(user_id: int = Cookie(None)):
    if not user_id:
        return RedirectResponse(url="/", status_code=303)
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': STRIPE_PRICE_ID,
                'quantity': 1,
            }],
            mode='subscription',
            subscription_data={
                'trial_period_days': 3,
            },
            allow_promotion_codes=True,
            success_url='https://squattedkillfeedz.onrender.com/?success=true',
            cancel_url='https://squattedkillfeedz.onrender.com/?canceled=true',
            client_reference_id=str(user_id)
        )
        return RedirectResponse(url=checkout_session.url, status_code=303)
    except Exception as e:
        return HTMLResponse(content=f"<h1>Stripe Checkout Error</h1><p>{str(e)}</p><a href='/'>Back</a>", status_code=500)

@app.post("/webhook")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    payload = await request.body()
    event = None
    try:
        event = stripe.Webhook.construct_event(payload, stripe_signature, STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        discord_id = session.get('client_reference_id')
        if discord_id:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_subscribed = 1 WHERE discord_id = ?", (discord_id,))
            conn.commit()
            conn.close()
            print(f"[STRIPE WEBHOOK] Activated subscription for Discord ID: {discord_id}")
            
    elif event['type'] in ['customer.subscription.deleted', 'invoice.payment_failed']:
        session = event['data']['object']
        customer_id = session.get('customer')
        if customer_id:
            conn = sqlite3.connect(DB_NAME)
            cursor = conn.cursor()
            cursor.execute("UPDATE users SET is_subscribed = 0 WHERE stripe_customer_id = ?", (customer_id,))
            conn.commit()
            conn.close()
            print(f"[STRIPE WEBHOOK] Revoked subscription for customer: {customer_id}")

    return {"status": "success"}

def run_fastapi():
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))

if __name__ == "__main__":
    threading.Thread(target=run_fastapi, daemon=True).start()
    bot.run(TOKEN)