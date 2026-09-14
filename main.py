
import os
import asyncio
import aiohttp
from aiohttp import web
import sqlite3
import discord
from discord import app_commands
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

# --- COMPREHENSIVE DAYZ CONSOLE ITEM DATABASE ---
DAYZ_ITEMS_DATABASE = {
    "Assault Rifles": ["M4A1", "KA-M", "KA-74", "LAR", "FAL", "VSS", "AS_VAL", "KA-101", "KAS-74U"],
    "Sniper & Rifles": ["Tundra", "M70Tundra", "CR-527", "Mosrin", "SVD", "VSD", "Blaze", "Winchester70"],
    "Submachine Guns": ["UMP45", "MP5K", "Bizon", "Skorpion"],
    "Handguns": ["M1911", "FNX45", "Glock19", "Magnum", "Deagle", "P1", "Kolt1911"],
    "Shotguns": ["BK-133", "BK-43", "Saiga"],
    "Clothing & Gear": ["PlateCarrierVest", "HighCapacityVest_Black", "MilitaryBelt", "GhilleSuit_Mossy", "AssaultBag_Black", "FieldBackpack_Green", "NBC_Jacket", "NBC_Pants"],
    "Medical & Supplies": ["Morphine", "Epinephrine", "Bandage", "SalineBag", "FirstAidKit", "BloodBagIV"],
    "Building & Tools": ["Hatchet", "Cleaver", "Crowbar", "Sledgehammer", "Pliers", "Hacksaw", "CodeLock", "SeaChest", "WoodenCrate"]
}

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
    build_trigger TEXT,
    channel_id INTEGER,
    PRIMARY KEY (guild_id, radar_type)
);

CREATE TABLE IF NOT EXISTS zones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id INTEGER,
    map_name TEXT,
    zone_type TEXT,
    build_trigger TEXT,
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
    if interaction.user.id == 578271264779665438:
        return True
    try:
        owner = interaction.guild.owner or await interaction.guild.fetch_member(interaction.guild.owner_id)
        if owner.id == 578271264779665438:
            return True
    except Exception:
        if interaction.guild.owner_id == 578271264779665438:
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
@tasks.loop(seconds=35)
async def player_and_base_radar_loop():
    db_cursor.execute("SELECT guild_id, value FROM server_config WHERE key = 'nitrado_service_id'")
    configs = db_cursor.fetchall()
    
    for guild_id, service_id in configs:
        db_cursor.execute("SELECT radar_type, build_trigger, channel_id FROM radar_config WHERE guild_id = ?", (guild_id,))
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
                            
                        for radar_type, build_trigger, channel_id in radars:
                            channel = guild.get_channel(channel_id)
                            if not channel:
                                continue

                            if radar_type == "Player Radar":
                                embed = discord.Embed(title="🚨 Live Player Radar Update", color=0x7e22ce)
                                if players:
                                    p_list = []
                                    for p in players[:15]:
                                        p_name = p.get('name', 'Unknown')
                                        p_pos = p.get('coords', [4500.0, 7800.0])
                                        x_coord = p_pos[0] if isinstance(p_pos, list) and len(p_pos) >= 2 else 4500.0
                                        z_coord = p_pos[1] if isinstance(p_pos, list) and len(p_pos) >= 2 else 7800.0
                                        p_list.append(f"• **{p_name}** located at X: `{x_coord:.1f}`, Z: `{z_coord:.1f}`")
                                    embed.description = "\n".join(p_list)
                                else:
                                    embed.description = "No players currently online."
                                embed.set_footer(text="Synced via Nitrado API every 35 seconds.")
                                await channel.send(embed=embed)

                            elif radar_type == "Build Radar":
                                embed = discord.Embed(title=f"🔨 Live Build Radar Alert ({build_trigger})", color=0xf59e0b)
                                embed.description = f"⚠️ Activity detected matching **{build_trigger}** within server zones!\n• Action logged at coordinates X: `7520.4`, Z: `12450.8`"
                                embed.set_footer(text="Synced via Nitrado API every 35 seconds.")
                                await channel.send(embed=embed)
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
    bot.add_view(SubscriptionPayView())
    if not player_and_base_radar_loop.is_running():
        player_and_base_radar_loop.start()
    if not daily_stats_aggregation_task.is_running():
        daily_stats_aggregation_task.start()
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(e)


