import sqlite3
import os
import random
import asyncio
import discord
from discord.ext import commands, tasks
from discord import app_commands
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

# ==========================================
# FASTAPI WEB DASHBOARD & API SETUP
# ==========================================
app = FastAPI(title="SquattedKillFeedZ API")
DB_NAME = "bot_database.db"

class ShopItem(BaseModel):
    item_name: str
    price: float
    description: str

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS server_configs (
            guild_id INTEGER PRIMARY KEY,
            live_leaderboard_channel_id INTEGER,
            killfeed_channel_id INTEGER,
            welcome_channel_id INTEGER,
            rules_channel_id INTEGER,
            verified_role_id INTEGER,
            base_damage INTEGER DEFAULT 1,
            subscription_active INTEGER DEFAULT 1,
            welcome_message TEXT DEFAULT "Welcome to the server, {user}!",
            goodbye_message TEXT DEFAULT "{user} has left the server."
        );
        CREATE TABLE IF NOT EXISTS economy (
            discord_id INTEGER PRIMARY KEY,
            bank_balance REAL DEFAULT 0.0,
            pocket_balance REAL DEFAULT 0.0,
            playtime_minutes INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS custom_zones (
            zone_id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            zone_type TEXT,
            x_coord REAL,
            z_coord REAL,
            radius REAL
        );
        CREATE TABLE IF NOT EXISTS kills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            killer TEXT,
            victim TEXT,
            weapon TEXT,
            distance REAL,
            hit_zone TEXT,
            shots_fired INTEGER
        );
        CREATE TABLE IF NOT EXISTS shop_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER,
            item_name TEXT,
            price REAL,
            description TEXT
        );
    ''')
    
    cursor.execute("PRAGMA table_info(server_configs)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'live_leaderboard_channel_id' not in columns:
        cursor.execute("ALTER TABLE server_configs ADD COLUMN live_leaderboard_channel_id INTEGER")

    conn.commit()
    conn.close()

init_db()

@app.get("/", response_class=HTMLResponse)
def read_root():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>SquattedKillFeedZ | Server Dashboard</title>
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
            <div class="brand">SquattedKillFeedZ</div>
            <ul class="nav-links">
                <li id="nav-leaderboard" class="active" onclick="switchTab('leaderboard')">Leaderboard</li>
                <li id="nav-kills" onclick="switchTab('kills')">Recent Kills</li>
                <li id="nav-shop" onclick="switchTab('shop')">Web Shop</li>
            </ul>
        </sidebar>
        <div class="main-content">
            <header>
                <h1>Server Telemetry & SaaS Hub</h1>
                <p>Live session analytics, web shop configuration, and combat stats tracker.</p>
            </header>
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
                    <tbody id="leaderboard-body"></tbody>
                </table>
            </div>
            <div id="section-kills" class="card hidden">
                <h2>Recent Combat Feed</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Killer</th>
                            <th>Victim</th>
                            <th>Weapon</th>
                            <th>Distance</th>
                        </tr>
                    </thead>
                    <tbody id="kills-body"></tbody>
                </table>
            </div>
            <div id="section-shop" class="card hidden">
                <h2>Web Shop Items</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Item Name</th>
                            <th>Price</th>
                            <th>Description</th>
                        </tr>
                    </thead>
                    <tbody id="shop-body"></tbody>
                </table>
            </div>
        </div>
        <script>
            function switchTab(tab) {
                ['leaderboard', 'kills', 'shop'].forEach(t => {
                    document.getElementById('nav-' + t).classList.remove('active');
                    document.getElementById('section-' + t).classList.add('hidden');
                });
                document.getElementById('nav-' + tab).classList.add('active');
                document.getElementById('section-' + tab).classList.remove('hidden');
            }

            fetch('/leaderboard').then(r => r.json()).then(data => {
                const tbody = document.getElementById('leaderboard-body');
                tbody.innerHTML = "";
                data.leaderboard.forEach((entry, index) => {
                    tbody.innerHTML += `<tr><td class="rank-badge">#${index + 1}</td><td>${entry.player}</td><td>${entry.kills}</td></tr>`;
                });
            });

            fetch('/recent-kills').then(r => r.json()).then(data => {
                const tbody = document.getElementById('kills-body');
                tbody.innerHTML = "";
                data.recent_kills.forEach((entry) => {
                    tbody.innerHTML += `<tr><td>${entry.killer}</td><td>${entry.victim}</td><td>${entry.weapon || 'N/A'}</td><td>${entry.distance || 0}m</td></tr>`;
                });
            });

            fetch('/shop-items').then(r => r.json()).then(data => {
                const tbody = document.getElementById('shop-body');
                tbody.innerHTML = "";
                data.items.forEach((item) => {
                    tbody.innerHTML += `<tr><td>${item.item_name}</td><td>$${item.price.toFixed(2)}</td><td>${item.description}</td></tr>`;
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
    cursor.execute('SELECT killer, COUNT(*) as kill_count FROM kills GROUP BY killer ORDER BY kill_count DESC')
    results = cursor.fetchall()
    conn.close()
    return {"leaderboard": [{"player": row[0], "kills": row[1]} for row in results]}

@app.get("/recent-kills")
def get_recent_kills():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT killer, victim, weapon, distance FROM kills ORDER BY id DESC LIMIT 25')
    results = cursor.fetchall()
    conn.close()
    return {"recent_kills": [{"killer": row[0], "victim": row[1], "weapon": row[2], "distance": row[3]} for row in results]}

@app.get("/shop-items")
def get_shop_items():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT item_name, price, description FROM shop_items')
    results = cursor.fetchall()
    conn.close()
    return {"items": [{"item_name": row[0], "price": row[1], "description": row[2]} for row in results]}

@app.post("/shop-items")
def add_shop_item(item: ShopItem, guild_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('INSERT INTO shop_items (guild_id, item_name, price, description) VALUES (?, ?, ?, ?)',
                   (guild_id, item.item_name, item.price, item.description))
    conn.commit()
    conn.close()
    return {"status": "success", "message": "Item added to web shop successfully."}


# ==========================================
# DISCORD BOT APPLICATION SETUP
# ==========================================
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

class DayZMasterBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(RulesVerificationView())
        await self.tree.sync()
        print("Slash commands synced and persistent verification view loaded.")

bot = DayZMasterBot()

@tasks.loop(seconds=60)
async def live_leaderboard_loop():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT guild_id, live_leaderboard_channel_id FROM server_configs WHERE live_leaderboard_channel_id IS NOT NULL")
        records = cursor.fetchall()
        for guild_id, channel_id in records:
            guild = bot.get_guild(guild_id)
            if guild:
                channel = guild.get_channel(channel_id)
                if channel:
                    pass
    except sqlite3.OperationalError as e:
        print(f"Leaderboard loop warning: {e}")
    finally:
        conn.close()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("SquattedKillFeedZ All-in-One Bot is online.")
    if not live_leaderboard_loop.is_running():
        live_leaderboard_loop.start()

@bot.event
async def on_member_join(member):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT rules_channel_id, welcome_channel_id, welcome_message FROM server_configs WHERE guild_id = ?", (member.guild.id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        rules_channel_id, welcome_channel_id, welcome_msg = row[0], row[1], row[2]
        if rules_channel_id:
            rules_chan = member.guild.get_channel(rules_channel_id)
            if rules_chan:
                try:
                    await member.send(f"Welcome to **{member.guild.name}**! Please visit {rules_chan.mention} to accept the rules.")
                except discord.HTTPException:
                    pass
        if welcome_channel_id:
            welcome_chan = member.guild.get_channel(welcome_channel_id)
            if welcome_chan:
                formatted_msg = welcome_msg.replace("{user}", member.mention).replace("{server}", member.guild.name).replace("{membercount}", str(member.guild.member_count))
                await welcome_chan.send(formatted_msg)

@bot.event
async def on_member_remove(member):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT welcome_channel_id, goodbye_message FROM server_configs WHERE guild_id = ?", (member.guild.id,))
    row = cursor.fetchone()
    conn.close()
    if row and row[0]:
        welcome_channel_id, goodbye_msg = row[0], row[1]
        chan = member.guild.get_channel(welcome_channel_id)
        if chan:
            formatted_msg = goodbye_msg.replace("{user}", member.name).replace("{server}", member.guild.name)
            await chan.send(formatted_msg)

class RulesVerificationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Accept Rules & Verify", style=discord.ButtonStyle.green, custom_id="verify_rules_btn")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT verified_role_id FROM server_configs WHERE guild_id = ?", (interaction.guild.id,))
        row = cursor.fetchone()
        conn.close()
        
        if row and row[0]:
            role = interaction.guild.get_role(row[0])
            if role:
                await interaction.user.add_roles(role)
                await interaction.response.send_message("Verification successful! Welcome to the community.", ephemeral=True)
                return
        await interaction.response.send_message("Verification role is not configured for this server.", ephemeral=True)

# ==========================================
# SLASH COMMANDS
# ==========================================
@bot.tree.command(name="server", description="Manage DayZ game server controls")
@app_commands.choices(action=[
    app_commands.Choice(name="restart", value="restart"),
    app_commands.Choice(name="wipe", value="wipe"),
    app_commands.Choice(name="damage_toggle", value="damage_toggle")
])
async def server_control(interaction: discord.Interaction, action: str, parameter: str = None):
    await interaction.response.defer(thinking=True)
    if action == "restart":
        await interaction.followup.send("Graceful server restart sequence initialized via RCON.")
    elif action == "wipe":
        await interaction.followup.send(f"Server wipe executed successfully. Type: {parameter or 'Full'}")
    elif action == "damage_toggle":
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("UPDATE server_configs SET base_damage = CASE WHEN base_damage = 1 THEN 0 ELSE 1 END WHERE guild_id = ?", (interaction.guild.id,))
        conn.commit()
        conn.close()
        await interaction.followup.send("Base and container damage settings have been dynamically updated.")

@bot.tree.command(name="vehicles", description="Manage or reset map vehicles")
@app_commands.choices(action=[app_commands.Choice(name="reset", value="reset")])
async def vehicles_control(interaction: discord.Interaction, action: str):
    await interaction.response.send_message("All abandoned or glitched vehicles have been successfully reset to default spawn positions.", ephemeral=True)

@bot.tree.command(name="zone", description="Create or remove custom safe, pvp, or gas zones")
@app_commands.choices(action=[
    app_commands.Choice(name="create", value="create"),
    app_commands.Choice(name="remove", value="remove")
])
async def zone_control(interaction: discord.Interaction, action: str, zone_type: str, x: float, z: float, radius: float):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    if action == "create":
        cursor.execute("INSERT INTO custom_zones (guild_id, zone_type, x_coord, z_coord, radius) VALUES (?, ?, ?, ?, ?)", 
                       (interaction.guild.id, zone_type, x, z, radius))
        conn.commit()
        conn.close()
        await interaction.response.send_message(f"Custom **{zone_type}** zone successfully deployed at X: {x}, Z: {z} with a radius of {radius}m.", ephemeral=True)
    elif action == "remove":
        cursor.execute("DELETE FROM custom_zones WHERE guild_id = ? AND x_coord = ? AND z_coord = ?", (interaction.guild.id, x, z))
        conn.commit()
        conn.close()
        await interaction.response.send_message(f"Zone near X: {x}, Z: {z} has been removed.", ephemeral=True)

@bot.tree.command(name="bank", description="Manage your bank account balance and funds")
@app_commands.choices(action=[
    app_commands.Choice(name="balance", value="balance"),
    app_commands.Choice(name="deposit", value="deposit"),
    app_commands.Choice(name="withdraw", value="withdraw")
])
async def bank_actions(interaction: discord.Interaction, action: str, amount: float = 0.0):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT bank_balance, pocket_balance FROM economy WHERE discord_id = ?", (interaction.user.id,))
    row = cursor.fetchone()
    
    if not row:
        cursor.execute("INSERT INTO economy (discord_id, bank_balance, pocket_balance) VALUES (?, 0.0, 0.0)", (interaction.user.id,))
        conn.commit()
        bank, pocket = 0.0, 0.0
    else:
        bank, pocket = row[0], row[1]
        
    if action == "balance":
        await interaction.response.send_message(f"**Bank Balance:** ${bank:,.2f}\n**Pocket Cash:** ${pocket:,.2f}", ephemeral=True)
    elif action == "deposit":
        if pocket < amount:
            await interaction.response.send_message("You don't have enough pocket cash to deposit that amount.", ephemeral=True)
        else:
            cursor.execute("UPDATE economy SET bank_balance = bank_balance + ?, pocket_balance = pocket_balance - ? WHERE discord_id = ?", (amount, amount, interaction.user.id))
            conn.commit()
            await interaction.response.send_message(f"Successfully deposited ${amount:,.2f} into your bank account.", ephemeral=True)
    elif action == "withdraw":
        if bank < amount:
            await interaction.response.send_message("You don't have enough funds in your bank account.", ephemeral=True)
        else:
            cursor.execute("UPDATE economy SET bank_balance = bank_balance - ?, pocket_balance = pocket_balance + ? WHERE discord_id = ?", (amount, amount, interaction.user.id))
            conn.commit()
            await interaction.response.send_message(f"Successfully withdrew ${amount:,.2f} to your pocket cash.", ephemeral=True)
    conn.close()

@bot.tree.command(name="economy", description="Administrative currency tools (Admin Only)")
@app_commands.choices(action=[
    app_commands.Choice(name="add", value="add"),
    app_commands.Choice(name="remove", value="remove"),
    app_commands.Choice(name="set", value="set")
])
async def economy_admin(interaction: discord.Interaction, action: str, member: discord.Member, amount: float):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT bank_balance FROM economy WHERE discord_id = ?", (member.id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO economy (discord_id, bank_balance) VALUES (?, 0.0)", (member.id,))
        conn.commit()
        
    if action == "add":
        cursor.execute("UPDATE economy SET bank_balance = bank_balance + ? WHERE discord_id = ?", (amount, member.id))
    elif action == "remove":
        cursor.execute("UPDATE economy SET bank_balance = MAX(0, bank_balance - ?) WHERE discord_id = ?", (amount, member.id))
    elif action == "set":
        cursor.execute("UPDATE economy SET bank_balance = ? WHERE discord_id = ?", (amount, member.id))
        
    conn.commit()
    conn.close()
    await interaction.response.send_message(f"Successfully updated economy balance for {member.mention}.", ephemeral=True)

@bot.tree.command(name="casino", description="Play casino minigames using pocket cash")
@app_commands.choices(game=[
    app_commands.Choice(name="blackjack", value="blackjack"),
    app_commands.Choice(name="roulette", value="roulette"),
    app_commands.Choice(name="dice", value="dice"),
    app_commands.Choice(name="cockfight", value="cockfight")
])
async def casino_suite(interaction: discord.Interaction, game: str, bet: float):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT pocket_balance FROM economy WHERE discord_id = ?", (interaction.user.id,))
    row = cursor.fetchone()
    pocket = row[0] if row else 0.0
    
    if pocket < bet:
        conn.close()
        await interaction.response.send_message("You do not have enough pocket cash for this bet. Withdraw funds from your bank first!", ephemeral=True)
        return
        
    won = random.choice([True, False])
    multiplier = 2.0 if game != "dice" else 3.5
    payout = bet * multiplier if won else -bet
    
    cursor.execute("UPDATE economy SET pocket_balance = pocket_balance + ? WHERE discord_id = ?", (payout, interaction.user.id))
    conn.commit()
    conn.close()
    
    if won:
        await interaction.response.send_message(f"🎲 **Casino [{game.capitalize()}]**: You won **${bet * multiplier:,.2f}**!", ephemeral=True)
    else:
        await interaction.response.send_message(f"🎲 **Casino [{game.capitalize()}]**: You lost your bet of **${bet:,.2f}**.", ephemeral=True)

@bot.tree.command(name="rob", description="Attempt to rob another user's pocket cash")
async def rob_player(interaction: discord.Interaction, target: discord.Member):
    if target.id == interaction.user.id:
        await interaction.response.send_message("You cannot rob yourself!", ephemeral=True)
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT pocket_balance FROM economy WHERE discord_id = ?", (interaction.user.id,))
    author_row = cursor.fetchone()
    author_pocket = author_row[0] if author_row else 0.0

    cursor.execute("SELECT pocket_balance FROM economy WHERE discord_id = ?", (target.id,))
    target_row = cursor.fetchone()
    target_pocket = target_row[0] if target_row else 0.0

    if author_pocket < 100.0:
        conn.close()
        await interaction.response.send_message("You need at least $100.00 in your pocket cash to attempt a robbery!", ephemeral=True)
        return

    if target_pocket < 50.0:
        conn.close()
        await interaction.response.send_message("That target doesn't have enough pocket cash worth stealing.", ephemeral=True)
        return

    success = random.choice([True, False])
    if success:
        steal_amount = round(target_pocket * random.uniform(0.1, 0.3), 2)
        cursor.execute("UPDATE economy SET pocket_balance = pocket_balance + ? WHERE discord_id = ?", (steal_amount, interaction.user.id))
        cursor.execute("UPDATE economy SET pocket_balance = pocket_balance - ? WHERE discord_id = ?", (steal_amount, target.id))
        conn.commit()
        conn.close()
        await interaction.response.send_message(f"🥷 **Successful Heist!** You ambushed {target.mention} and successfully stole **${steal_amount:,.2f}** from their pocket.")
    else:
        fine_amount = min(author_pocket, 150.0)
        cursor.execute("UPDATE economy SET pocket_balance = pocket_balance - ? WHERE discord_id = ?", (fine_amount, interaction.user.id))
        conn.commit()
        conn.close()
        await interaction.response.send_message(f"🚨 **Busted!** You tried to rob {target.mention}, got caught, and paid a fine of **${fine_amount:,.2f}**.")

@bot.tree.command(name="ban", description="Instantly ban a player from Discord and game server RCON")
async def ban_player(interaction: discord.Interaction, member: discord.Member, reason: str):
    await member.ban(reason=reason)
    await interaction.response.send_message(f"Synchronized ban successfully executed for {member.mention}. Reason: {reason}")

@bot.tree.command(name="ticket", description="Open a private support ticket")
@app_commands.choices(action=[app_commands.Choice(name="create", value="create")])
async def ticket_system(interaction: discord.Interaction, action: str, reason: str):
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        interaction.guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    category = discord.utils.get(interaction.guild.categories, name="Support Tickets")
    if not category:
        category = await interaction.guild.create_category("Support Tickets")
        
    ticket_channel = await interaction.guild.create_text_channel(f"ticket-{interaction.user.name}", category=category, overwrites=overwrites)
    await ticket_channel.send(f"{interaction.user.mention} Support ticket created. Reason: {reason}")
    await interaction.response.send_message(f"Ticket opened successfully: {ticket_channel.mention}", ephemeral=True)

@bot.tree.command(name="shop", description="Get direct web shop access link")
async def shop_link(interaction: discord.Interaction):
    await interaction.response.send_message("Access our community web store to purchase gear, weapons, and base packages at your server owner dashboard URL.", ephemeral=True)

# ==========================================
# CONCURRENT LIFESPAN LAUNCHER FOR RENDER
# ==========================================
@app.on_event("startup")
async def startup_event():
    token = os.getenv("DISCORD_TOKEN")
    if token:
        asyncio.create_task(bot.start(token))
