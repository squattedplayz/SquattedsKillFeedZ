import os
import asyncio
import aiohttp
from aiohttp import web
import sqlite3
import discord
from discord.ext import commands, tasks
import stripe

# --- CONFIGURATION ---
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "sk_test_placeholder")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "your_bot_token_here")
NITRADO_API_TOKEN = os.getenv("NITRADO_API_TOKEN", "your_nitrado_token_here")
WEB_SERVER_HOST = "0.0.0.0"
WEB_SERVER_PORT = int(os.getenv("PORT", 8080))
PUBLIC_URL = os.getenv("PUBLIC_URL", f"http://localhost:{WEB_SERVER_PORT}")

MASTER_ADMIN_ID = 578271264779665438

# --- SQLITE DATABASE SETUP (100% Persistent & Multi-Tenant) ---
db_conn = sqlite3.connect("dayz_bot.db", check_same_thread=False)
db_cursor = db_conn.cursor()

db_cursor.executescript("""
CREATE TABLE IF NOT EXISTS subscriptions (
    guild_id INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS server_config (
    guild_id INTEGER,
    key TEXT,
    value TEXT,
    PRIMARY KEY (guild_id, key)
);

CREATE TABLE IF NOT EXISTS welcome_config (
    guild_id INTEGER PRIMARY KEY,
    channel TEXT,
    message TEXT
);

CREATE TABLE IF NOT EXISTS goodbye_config (
    guild_id INTEGER PRIMARY KEY,
    channel TEXT,
    message TEXT
);

CREATE TABLE IF NOT EXISTS shop_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    item_name TEXT,
    category TEXT,
    price INTEGER,
    command TEXT
);

CREATE TABLE IF NOT EXISTS player_balances (
    user_id INTEGER PRIMARY KEY,
    cash INTEGER,
    bank INTEGER
);

CREATE TABLE IF NOT EXISTS player_links (
    discord_id INTEGER,
    gamertag TEXT,
    PRIMARY KEY (discord_id, gamertag)
);

CREATE TABLE IF NOT EXISTS whitelist (
    guild_id INTEGER,
    gamertag TEXT
);

CREATE TABLE IF NOT EXISTS killfeed_config (
    guild_id INTEGER PRIMARY KEY,
    enabled INTEGER,
    channel_id INTEGER
);

CREATE TABLE IF NOT EXISTS leaderboard_config (
    guild_id INTEGER PRIMARY KEY,
    channel_id INTEGER
);

CREATE TABLE IF NOT EXISTS radar_config (
    guild_id INTEGER,
    radar_type TEXT,
    channel_id INTEGER,
    PRIMARY KEY (guild_id, radar_type)
);

CREATE TABLE IF NOT EXISTS zones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    map_name TEXT,
    zone_type TEXT,
    coords TEXT
);

CREATE TABLE IF NOT EXISTS bounties (
    target_id INTEGER PRIMARY KEY,
    amount INTEGER,
    setter_id INTEGER
);

CREATE TABLE IF NOT EXISTS ticket_stats (
    metric TEXT PRIMARY KEY,
    count INTEGER
);
""")

db_cursor.execute("INSERT OR IGNORE INTO ticket_stats (metric, count) VALUES ('open', 0)")
db_cursor.execute("INSERT OR IGNORE INTO ticket_stats (metric, count) VALUES ('closed', 5)")
db_conn.commit()


# --- ACCESS & SUBSCRIPTION CHECK ---
async def verify_server_access(interaction: discord.Interaction) -> bool:
    if interaction.user.id == MASTER_ADMIN_ID:
        return True
    try:
        owner = interaction.guild.owner or await interaction.guild.fetch_member(interaction.guild.owner_id)
        if owner.id == MASTER_ADMIN_ID:
            return True
    except Exception:
        if interaction.guild.owner_id == MASTER_ADMIN_ID:
            return True
            
    db_cursor.execute("SELECT 1 FROM subscriptions WHERE guild_id = ?", (interaction.guild.id,))
    if db_cursor.fetchone():
        return True
        
    await interaction.followup.send(
        "🔒 **Access Restricted:** This server requires an active subscription of **$12.99/month** to use bot commands.\n\nClick the button below to generate your secure in-Discord Stripe checkout link.",
        view=SubscriptionPayView(),
        ephemeral=True
    )
    return False