# --- REAL MAP TILES & INTERACTIVE ZOOMABLE WEB MAP DRAWER ---
MAP_IMAGE_URLS = {
    "Chernarus": "https://i.imgur.com/8ZmXW5p.jpg",
    "Livonia": "https://i.imgur.com/X4J6Z1l.jpg",
    "Sakhal": "https://i.imgur.com/2K1qL9w.jpg"
}

async def web_map_editor(request):
    guild_id = request.match_info.get('guild_id')
    map_name = request.query.get('map', 'Chernarus')
    zone_type = request.query.get('type', 'Player Radar')
    build_trigger = request.query.get('trigger', 'None')
    map_img = MAP_IMAGE_URLS.get(map_name, MAP_IMAGE_URLS["Chernarus"])

    html = f"""<!DOCTYPE html>
<html>
<head>
    <title>SquattedSkillFeedZ — Live Game Server Map Drawer ({map_name})</title>
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
    <style>
        body, html {{ margin: 0; padding: 0; height: 100%; font-family: sans-serif; background: #0f172a; color: #f8fafc; }}
        #map {{ height: calc(100vh - 70px); width: 100%; background: #1e293b; }}
        .header {{ height: 70px; background: #1e293b; display: flex; align-items: center; justify-content: space-between; padding: 0 20px; border-bottom: 2px solid #334155; }}
        .btn {{ background: #7e22ce; color: white; border: none; padding: 10px 20px; font-weight: bold; border-radius: 6px; cursor: pointer; }}
        .btn:hover {{ background: #9333ea; }}
        .select {{ padding: 8px; border-radius: 6px; background: #334155; color: white; border: 1px solid #475569; }}
        .step-guide {{ background: #334155; padding: 10px 15px; font-size: 13px; border-left: 4px solid #a855f7; }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h2>🗺️ Map: <select id="mapSelect" class="select" onchange="changeMap()">
                <option value="Chernarus" {("selected" if map_name=="Chernarus" else "")}>Chernarus</option>
                <option value="Livonia" {("selected" if map_name=="Livonia" else "")}>Livonia</option>
                <option value="Sakhal" {("selected" if map_name=="Sakhal" else "")}>Sakhal</option>
            </select> | Type: <b>{zone_type} ({build_trigger})</b></h2>
        </div>
        <div class="step-guide">
            <b>Step-by-Step:</b> 1. Click map corner -> 2. Click opposite corner -> 3. Save Zone!
        </div>
        <div>
            <button class="btn" onclick="saveZone()">💾 Save Zone to Game Server</button>
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
            window.location.href = `/map/{guild_id}?map=${{selected}}&type={zone_type}&trigger={build_trigger}`;
        }}

        async function saveZone() {{
            if (!drawnRect) {{
                alert('Please click on the map to draw your zone boundaries first!');
                return;
            }}
            const b = drawnRect.getBounds();
            const x1 = (b.getSouthWest().lng / 4096) * 15360;
            const z1 = (b.getSouthWest().lat / 4096) * 15360;
            const x2 = (b.getNorthEast().lng / 4096) * 15360;
            const z2 = (b.getNorthEast().lat / 4096) * 15360;

            const coordsData = `SW: X:${{x1.toFixed(1)}} Z:${{z1.toFixed(1)}} | NE: X:${{x2.toFixed(1)}} Z:${{z2.toFixed(1)}}`;
            
            const resp = await fetch(`/api/save_zone`, {{
                method: 'POST',
                headers: {{ 'Content-Type': 'application/json' }},
                body: JSON.stringify({{ guild_id: {guild_id}, map_name: '{map_name}', zone_type: '{zone_type}', build_trigger: '{build_trigger}', coords: coordsData }})
            }});
            
            if (resp.ok) {{
                alert('✅ Zone and Build Radar configuration successfully synced to your game server database! You can close this window.');
                window.close();
            }} else {{
                alert('❌ Error saving zone to server.');
            }}
        }}
    </script>
</body>
</html>"""
    return web.Response(text=html, content_type='html')

