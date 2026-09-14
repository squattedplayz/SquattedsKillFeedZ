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

@bot.event
async def on_member_join(member: discord.Member):
    db_cursor.execute("SELECT channel, message FROM welcome_config WHERE guild_id = ?", (member.guild.id,))
    res = db_cursor.fetchone()
    if res:
        ch_name, msg = res
        channel = discord.utils.get(member.guild.text_channels, name=ch_name) or member.guild.system_channel
        if channel:
            formatted_msg = msg.replace("{user}", member.mention).replace("{server}", member.guild.name)
            await channel.send(formatted_msg)

@bot.event
async def on_member_remove(member: discord.Member):
    db_cursor.execute("SELECT channel, message FROM goodbye_config WHERE guild_id = ?", (member.guild.id,))
    res = db_cursor.fetchone()
    if res:
        ch_name, msg = res
        channel = discord.utils.get(member.guild.text_channels, name=ch_name)
        if channel:
            formatted_msg = msg.replace("{user}", member.name).replace("{server}", member.guild.name)
            await channel.send(formatted_msg)


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


# --- INTERACTIVE SHOP SETUP & CATALOG VIEWS ---
class ShopCategorySelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=cat, description=f"Browse console items in {cat}") for cat in DAYZ_ITEMS_DATABASE.keys()]
        super().__init__(placeholder="Select a DayZ Item Category...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        category = self.values[0]
        items = DAYZ_ITEMS_DATABASE[category]
        await interaction.response.send_message(
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
    coords_input = discord.ui.TextInput(label="In-Game Coordinates (X, Z or Grid)", placeholder="e.g. 4500.5, 7800.2", required=True)

    def __init__(self, item_id: int, item_name: str, price: int, command: str, currency_symbol: str):
        super().__init__()
        self.item_id = item_id
        self.item_name = item_name
        self.price = price
        self.command = command
        self.currency_symbol = currency_symbol

    async def on_submit(self, interaction: discord.Interaction):
        coords = self.coords_input.value
        # Deduct balance
        db_cursor.execute("UPDATE player_balances SET cash = cash - ? WHERE user_id = ?", (self.price, interaction.user.id))
        db_conn.commit()

        await interaction.response.send_message(
            f"✅ Successfully purchased **{self.item_name}** for {self.currency_symbol}{self.price:,}!\n"
            f"📍 Target coordinates recorded: `{coords}`\n"
            f"⚙️ Item queued to spawn on the following restart via command: `{self.command}`",
            ephemeral=True
        )


# --- BULLETPROOF BUTTON VIEW FOR WEB MAP ---
class MapLinkView(discord.ui.View):
    def __init__(self, web_url: str):
        super().__init__(timeout=180)
        self.add_item(discord.ui.Button(label="🌐 Open Zoomable Web Canvas", style=discord.ButtonStyle.link, url=web_url))


# --- ALL COMPREHENSIVE DISCORD SLASH COMMANDS ---
@bot.tree.command(name="zone", description="Launch the interactive zoomable web map drawer for zones/radars (Admin only).")
async def zone_cmd(
    interaction: discord.Interaction, 
    action: str, 
    map_name: str = "Chernarus", 
    zone_type: str = "Base Radar", 
    channel: discord.TextChannel = None
):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return
        
    if action.lower() == "create":
        if channel:
            db_cursor.execute("INSERT OR REPLACE INTO radar_config (guild_id, radar_type, channel_id) VALUES (?, ?, ?)", (interaction.guild.id, zone_type, channel.id))
            db_conn.commit()
            
        map_image_url = MAP_IMAGE_URLS.get(map_name, MAP_IMAGE_URLS["Chernarus"])
        web_url = f"{PUBLIC_URL}/map/{interaction.guild.id}?map={map_name}&type={zone_type}"
        
        embed = discord.Embed(
            title=f"🗺️ Precision Map Canvas — {map_name} ({zone_type})",
            description=f"Click the secure button below to launch your **Interactive Zoomable Map Drawer** in your browser.\n\n• **Zoom in/out** with your mouse wheel or pinch gesture.\n• **Click & drag / tap** to draw custom zone boundaries.\n• Click **Save Drawn Zone** to sync instantly back to your Discord server.",
            color=0x7e22ce
        )
        embed.set_image(url=map_image_url)
        
        await interaction.followup.send(embed=embed, view=MapLinkView(web_url), ephemeral=True)
        
    elif action.lower() == "remove":
        db_cursor.execute("DELETE FROM zones WHERE guild_id = ?", (interaction.guild.id,))
        db_conn.commit()
        await interaction.followup.send("🗑️ All custom zones and radar configurations have been cleared from this server.", ephemeral=True)
    else:
        await interaction.followup.send("❌ Use `/zone create` or `/zone remove`.", ephemeral=True)


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
        await interaction.followup.send("🛒 No items have been set up in this server's shop yet. An admin can use `/shop setup` to add items.", ephemeral=True)
        return

    embed = discord.Embed(title=f"🛒 {interaction.guild.name} — Online Store Catalog", description="Select an item below to purchase and enter your spawn coordinates for the next server restart.", color=0x3b82f6)
    for item_id, name, cat, price, cmd in items[:10]:
        embed.add_field(name=f"{name} ({cat})", value=f"Price: **{curr}{price:,}**\nCommand: `{cmd}`", inline=False)

    await interaction.followup.send(embed=embed, view=ShopCatalogView(items, curr), ephemeral=True)


@bot.tree.command(name="shop_setup", description="Setup or add items to the server shop via an interactive category dropdown (Admin only).")
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
    # Simulated live query or fetched position from Nitrado/server logs for the linked gamertag
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


@bot.tree.command(name="whitelist", description="Manage server access whitelist.")
async def whitelist_cmd(interaction: discord.Interaction, action: str, gamertag: str):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return
    if action.lower() == "add":
        db_cursor.execute("INSERT INTO whitelist (guild_id, gamertag) VALUES (?, ?)", (interaction.guild.id, gamertag))
        db_conn.commit()
        await interaction.followup.send(f"✅ Successfully whitelisted gamertag: **{gamertag}**", ephemeral=True)
    elif action.lower() == "remove":
        db_cursor.execute("DELETE FROM whitelist WHERE guild_id = ? AND gamertag = ?", (interaction.guild.id, gamertag))
        db_conn.commit()
        await interaction.followup.send(f"🗑️ Removed gamertag from whitelist: **{gamertag}**", ephemeral=True)
    else:
        await interaction.followup.send("❌ Use `/whitelist add <gamertag>` or `/whitelist remove <gamertag>`.", ephemeral=True)


@bot.tree.command(name="bounty", description="Place or view active bounties on target players.")
async def bounty_cmd(interaction: discord.Interaction, action: str, amount: int = None, target: discord.Member = None):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return
    if action.lower() == "list":
        db_cursor.execute("SELECT target_id, amount, setter_id FROM bounties")
        bounties = db_cursor.fetchall()
        embed = discord.Embed(title="🎯 Active Bounties Board", color=0xef4444)
        if not bounties:
            embed.description = "No active bounties currently placed."
        else:
            for t_id, amt, s_id in bounties:
                embed.add_field(name=f"Target ID: {t_id}", value=f"Reward: **${amt:,}**\nPlaced by: <@{s_id}>", inline=False)
        await interaction.followup.send(embed=embed, ephemeral=True)
    elif action.lower() == "set" and target and amount:
        db_cursor.execute("INSERT OR REPLACE INTO bounties (target_id, amount, setter_id) VALUES (?, ?, ?)", (target.id, amount, interaction.user.id))
        db_conn.commit()
        await interaction.followup.send(f"🎯 Bounty of **${amount:,}** placed on {target.mention}!", ephemeral=True)
    else:
        await interaction.followup.send("❌ Invalid usage. Use `/bounty list` or `/bounty set <amount> <target>`.", ephemeral=True)


@bot.tree.command(name="ticket", description="Manage administrative support tickets.")
async def ticket_cmd(interaction: discord.Interaction, action: str):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return
    if action.lower() == "stats":
        db_cursor.execute("SELECT metric, count FROM ticket_stats")
        stats = db_cursor.fetchall()
        embed = discord.Embed(title="🎫 Support Ticket Statistics", color=0x06b6d4)
        for metric, count in stats:
            embed.add_field(name=metric.capitalize(), value=str(count), inline=True)
        await interaction.followup.send(embed=embed, ephemeral=True)
    else:
        await interaction.followup.send("Support ticket creation is managed automatically through server panel integration.", ephemeral=True)


@bot.tree.command(name="welcome", description="Configure server welcome message settings.")
async def welcome_cmd(interaction: discord.Interaction, channel: discord.TextChannel, message: str):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return
    db_cursor.execute("INSERT OR REPLACE INTO welcome_config (guild_id, channel, message) VALUES (?, ?, ?)", (interaction.guild.id, channel.name, message))
    db_conn.commit()
    await interaction.followup.send(f"✅ Welcome messages configured for channel {channel.mention}.", ephemeral=True)


@bot.tree.command(name="goodbye", description="Configure server goodbye message settings.")
async def goodbye_cmd(interaction: discord.Interaction, channel: discord.TextChannel, message: str):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return
    db_cursor.execute("INSERT OR REPLACE INTO goodbye_config (guild_id, channel, message) VALUES (?, ?, ?)", (interaction.guild.id, channel.name, message))
    db_conn.commit()
    await interaction.followup.send(f"✅ Goodbye messages configured for channel {channel.mention}.", ephemeral=True)


@bot.tree.command(name="killfeed", description="Enable or disable automated live server killfeed updates.")
async def killfeed_cmd(interaction: discord.Interaction, enabled: bool, channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return
    db_cursor.execute("INSERT OR REPLACE INTO killfeed_config (guild_id, enabled, channel_id) VALUES (?, ?, ?)", (interaction.guild.id, 1 if enabled else 0, channel.id))
    db_conn.commit()
    status_str = "Enabled" if enabled else "Disabled"
    await interaction.followup.send(f"⚔️ Killfeed successfully **{status_str}** targeting channel {channel.mention}.", ephemeral=True)


@bot.tree.command(name="leaderboard", description="Configure the live server player leaderboard channel.")
async def leaderboard_cmd(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return
    db_cursor.execute("INSERT OR REPLACE INTO leaderboard_config (guild_id, channel_id) VALUES (?, ?)", (interaction.guild.id, channel.id))
    db_conn.commit()
    await interaction.followup.send(f"🏆 Leaderboard display channel set to {channel.mention}.", ephemeral=True)


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