class SubscriptionPayView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="💳 Pay $12.99/mo via Stripe", style=discord.ButtonStyle.success, custom_id="stripe_pay_btn")
    async def pay_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        try:
            session = stripe.checkout.Session.create(
                payment_method_types=['card'],
                line_items=[{
                    'price_data': {
                        'currency': 'usd',
                        'product_data': {'name': f'SquattedSkillFeedZ Bot Subscription ({interaction.guild.name})'},
                        'unit_amount': 1299,
                        'recurring': {'interval': 'month'}
                    },
                    'quantity': 1,
                }],
                mode='subscription',
                success_url=f"https://discord.com/channels/{interaction.guild.id}",
                cancel_url=f"https://discord.com/channels/{interaction.guild.id}",
                client_reference_id=str(interaction.guild.id)
            )
            await interaction.followup.send(
                f"✅ **Stripe Checkout Ready:** Click the link below to complete your secure subscription payment:\n\n{session.url}",
                ephemeral=True
            )
        except Exception as e:
            await interaction.followup.send(f"❌ Error creating Stripe session: {str(e)}", ephemeral=True)


# --- BACKGROUND TASKS ---
@tasks.loop(seconds=15)
async def player_and_base_radar_loop():
    db_cursor.execute("SELECT guild_id, value FROM server_config WHERE key = 'service_id'")
    configs = db_cursor.fetchall()
    
    for guild_id, service_id in configs:
        db_cursor.execute("SELECT radar_type, channel_id FROM radar_config WHERE guild_id = ?", (guild_id,))
        radars = db_cursor.fetchall()
        if not radars:
            continue
            
        url = f"https://api.nitrado.net/services/{service_id}/gameservers/players"
        headers = {"Authorization": f"Bearer {NITRADO_API_TOKEN}"}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        players = data.get("data", {}).get("players", [])
                        
                        guild = bot.get_guild(guild_id)
                        if not guild:
                            continue
                            
                        for radar_type, channel_id in radars:
                            channel = guild.get_channel(channel_id)
                            if channel and players:
                                embed = discord.Embed(title=f"🚨 Live {radar_type} Update", color=0x7e22ce)
                                p_list = "\n".join([f"• {p.get('name', 'Unknown')} (Active)" for p in players[:10]])
                                embed.add_field(name="Tracked Entities", value=p_list or "No players online.", inline=False)
        except Exception:
            pass

@tasks.loop(hours=24)
async def daily_stats_aggregation_task():
    db_cursor.execute("UPDATE ticket_stats SET count = count WHERE metric = 'open'")
    db_conn.commit()


# --- DISCORD BOT SETUP & EVENTS ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    if not player_and_base_radar_loop.is_running():
        player_and_base_radar_loop.start()
    if not daily_stats_aggregation_task.is_running():
        daily_stats_aggregation_task.start()
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(e)


# --- INTERACTIVE ZOOMABLE WEB MAP & ZONE DRAWER ---
MAP_IMAGE_URLS = {
    "Chernarus": "https://static.wikia.nocookie.net/dayz_gamepedia/images/b/b3/ChernarusPlus_Map.jpg",
    "Livonia": "https://static.wikia.nocookie.net/dayz_gamepedia/images/5/5a/Livonia_Map.jpg",
    "Sakhal": "https://static.wikia.nocookie.net/dayz_gamepedia/images/d/d4/Sakhal_Map.jpg"
}