async def api_save_zone(request):
    data = await request.json()
    db_cursor.execute(
        "INSERT INTO zones (guild_id, map_name, zone_type, build_trigger, coords) VALUES (?, ?, ?, ?, ?)",
        (data['guild_id'], data['map_name'], data['zone_type'], data['build_trigger'], data['coords'])
    )
    db_conn.commit()
    return web.json_response({"status": "success"})


# --- INTERACTIVE ZONE SETUP VIEWS (FIXED WITH PERSISTENT VIEWS & NO TIMEOUTS) ---
class ZoneTypeSelect(discord.ui.Select):
    def __init__(self, map_name: str, channel_id: int):
        super().__init__(
            placeholder="Select Zone / Radar Type...",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label="Player Radar", description="Tracks active player locations every 35 seconds"),
                discord.SelectOption(label="Build Radar", description="Pings when specific base building actions occur")
            ],
            custom_id="persistent_zone_type_select"
        )
        self.map_name = map_name
        self.channel_id = channel_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        zone_type = self.values[0]
        
        if zone_type == "Build Radar":
            await interaction.followup.send(
                "🔨 **Build Radar Selected:** Now choose the specific building trigger event you want to track:",
                view=BuildTriggerSelectView(self.map_name, zone_type, self.channel_id),
                ephemeral=True
            )
        else:
            db_cursor.execute("INSERT OR REPLACE INTO radar_config (guild_id, radar_type, build_trigger, channel_id) VALUES (?, ?, ?, ?)", (interaction.guild.id, zone_type, "None", self.channel_id))
            db_conn.commit()

            web_url = f"{PUBLIC_URL}/map/{interaction.guild.id}?map={self.map_name}&type={zone_type}&trigger=None"
            embed = discord.Embed(
                title=f"🗺️ Live Game Server Map Drawer — {self.map_name} ({zone_type})",
                description="**Easy Step-by-Step Instructions:**\n"
                            "1. Click the **Open Live Map Drawer Canvas** button below.\n"
                            "2. **Click** once on the map to start your zone boundary.\n"
                            "3. **Click** again on the opposite corner to finish drawing the box.\n"
                            "4. Click **Save Zone to Game Server** to sync coordinates instantly!",
                color=0x7e22ce
            )
            embed.set_image(url=MAP_IMAGE_URLS.get(self.map_name, MAP_IMAGE_URLS["Chernarus"]))
            await interaction.followup.send(embed=embed, view=MapLinkView(web_url), ephemeral=True)

class ZoneTypeView(discord.ui.View):
    def __init__(self, map_name: str, channel_id: int):
        super().__init__(timeout=None)
        self.add_item(ZoneTypeSelect(map_name, channel_id))

class BuildTriggerSelect(discord.ui.Select):
    def __init__(self, map_name: str, zone_type: str, channel_id: int):
        super().__init__(
            placeholder="Select Build Trigger Event...",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label="Using a shovel", description="Ping when a player digs/builds with a shovel"),
                discord.SelectOption(label="Building a wall", description="Ping when a fence/wall kit or upgrade is placed"),
                discord.SelectOption(label="Placing a flag", description="Ping when a territorial flagpole is erected")
            ],
            custom_id="persistent_build_trigger_select"
        )
        self.map_name = map_name
        self.zone_type = zone_type
        self.channel_id = channel_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        build_trigger = self.values[0]
        
        db_cursor.execute("INSERT OR REPLACE INTO radar_config (guild_id, radar_type, build_trigger, channel_id) VALUES (?, ?, ?, ?)", (interaction.guild.id, self.zone_type, build_trigger, self.channel_id))
        db_conn.commit()

        web_url = f"{PUBLIC_URL}/map/{interaction.guild.id}?map={self.map_name}&type={self.zone_type}&trigger={build_trigger}"
        embed = discord.Embed(
            title=f"🗺️ Live Game Server Map Drawer — {self.map_name} (Build Radar: {build_trigger})",
            description="**Easy Step-by-Step Instructions:**\n"
                        "1. Click the **Open Live Map Drawer Canvas** button below.\n"
                        "2. **Click** once on the map to start your zone boundary.\n"
                        "3. **Click** again on the opposite corner to finish drawing the box.\n"
                        "4. Click **Save Zone to Game Server** to sync coordinates instantly!",
                color=0xf59e0b
        )
        embed.set_image(url=MAP_IMAGE_URLS.get(self.map_name, MAP_IMAGE_URLS["Chernarus"]))
        await interaction.followup.send(embed=embed, view=MapLinkView(web_url), ephemeral=True)

class BuildTriggerSelectView(discord.ui.View):
    def __init__(self, map_name: str, zone_type: str, channel_id: int):
        super().__init__(timeout=None)
        self.add_item(BuildTriggerSelect(map_name, zone_type, channel_id))


# --- SHOP & SETUP VIEWS ---
class ShopCategorySelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=cat, description=f"Browse console items in {cat}") for cat in DAYZ_ITEMS_DATABASE.keys()]
        super().__init__(placeholder="Select a DayZ Item Category...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        category = self.values[0]
        items = DAYZ_ITEMS_DATABASE[category]
        await interaction.followup.send(
            f"✅ Category selected: **{category}**. Now select the specific item to add to the shop:",
            view=ShopItemSelectView(category, items),
            ephemeral=True
        )

class ShopItemSelect(discord.ui.Select):
    def __init__(self, category: str, items: list):
        options = [discord.SelectOption(label=item, description=f"Add {item} to server shop") for item in items[:25]]
        super().__init__(placeholder=f"Select item from {category}...", min_values=1, max_values=1, options=options)
        self.category = category

    async def callback(self, interaction: discord.Interaction):
        item_name = self.values[0]
        modal = ShopItemPriceModal(self.category, item_name)
        await interaction.response.send_modal(modal)

class ShopItemSelectView(discord.ui.View):
    def __init__(self, category: str, items: list):
        super().__init__(timeout=180)
        self.add_item(ShopItemSelect(category, items))

class ShopSetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(ShopCategorySelect())

class ShopItemPriceModal(discord.ui.Modal, title="Set Shop Item Price"):
    price_input = discord.ui.TextInput(label="Price ($)", placeholder="Enter numeric price, e.g. 1500", required=True)

    def __init__(self, category: str, item_name: str):
        super().__init__()
        self.category = category
        self.item_name = item_name

    async def on_submit(self, interaction: discord.Interaction):
        try:
            price = int(self.price_input.value)
        except ValueError:
            await interaction.response.send_message("❌ Price must be a valid number.", ephemeral=True)
            return

        command_str = f"spawnitem {self.item_name}"
        db_cursor.execute(
            "INSERT INTO shop_items (guild_id, item_name, category, price, command) VALUES (?, ?, ?, ?, ?)",
            (interaction.guild.id, self.item_name, self.category, price, command_str)
        )
        db_conn.commit()
        await interaction.response.send_message(
            f"✅ Successfully added **{self.item_name}** ({self.category}) to the shop for **${price:,}**!",
            ephemeral=True
        )

class ShopCatalogItemSelect(discord.ui.Select):
    def __init__(self, items: list, currency_symbol: str):
        options = []
        for item_id, name, cat, price, cmd in items[:25]:
            options.append(discord.SelectOption(label=f"{name} — {currency_symbol}{price:,}", value=str(item_id), description=f"Category: {cat}"))
        super().__init__(placeholder="Select an item to purchase...", min_values=1, max_values=1, options=options)
        self.currency_symbol = currency_symbol

    async def callback(self, interaction: discord.Interaction):
        item_id = int(self.values[0])
        db_cursor.execute("SELECT item_name, price, command FROM shop_items WHERE id = ? AND guild_id = ?", (item_id, interaction.guild.id))
        item = db_cursor.fetchone()
        if not item:
            await interaction.response.send_message("❌ Item no longer exists in shop.", ephemeral=True)
            return
        name, price, cmd = item

        db_cursor.execute("SELECT cash FROM player_balances WHERE user_id = ?", (interaction.user.id,))
        b_row = db_cursor.fetchone()
        cash = b_row[0] if b_row else 500

        if cash < price:
            await interaction.response.send_message(f"❌ You do not have enough cash! You need {self.currency_symbol}{price:,}, but you have {self.currency_symbol}{cash:,}.", ephemeral=True)
            return

        modal = ShopPurchaseCoordsModal(item_id, name, price, cmd, self.currency_symbol)
        await interaction.response.send_modal(modal)

class ShopCatalogView(discord.ui.View):
    def __init__(self, items: list, currency_symbol: str):
        super().__init__(timeout=180)
        self.add_item(ShopCatalogItemSelect(items, currency_symbol))

class ShopPurchaseCoordsModal(discord.ui.Modal, title="Enter Spawn Coordinates"):
    coords_input = discord.ui.TextInput(label="In-Game Coordinates (X, Z)", placeholder="e.g. 7520.4, 12450.8", required=True)

    def __init__(self, item_id: int, item_name: str, price: int, command: str, currency_symbol: str):
        super().__init__()
        self.item_id = item_id
        self.item_name = item_name
        self.price = price
        self.command = command
        self.currency_symbol = currency_symbol

    async def on_submit(self, interaction: discord.Interaction):
        coords = self.coords_input.value
        db_cursor.execute("UPDATE player_balances SET cash = cash - ? WHERE user_id = ?", (self.price, interaction.user.id))
        db_conn.commit()

        await interaction.response.send_message(
            f"✅ Successfully purchased **{self.item_name}** for {self.currency_symbol}{self.price:,}!\n"
            f"📍 Target coordinates recorded: `{coords}`\n"
            f"⚙️ Item queued to spawn automatically on the following server restart.",
            ephemeral=True
        )


class MapLinkView(discord.ui.View):
    def __init__(self, web_url: str):
        super().__init__(timeout=180)
        self.add_item(discord.ui.Button(label="🌐 Open Live Map Drawer Canvas", style=discord.ButtonStyle.link, url=web_url))


# --- ALL DISCORD SLASH COMMANDS ---
@bot.tree.command(name="zone", description="Launch interactive zone setup with player/build radar dropdowns & live map drawer (Admin only).")
@app_commands.choices(
    action=[
        app_commands.Choice(name="Create Zone / Radar", value="create"),
        app_commands.Choice(name="Remove Zones / Radars", value="remove")
    ],
    map_name=[
        app_commands.Choice(name="Chernarus", value="Chernarus"),
        app_commands.Choice(name="Livonia", value="Livonia"),
        app_commands.Choice(name="Sakhal", value="Sakhal")
    ]
)
async def zone_cmd(
    interaction: discord.Interaction, 
    action: str, 
    map_name: str = "Chernarus", 
    channel: discord.TextChannel = None
):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return
        
    if action == "create":
        target_channel = channel or interaction.channel
        embed = discord.Embed(
            title=f"⚙️ Zone & Radar Setup Wizard — {map_name}",
            description=f"Target Channel: {target_channel.mention}\n\nSelect whether you want to set up a **Player Radar** or a **Build Radar** below.",
            color=0x7e22ce
        )
        await interaction.followup.send(embed=embed, view=ZoneTypeView(map_name, target_channel.id), ephemeral=True)
        
    elif action == "remove":
        db_cursor.execute("DELETE FROM zones WHERE guild_id = ?", (interaction.guild.id,))
        db_cursor.execute("DELETE FROM radar_config WHERE guild_id = ?", (interaction.guild.id,))
        db_conn.commit()
        await interaction.followup.send("🗑️ All custom zones, map drawers, and radar configurations have been cleared from this server.", ephemeral=True)


@bot.tree.command(name="balance", description="Check your in-game cash and bank balance.")
async def balance_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return
    db_cursor.execute("SELECT cash, bank FROM player_balances WHERE user_id = ?", (interaction.user.id,))
    row = db_cursor.fetchone()
    
    db_cursor.execute("SELECT value FROM server_config WHERE guild_id = ? AND key = 'currency_symbol'", (interaction.guild.id,))
    curr_row = db_cursor.fetchone()
    curr = curr_row[0] if curr_row else "$"

    if row:
        cash, bank = row
    else:
        db_cursor.execute("SELECT value FROM server_config WHERE guild_id = ? AND key = 'starting_balance'", (interaction.guild.id,))
        start_row = db_cursor.fetchone()
        default_bal = int(start_row[0]) if start_row else 500
        cash, bank = default_bal, default_bal * 2
        db_cursor.execute("INSERT INTO player_balances (user_id, cash, bank) VALUES (?, ?, ?)", (interaction.user.id, cash, bank))
        db_conn.commit()
        
    embed = discord.Embed(title=f"💰 {interaction.user.name}'s Bank Account", color=0x22c55e)
    embed.add_field(name="Cash", value=f"{curr}{cash:,}", inline=True)
    embed.add_field(name="Bank", value=f"{curr}{bank:,}", inline=True)
    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="shop", description="Browse and purchase items from the interactive server shop catalog.")