async def web_map_editor(request):
    guild_id = request.match_info.get('guild_id')
    map_name = request.query.get('map', 'Chernarus')
    zone_type = request.query.get('type', 'Base Radar')
    map_img = MAP_IMAGE_URLS.get(map_name, MAP_IMAGE_URLS["Chernarus"])

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>SquattedSkillFeedZ - Precision Map Drawer ({map_name})</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        body, html {{ margin: 0; padding: 0; height: 100%; font-family: sans-serif; background: #0f172a; color: #f8fafc; }}
        #map {{ height: calc(100vh - 70px); width: 100%; background: #1e293b; }}
        .header {{ height: 70px; background: #1e293b; display: flex; align-items: center; justify-content: space-between; padding: 0 20px; border-bottom: 2px solid #334155; }}
        .btn {{ background: #7e22ce; color: white; border: none; padding: 10px 20px; font-weight: bold; border-radius: 6px; cursor: pointer; }}
        .btn:hover {{ background: #9333ea; }}
        .select {{ padding: 8px; border-radius: 6px; background: #334155; color: white; border: 1px solid #475569; }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h2>🗺️ Map: <select id="mapSelect" class="select" onchange="changeMap()">
                <option value="Chernarus" {("selected" if map_name=="Chernarus" else "")}>Chernarus</option>
                <option value="Livonia" {("selected" if map_name=="Livonia" else "")}>Livonia</option>
                <option value="Sakhal" {("selected" if map_name=="Sakhal" else "")}>Sakhal</option>
            </select> | Type: <b>{zone_type}</b></h2>
        </div>
        <div>
            <button class="btn" onclick="saveZone()">💾 Save Drawn Zone</button>
        </div>
    </div>
    <div id="map"></div>

    <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
    <script>
        const map = L.map('map', {{
            crs: L.CRS.Simple,
            minZoom: -2,
            maxZoom: 6,
            zoomSnap: 0.25
        }});

        const bounds = [[0, 0], [4096, 4096]];
        const image = L.imageOverlay('{map_img}', bounds).addTo(map);
        map.fitBounds(bounds);

        let drawnRect = null;
        let startPoint = null;
        let isDrawing = false;

        map.on('click', function(e) {{
            if (!isDrawing) {{
                startPoint = e.latlng;
                isDrawing = true;
                if (drawnRect) map.removeLayer(drawnRect);
            }} else {{
                let endPoint = e.latlng;
                drawnRect = L.rectangle([startPoint, endPoint], {{color: "#7e22ce", weight: 3, fillColor: "#9333ea", fillOpacity: 0.4}}).addTo(map);
                isDrawing = false;
            }}
        }});

        map.on('mousemove', function(e) {{
            if (isDrawing && startPoint) {{
                if (drawnRect) map.removeLayer(drawnRect);
                drawnRect = L.rectangle([startPoint, e.latlng], {{color: "#a855f7", weight: 2, fillColor: "#a855f7", fillOpacity: 0.2}}).addTo(map);
            }}
        }});

        function changeMap() {{
            const selected = document.getElementById('mapSelect').value;
            window.location.href = `/map/{guild_id}?map=${{selected}}&type={zone_type}`;
        }}

        async function saveZone() {{
            if (!drawnRect) {{
                alert('Please click on the map to draw a zone boundary first!');
                return;
            }}
            const b = drawnRect.getBounds();
            const coordsData = `SW: ${{b.getSouthWest().lat.toFixed(1)}}, ${{b.getSouthWest().lng.toFixed(1)}} | NE: ${{b.getNorthEast().lat.toFixed(1)}}, ${{b.getNorthEast().lng.toFixed(1)}}`;
            
            const resp = await fetch(`/api/save_zone`, {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ guild_id: {guild_id}, map_name: '{map_name}', zone_type: '{zone_type}', coords: coordsData }})
            }});
            
            if (resp.ok) {{
                alert('✅ Zone successfully saved to Discord server database! You can close this window.');
                window.close();
            }} else {{
                alert('❌ Error saving zone.');
            }}
        }}
    </script>
</body>
</html>"""
    return web.Response(text=html, content_type='html')

async def api_save_zone(request):
    data = await request.json()
    db_cursor.execute(
        "INSERT INTO zones (guild_id, map_name, zone_type, coords) VALUES (?, ?, ?, ?)",
        (data['guild_id'], data['map_name'], data['zone_type'], data['coords'])
    )
    db_conn.commit()
    return web.json_response({"status": "success"})

class MapSelectView(discord.ui.View):
    def __init__(self, zone_type: str):
        super().__init__(timeout=180)
        self.zone_type = zone_type

    @discord.ui.select(placeholder="Select DayZ Map...", options=[
        discord.SelectOption(label="Chernarus", description="Standard 15x15km wooded & military map", emoji="🌲"),
        discord.SelectOption(label="Livonia", description="Lush forested and riverine DLC map", emoji="🌊"),
        discord.SelectOption(label="Sakhal", description="Severe arctic volcanic archipelago map", emoji="❄️")
    ])
    async def select_map(self, interaction: discord.Interaction, select: discord.ui.Select):
        # 1. Immediately defer to prevent Discord interaction timeout (Fixes "didn't respond in time")
        await interaction.response.defer(ephemeral=True)
        
        selected_map = select.values[0]
        map_image_url = MAP_IMAGE_URLS.get(selected_map, MAP_IMAGE_URLS["Chernarus"])
        web_url = f"{PUBLIC_URL}/map/{interaction.guild.id}?map={selected_map}&type={self.zone_type}"
        
        embed = discord.Embed(
            title=f"🗺️ Precision Map Canvas — {selected_map} ({self.zone_type})",
            description=f"Click the secure button below to launch your **Interactive Zoomable Map Drawer** in your browser.\n\n• **Zoom in/out** with your mouse wheel or pinch gesture for pinpoint accuracy.\n• **Click & drag / tap** to draw custom zone boundaries.\n• Click **Save Drawn Zone** to sync instantly back to your Discord server.",
            color=0x7e22ce
        )
        embed.set_image(url=map_image_url)
        
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="🌐 Open Zoomable Web Canvas", style=discord.ButtonStyle.link, url=web_url))
        
        await interaction.edit_original_response(embed=embed, view=view)

class ZoneTypeSelectView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.select(placeholder="Select Zone Type to Draw...", options=[
        discord.SelectOption(label="Base Radar", description="High-speed precision radar tracking base activity"),
        discord.SelectOption(label="PvP Zone", description="Designated player combat zone"),
        discord.SelectOption(label="Safe Zone", description="Protected non-combat zone"),
        discord.SelectOption(label="Player Radar", description="Instant-refresh target tracking radar"),
        discord.SelectOption(label="Gas Zone", description="Contaminated toxic hazard zone")
    ])
    async def select_zone_type(self, interaction: discord.Interaction, select: discord.ui.Select):
        # 1. Immediately defer to prevent timeout
        await interaction.response.defer(ephemeral=True)
        
        zone_type = select.values[0]
        embed = discord.Embed(
            title=f"🗺️ Select Map for {zone_type}",
            description="Choose which DayZ map you want to open in the interactive zoomable drawing canvas.",
            color=0x7e22ce
        )
        await interaction.edit_original_response(embed=embed, view=MapSelectView(zone_type))

@bot.tree.command(name="zone", description="Launch the interactive zoomable web map drawer for zones/radars (Admin only).")
async def zone_cmd(interaction: discord.Interaction, action: str, channel: discord.TextChannel = None):
    await interaction.response.defer(ephemeral=True)
    if action.lower() == "create":
        embed = discord.Embed(
            title="📍 Interactive Zoomable Map Drawer",
            description="Select the **Zone Type** below from the dropdown menu to begin.",
            color=0x7e22ce
        )
        if channel:
            db_cursor.execute("INSERT OR REPLACE INTO radar_config (guild_id, radar_type, channel_id) VALUES (?, 'General', ?)", (interaction.guild.id, channel.id))
            db_conn.commit()
        await interaction.followup.send(embed=embed, view=ZoneTypeSelectView(), ephemeral=True)
    elif action.lower() == "remove":
        db_cursor.execute("DELETE FROM zones WHERE guild_id = ?", (interaction.guild.id,))
        db_conn.commit()
        await interaction.followup.send("🗑️ All custom zones and radar configurations have been cleared from this server.", ephemeral=True)
    else:
        await interaction.followup.send("❌ Use `/zone create` or `/zone remove`.", ephemeral=True)

# --- RUN WEB SERVER & BOT CONCURRENTLY ---
async def start_web_server():
    app = web.Application()
    app.router.add_get('/map/{guild_id}', web_map_editor)
    app.router.add_post('/api/save_zone', api_save_zone)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, WEB_SERVER_HOST, WEB_SERVER_PORT)
    await site.start()
    print(f"🌐 Web map canvas server running at {PUBLIC_URL}")

async def main():
    await start_web_server()
    await bot.start(DISCORD_BOT_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