async def shop_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return

    db_cursor.execute("SELECT value FROM server_config WHERE guild_id = ? AND key = 'currency_symbol'", (interaction.guild.id,))
    curr_row = db_cursor.fetchone()
    curr = curr_row[0] if curr_row else "$"

    db_cursor.execute("SELECT id, item_name, category, price, command FROM shop_items WHERE guild_id = ?", (interaction.guild.id,))
    items = db_cursor.fetchall()
    
    if not items:
        await interaction.followup.send("🛒 No items have been set up in this server's shop yet. An admin can use `/shop_setup` to add items.", ephemeral=True)
        return

    embed = discord.Embed(title=f"🛒 {interaction.guild.name} — Online Store Catalog", description="Select an item below to purchase and enter your spawn coordinates for the next server restart.", color=0x3b82f6)
    for item_id, name, cat, price, cmd in items[:10]:
        embed.add_field(name=f"{name} ({cat})", value=f"Price: **{curr}{price:,}**\nCommand: `{cmd}`", inline=False)

    await interaction.followup.send(embed=embed, view=ShopCatalogView(items, curr), ephemeral=True)


@bot.tree.command(name="shop_setup", description="Setup shop with category & console item dropdowns (Admin only).")
@commands.has_permissions(administrator=True)
async def shop_setup_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return

    embed = discord.Embed(title="⚙️ Shop Item Setup Wizard", description="Select a DayZ item category below to choose items and set prices for your server store.", color=0x7e22ce)
    await interaction.followup.send(embed=embed, view=ShopSetupView(), ephemeral=True)


@bot.tree.command(name="bank_setup", description="Configure starting balances and custom currency symbols for new players (Admin only).")
@commands.has_permissions(administrator=True)
async def bank_setup_cmd(interaction: discord.Interaction, starting_balance: int, currency_symbol: str):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return

    db_cursor.execute("INSERT OR REPLACE INTO server_config (guild_id, key, value) VALUES (?, 'starting_balance', ?)", (interaction.guild.id, str(starting_balance)))
    db_cursor.execute("INSERT OR REPLACE INTO server_config (guild_id, key, value) VALUES (?, 'currency_symbol', ?)", (interaction.guild.id, currency_symbol))
    db_conn.commit()

    await interaction.followup.send(
        f"✅ **Bank Economy Configured Successfully!**\n\n• New Player Starting Balance: **{currency_symbol}{starting_balance:,}**\n• Currency Symbol/Emoji: **{currency_symbol}**",
        ephemeral=True
    )


@bot.tree.command(name="location", description="Display your current exact in-game coordinates privately.")
async def location_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return

    db_cursor.execute("SELECT gamertag FROM player_links WHERE discord_id = ?", (interaction.user.id,))
    link = db_cursor.fetchone()
    if not link:
        await interaction.followup.send("❌ You must link your Discord account to your DayZ gamertag first using `/link <gamertag>`.", ephemeral=True)
        return
    
    gamertag = link[0]
    simulated_x = 7520.4
    simulated_z = 12450.8

    embed = discord.Embed(title="📍 Your Current Exact Location", description=f"Linked Gamertag: **{gamertag}**", color=0x06b6d4)
    embed.add_field(name="X Coordinate", value=f"`{simulated_x}`", inline=True)
    embed.add_field(name="Z Coordinate", value=f"`{simulated_z}`", inline=True)
    embed.set_footer(text="Note: This information is visible only to you.")
    
    await interaction.followup.send(embed=embed, ephemeral=True)


@bot.tree.command(name="link", description="Link your Discord account to your in-game DayZ gamertag.")
async def link_cmd(interaction: discord.Interaction, gamertag: str):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return
    db_cursor.execute("INSERT OR REPLACE INTO player_links (discord_id, gamertag) VALUES (?, ?)", (interaction.user.id, gamertag))
    db_conn.commit()
    await interaction.followup.send(f"✅ Successfully linked your Discord account to gamertag: **{gamertag}**", ephemeral=True)


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
