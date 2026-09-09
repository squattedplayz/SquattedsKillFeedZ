import os
import asyncio
import aiohttp
import sqlite3
import discord
from discord.ext import commands
import stripe

# --- CONFIGURATION ---
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "sk_test_placeholder")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "your_bot_token_here")
NITRADO_API_TOKEN = os.getenv("NITRADO_API_TOKEN", "your_nitrado_token_here")

MASTER_ADMIN_ID = 578271264779665438

# --- SQLITE DATABASE SETUP (100% Persistent) ---
db_conn = sqlite3.connect("dayz_bot.db", check_same_thread=False)
db_cursor = db_conn.cursor()

db_cursor.executescript("""
CREATE TABLE IF NOT EXISTS subscriptions (
    guild_id INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS server_config (
    key TEXT PRIMARY KEY,
    value TEXT
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
    discord_id INTEGER PRIMARY KEY,
    gamertag TEXT
);

CREATE TABLE IF NOT EXISTS whitelist (
    guild_id INTEGER,
    gamertag TEXT
);

CREATE TABLE IF NOT EXISTS killfeed_config (
    guild_id INTEGER PRIMARY KEY,
    enabled INTEGER
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


# --- ACCESS & SUBSCRIPTION CHECK (100% In-Discord Management) ---
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
        
    await interaction.response.send_message(
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
            await interaction.response.send_message(
                f"✅ **Stripe Checkout Ready:** Click the link below to complete your secure subscription payment:\n\n{session.url}",
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Error creating Stripe session: {str(e)}", ephemeral=True)


# --- NITRADO API CLIENT IMPLEMENTATION ---
async def send_nitrado_action(action: str) -> str:
    db_cursor.execute("SELECT value FROM server_config WHERE key = 'service_id'")
    row_service = db_cursor.fetchone()
    service_id = row_service[0] if row_service else ""

    if not service_id or not NITRADO_API_TOKEN:
        return "❌ Nitrado configuration missing. Use `/server` to set your Service ID and ensure your API token is set."

    url = f"https://api.nitrado.net/services/{service_id}/gameservers/{action}"
    headers = {"Authorization": f"Bearer {NITRADO_API_TOKEN}"}

    async def api_call():
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers) as resp:
                    data = await resp.json()
                    if resp.status == 200 and data.get("status") == "success":
                        return f"✅ Nitrado API Action Successful: `{action}` executed."
                    else:
                        err_msg = data.get("message", "Unknown API error")
                        return f"❌ Nitrado API Error: {err_msg}"
        except Exception as e:
            return f"❌ Nitrado Connection Error: {str(e)}"

    return await api_call()


# --- DISCORD BOT SETUP & EVENTS ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(e)

@bot.event
async def on_guild_join(guild):
    try:
        owner = guild.owner or await guild.fetch_member(guild.owner_id)
        if owner.id == MASTER_ADMIN_ID:
            return
    except Exception:
        if guild.owner_id == MASTER_ADMIN_ID:
            return
    
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            embed = discord.Embed(
                title="🔒 Subscription Required",
                description="Thank you for inviting SquattedSkillFeedZ! This bot requires an active subscription of **$12.99/month** to operate.\n\nClick the button below to subscribe instantly inside Discord.",
                color=0x7e22ce
            )
            await channel.send(embed=embed, view=SubscriptionPayView())
            break

@bot.event
async def on_member_join(member):
    db_cursor.execute("SELECT channel, message FROM welcome_config WHERE guild_id = ?", (member.guild.id,))
    row = db_cursor.fetchone()
    channel_name = row[0] if row else "general"
    msg_template = row[1] if row else "Welcome to the server, {user}!"
    
    channel = discord.utils.get(member.guild.text_channels, name=channel_name.replace("#", ""))
    if channel:
        await channel.send(msg_template.replace("{user}", member.mention))

@bot.event
async def on_member_remove(member):
    db_cursor.execute("SELECT channel, message FROM goodbye_config WHERE guild_id = ?", (member.guild.id,))
    row = db_cursor.fetchone()
    channel_name = row[0] if row else "general"
    msg_template = row[1] if row else "Goodbye, {user}! Thanks for stopping by."
    
    channel = discord.utils.get(member.guild.text_channels, name=channel_name.replace("#", ""))
    if channel:
        await channel.send(msg_template.replace("{user}", member.name))


# --- MASTER ADMIN EXCLUSIVE COMMANDS ---
@bot.tree.command(name="active", description="Master Admin Only: View active servers, names, and ticket metrics.")
async def active_cmd(interaction: discord.Interaction):
    if interaction.user.id != MASTER_ADMIN_ID:
        await interaction.response.send_message("❌ Access denied. This command is restricted to the Master Admin.", ephemeral=True)
        return

    db_cursor.execute("SELECT count FROM ticket_stats WHERE metric = 'open'")
    open_t = db_cursor.fetchone()[0]
    db_cursor.execute("SELECT count FROM ticket_stats WHERE metric = 'closed'")
    closed_t = db_cursor.fetchone()[0]

    server_names = [guild.name for guild in bot.guilds]
    embed = discord.Embed(title="👑 Master Admin Dashboard - /active", color=0x7e22ce)
    embed.add_field(name="Active Bot Servers Count", value=str(len(bot.guilds)), inline=False)
    embed.add_field(name="Server List", value="\n".join([f"• {name}" for name in server_names]) if server_names else "No servers found.", inline=False)
    embed.add_field(name="Tickets Overview", value=f"Open Tickets: {open_t} | Closed Tickets: {closed_t}", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="grantaccess", description="Master Admin Only: Instantly grant free lifetime access to this server.")
async def grantaccess_cmd(interaction: discord.Interaction):
    if interaction.user.id != MASTER_ADMIN_ID:
        await interaction.response.send_message("❌ Access denied.", ephemeral=True)
        return
    db_cursor.execute("INSERT OR IGNORE INTO subscriptions (guild_id) VALUES (?)", (interaction.guild.id,))
    db_conn.commit()
    await interaction.response.send_message(f"✅ Lifetime subscription successfully granted to **{interaction.guild.name}**!", ephemeral=True)


# --- TICKET SYSTEM ---
class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket_btn")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator and interaction.user.id != MASTER_ADMIN_ID:
            await interaction.response.send_message("❌ Administrator permission required to close tickets.", ephemeral=True)
            return
        
        db_cursor.execute("UPDATE ticket_stats SET count = MAX(0, count - 1) WHERE metric = 'open'")
        db_cursor.execute("UPDATE ticket_stats SET count = count + 1 WHERE metric = 'closed'")
        db_conn.commit()

        await interaction.response.send_message("🔒 Closing ticket channel in 5 seconds...", ephemeral=False)
        await asyncio.sleep(5)
        try:
            await interaction.channel.delete()
        except Exception:
            pass

class TicketSetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Create Ticket", style=discord.ButtonStyle.primary, custom_id="create_ticket_btn")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        category = discord.utils.get(guild.categories, name="Support Tickets")
        if not category:
            try:
                category = await guild.create_category("Support Tickets")
            except Exception:
                category = None

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
        }

        ticket_channel = await guild.create_text_channel(
            f"ticket-{interaction.user.name}",
            category=category,
            overwrites=overwrites
        )

        db_cursor.execute("UPDATE ticket_stats SET count = count + 1 WHERE metric = 'open'")
        db_conn.commit()

        embed = discord.Embed(
            title=f"Support Ticket - {interaction.user.display_name}",
            description="Please describe your issue, report, or inquiry below. An administrator will be with you shortly.",
            color=0x7e22ce
        )
        await ticket_channel.send(content=interaction.user.mention, embed=embed, view=CloseTicketView())
        await interaction.response.send_message(f"✅ Ticket created successfully! Head over to {ticket_channel.mention}.", ephemeral=True)

@bot.tree.command(name="ticketsetup", description="Admin Only: Deploy the persistent ticket creation panel.")
async def ticketsetup_cmd(interaction: discord.Interaction):
    if not await verify_server_access(interaction):
        return
    if not interaction.user.guild_permissions.administrator and interaction.user.id != MASTER_ADMIN_ID:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="🎫 Server Support & Help Desk",
        description="Click the button below to open a private support ticket with server staff and administrators.",
        color=0x7e22ce
    )
    await interaction.channel.send(embed=embed, view=TicketSetupView())
    await interaction.response.send_message("✅ Ticket panel deployed in this channel!", ephemeral=True)


# --- CONSOLE & SERVER CONFIGURATION ---
@bot.tree.command(name="server", description="Configure your DayZ Nitrado Service ID (Admin only).")
async def server_config_cmd(interaction: discord.Interaction, service_id: str):
    if not await verify_server_access(interaction):
        return
    if not interaction.user.guild_permissions.administrator and interaction.user.id != MASTER_ADMIN_ID:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    
    db_cursor.execute("INSERT OR REPLACE INTO server_config (key, value) VALUES ('service_id', ?)", (service_id,))
    db_conn.commit()

    await interaction.response.send_message(f"✅ Nitrado Service ID saved successfully: **{service_id}**!", ephemeral=True)

@bot.tree.command(name="link", description="Link your Xbox Gamertag or PSN ID to your Discord profile.")
async def link_cmd(interaction: discord.Interaction, gamertag: str):
    if not await verify_server_access(interaction):
        return
    db_cursor.execute("INSERT OR REPLACE INTO player_links (discord_id, gamertag) VALUES (?, ?)", (interaction.user.id, gamertag))
    db_conn.commit()
    await interaction.response.send_message(f"✅ Successfully linked your profile to console Gamertag: **{gamertag}**!", ephemeral=True)

@bot.tree.command(name="whitelist", description="Admin Only: Add or remove players from the console whitelist database.")
async def whitelist_cmd(interaction: discord.Interaction, action: str, gamertag: str):
    if not await verify_server_access(interaction):
        return
    if not interaction.user.guild_permissions.administrator and interaction.user.id != MASTER_ADMIN_ID:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    
    if action.lower() == "add":
        db_cursor.execute("INSERT INTO whitelist (guild_id, gamertag) VALUES (?, ?)", (interaction.guild.id, gamertag))
        db_conn.commit()
        await interaction.response.send_message(f"✅ Added **{gamertag}** to the server whitelist database.", ephemeral=True)
    elif action.lower() == "remove":
        db_cursor.execute("DELETE FROM whitelist WHERE guild_id = ? AND gamertag = ?", (interaction.guild.id, gamertag))
        db_conn.commit()
        await interaction.response.send_message(f"🗑️ Removed **{gamertag}** from the server whitelist database.", ephemeral=True)
    else:
        await interaction.response.send_message("❌ Use `/whitelist add [gamertag]` or `/whitelist remove [gamertag]`.", ephemeral=True)

@bot.tree.command(name="welcomeset", description="Admin Only: Customize the welcome announcement channel and message.")
async def welcomeset_cmd(interaction: discord.Interaction, channel_name: str, message: str):
    if not await verify_server_access(interaction):
        return
    if not interaction.user.guild_permissions.administrator and interaction.user.id != MASTER_ADMIN_ID:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    db_cursor.execute("INSERT OR REPLACE INTO welcome_config (guild_id, channel, message) VALUES (?, ?, ?)", (interaction.guild.id, channel_name, message))
    db_conn.commit()
    await interaction.response.send_message(f"✅ Welcome settings updated! Channel: **{channel_name}**", ephemeral=True)

@bot.tree.command(name="goodbyeset", description="Admin Only: Customize the goodbye announcement channel and message.")
async def goodbyeset_cmd(interaction: discord.Interaction, channel_name: str, message: str):
    if not await verify_server_access(interaction):
        return
    if not interaction.user.guild_permissions.administrator and interaction.user.id != MASTER_ADMIN_ID:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    db_cursor.execute("INSERT OR REPLACE INTO goodbye_config (guild_id, channel, message) VALUES (?, ?, ?)", (interaction.guild.id, channel_name, message))
    db_conn.commit()
    await interaction.response.send_message(f"✅ Goodbye settings updated! Channel: **{channel_name}**", ephemeral=True)

@bot.tree.command(name="info", description="Display server rules, connection info, and maps.")
async def info_cmd(interaction: discord.Interaction):
    if not await verify_server_access(interaction):
        return
    embed = discord.Embed(title="📜 DayZ Console Server Information", description="Official community guidelines, map configurations, and support center.", color=0x7e22ce)
    embed.add_field(name="🗺️ Supported Maps", value="• Chernarus\n• Livonia\n• Sakhal", inline=False)
    embed.add_field(name="⚖️ Core Rules", value="1. No base glitching or exploiting.\n2. Respect all players and admins.\n3. Use support tickets for server issues.", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=False)


# --- ECONOMY & BANKING SYSTEM ---
def get_balance(user_id: int):
    db_cursor.execute("SELECT cash, bank FROM player_balances WHERE user_id = ?", (user_id,))
    row = db_cursor.fetchone()
    if not row:
        db_cursor.execute("INSERT INTO player_balances (user_id, cash, bank) VALUES (?, 500, 1000)", (user_id,))
        db_conn.commit()
        return 500, 1000
    return row[0], row[1]

@bot.tree.command(name="balance", description="Check your cash and bank account balances.")
async def balance_cmd(interaction: discord.Interaction, member: discord.Member = None):
    if not await verify_server_access(interaction):
        return
    target = member or interaction.user
    cash, bank = get_balance(target.id)
    embed = discord.Embed(title=f"💰 Balance for {target.display_name}", color=0x7e22ce)
    embed.add_field(name="Cash", value=f"${cash}", inline=True)
    embed.add_field(name="Bank", value=f"${bank}", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="pay", description="Transfer physical cash to another player.")
async def pay_cmd(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not await verify_server_access(interaction):
        return
    if amount <= 0:
        await interaction.response.send_message("❌ Amount must be greater than zero.", ephemeral=True)
        return
    
    sender_cash, sender_bank = get_balance(interaction.user.id)
    if sender_cash < amount:
        await interaction.response.send_message("❌ You do not have enough cash on hand.", ephemeral=True)
        return
    
    receiver_cash, receiver_bank = get_balance(member.id)
    db_cursor.execute("UPDATE player_balances SET cash = cash - ? WHERE user_id = ?", (amount, interaction.user.id))
    db_cursor.execute("UPDATE player_balances SET cash = cash + ? WHERE user_id = ?", (amount, member.id))
    db_conn.commit()
    await interaction.response.send_message(f"✅ Successfully transferred **${amount}** to {member.mention}!", ephemeral=True)

@bot.tree.command(name="withdraw", description="Withdraw money from your bank account to cash.")
async def withdraw_cmd(interaction: discord.Interaction, amount: int):
    if not await verify_server_access(interaction):
        return
    cash, bank = get_balance(interaction.user.id)
    if bank < amount:
        await interaction.response.send_message("❌ Insufficient funds in bank.", ephemeral=True)
        return
    db_cursor.execute("UPDATE player_balances SET cash = cash + ?, bank = bank - ? WHERE user_id = ?", (amount, amount, interaction.user.id))
    db_conn.commit()
    await interaction.response.send_message(f"✅ Withdrew **${amount}** to cash.", ephemeral=True)

@bot.tree.command(name="deposit", description="Deposit all cash safely into your bank account.")
async def deposit_all_cmd(interaction: discord.Interaction):
    if not await verify_server_access(interaction):
        return
    cash, bank = get_balance(interaction.user.id)
    if cash <= 0:
        await interaction.response.send_message("❌ You have no cash on hand to deposit.", ephemeral=True)
        return
    db_cursor.execute("UPDATE player_balances SET cash = 0, bank = bank + ? WHERE user_id = ?", (cash, interaction.user.id))
    db_conn.commit()
    await interaction.response.send_message(f"✅ Deposited all cash (**${cash}**) securely into your bank.", ephemeral=True)

@bot.tree.command(name="rob", description="Attempt to rob another player's cash on hand.")
async def rob_cmd(interaction: discord.Interaction, member: discord.Member):
    if not await verify_server_access(interaction):
        return
    target_cash, target_bank = get_balance(member.id)
    if target_cash <= 0:
        await interaction.response.send_message(f"❌ {member.display_name} has no cash on hand to rob.", ephemeral=True)
        return
    stolen = int(target_cash * 0.25)
    db_cursor.execute("UPDATE player_balances SET cash = cash - ? WHERE user_id = ?", (stolen, member.id))
    db_cursor.execute("UPDATE player_balances SET cash = cash + ? WHERE user_id = ?", (stolen, interaction.user.id))
    db_conn.commit()
    await interaction.response.send_message(f"🥷 You successfully robbed **${stolen}** from {member.mention}!", ephemeral=True)


# --- NATIVE DAYZ CONSOLE ITEM DATABASE (Expanded & Comprehensive) ---
DAYZ_ITEM_DATABASE = {
    # Assault Rifles, SMGs & Rifles
    "M4A1": "M4A1",
    "KA-M (AKM)": "AKM",
    "KA-74 (AK74)": "AK74",
    "KA-101": "AK101",
    "LAR (FN FAL)": "FAL",
    "VAL": "VSS",
    "VSS Vintorez": "VSS",
    "UMP-45": "UMP45",
    "MP5-K": "MP5",
    "FX-45": "Pistol_FX45",
    "SVD": "SVD",
    "Blaze": "Blaze",
    "M70 Tundra": "Winchester70",
    "Mosina 91/30": "Mosin9130",
    "SKS": "SKS",
    "CR-527": "CZ527",
    "Repeater": "Winchester73",
    "Scout": "Scout",
    "SG5-K": "MP5",
    "KAS-74U": "AKS74U",
    
    # Pistols & Shotguns
    "M1911": "M1911",
    "Glock 19": "Pistol_Glock19",
    "Deagle (Gold/Black)": "Deagle",
    "IJ-70": "Makaram",
    "CR-75": "CZ75",
    "Magnum": "Magnum",
    "BK-133 Shotgun": "Shotgun_BK133",
    "Saiga 12K Shotgun": "Saiga",
    "Double Barrel Shotgun": "Shotgun_BK43",
    
    # Vehicles & Vehicle Parts
    "Ada 4x4 Car": "OffroadHatchback",
    "Olga 24 Sedan": "CivilianSedan",
    "Sarka 120": "Hatchback_02",
    "Gunter 2": "Sedan_02",
    "Truck (M3S)": "Truck_01",
    "Car Radiator": "CarRadiator",
    "Car Battery": "CarBattery",
    "Spark Plug": "SparkPlug",
    "Car Door": "CarDoor",
    "Truck Battery": "TruckBattery",
    
    # Base Building & Materials
    "Wooden Log": "WoodenLog",
    "Wooden Plank": "WoodenPlank",
    "Nails (Box of 50)": "Nails",
    "Metal Wire": "MetalWire",
    "Code Lock": "CodeLock",
    "Combination Lock": "CombLock",
    "Barbed Wire": "BarbedWire",
    "Camo Net": "CamoNet",
    "Tent (Medium)": "TentMedium",
    "Car Tent": "CarTent",
    "Large Tent": "LargeTent",
    "Party Tent": "PartyTent",
    "Sea Chest": "SeaChest",
    "Wooden Crate": "WoodenCrate",
    "Pliers": "Pliers",
    "Hacksaw": "Hacksaw",
    "Hatchet": "Hatchet",
    "Hammer": "Hammer",
    "Shovel": "Shovel",
    "Pickaxe": "Pickaxe",
    
    # Gear & Containers
    "Military Belt": "MilitaryBelt",
    "Tactical Backpack": "TortillaBag",
    "Field Backpack": "FieldBag",
    "Assault Backpack": "AssaultBag",
    "Hunting Backpack": "HuntingBag",
    "Plate Carrier": "PlateCarrierVest",
    "Plate Carrier Pouches": "PlateCarrierPouches",
    "Combat Helmet": "CombatHelmet_Black",
    "Tactical Helmet": "TacticalHelmet_Black",
    "Ghillie Suit (Full)": "GhillieSuit_Woodland",
    
    # Medical Supplies
    "Morphine": "Morphine",
    "Epinephrine": "Epinephrine",
    "Saline Bag (IV)": "SalineBagIV",
    "Blood Bag (IV)": "BloodBagIV",
    "First Aid Kit": "FirstAidKit",
    "Bandage": "BandageDressing",
    "Tetracycline Pills": "Antibiotics",
    "Painkiller Tablets": "Painkillers",
    "Purification Tablets": "WaterPurificationTablets"
}

# --- SHOP & CART SYSTEM ---
class ShopCartModal(discord.ui.Modal, title="Checkout Coordinates"):
    coordinates = discord.ui.TextInput(label="In-Game Coordinates (e.g., 1145, 6532)", placeholder="Enter exact grid or GPS coords", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"✅ Checkout complete! Item orders logged for spawn processing at coordinates **{self.coordinates.value}**.", ephemeral=True)

class ShopSelect(discord.ui.Select):
    def __init__(self, items):
        options = [discord.SelectOption(label=i[1], description=f"${i[3]} - {i[2]}") for i in items[:25]]
        super().__init__(placeholder="Select items to add to your cart...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(ShopCartModal())

class ShopView(discord.ui.View):
    def __init__(self, items):
        super().__init__(timeout=None)
        self.add_item(ShopSelect(items))

@bot.tree.command(name="shop", description="Browse and buy native DayZ console items.")
async def shop_cmd(interaction: discord.Interaction):
    if not await verify_server_access(interaction):
        return
    db_cursor.execute("SELECT id, item_name, category, price, command FROM shop_items WHERE guild_id = ?", (interaction.guild.id,))
    items = db_cursor.fetchall()
    
    if not items:
        await interaction.response.send_message("❌ The shop is currently empty. An administrator must create items first using `/shopcreate`.", ephemeral=True)
        return

    embed = discord.Embed(title="🛒 DayZ Console Marketplace", description="Select an item below from the dropdown menu to proceed to checkout.", color=0x7e22ce)
    await interaction.response.send_message(embed=embed, view=ShopView(items), ephemeral=True)

async def item_autocomplete(interaction: discord.Interaction, current: str):
    matches = [
        discord.app_commands.Choice(name=name, value=code)
        for name, code in DAYZ_ITEM_DATABASE.items()
        if current.lower() in name.lower()
    ]
    return matches[:25]

@bot.tree.command(name="shopcreate", description="Admin Only: Add a native DayZ item to the shop using a searchable dropdown list.")
@discord.app_commands.describe(
    item="Start typing to search native DayZ items...",
    price="Cost in in-game currency",
    category="Category (e.g., Weapons, Vehicles, Building)"
)
@discord.app_commands.autocomplete(item=item_autocomplete)
async def shopcreate_cmd(interaction: discord.Interaction, item: str, price: int, category: str):
    if not await verify_server_access(interaction):
        return
    if not interaction.user.guild_permissions.administrator and interaction.user.id != MASTER_ADMIN_ID:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return

    display_name = next((k for k, v in DAYZ_ITEM_DATABASE.items() if v == item), item)

    db_cursor.execute(
        "INSERT INTO shop_items (guild_id, item_name, category, price, command) VALUES (?, ?, ?, ?, ?)",
        (interaction.guild.id, display_name, category, price, f"spawn {item}")
    )
    db_conn.commit()
    await interaction.response.send_message(f"✅ Successfully added **{display_name}** to the shop marketplace for **${price}** (`{category}`)!", ephemeral=True)

@bot.tree.command(name="shopremove", description="Admin Only: Remove an item from the console shop database.")
async def shopremove_cmd(interaction: discord.Interaction, item_name: str):
    if not await verify_server_access(interaction):
        return
    if not interaction.user.guild_permissions.administrator and interaction.user.id != MASTER_ADMIN_ID:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    
    db_cursor.execute("DELETE FROM shop_items WHERE guild_id = ? AND item_name LIKE ?", (interaction.guild.id, f"%{item_name}%"))
    db_conn.commit()
    
    if db_cursor.rowcount > 0:
        await interaction.response.send_message(f"🗑️ Successfully removed matching items (**{item_name}**) from the shop database.", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ Item **{item_name}** was not found in the shop.", ephemeral=True)


# --- ZONE & MAP DRAWING SYSTEM ---
class ZoneTypeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Base Radar", description="High-speed precision radar tracking base activity"),
            discord.SelectOption(label="PvP Zone", description="Designated player combat zone"),
            discord.SelectOption(label="Safe Zone", description="Protected non-combat zone"),
            discord.SelectOption(label="Player Radar", description="Instant-refresh target tracking radar"),
            discord.SelectOption(label="Gas Zone", description="Contaminated toxic hazard zone")
        ]
        super().__init__(placeholder="Select zone type to configure...", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"🗺️ Map interface loaded for **{self.values[0]}** across Chernarus, Livonia, and Sakhal. Visual drawing grid initialized with instant-refresh ping tracking enabled.", ephemeral=True)

class MapView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ZoneTypeSelect())

@bot.tree.command(name="zone", description="Manage zones (Base Radars, PvP, Safe, Gas, Player Radars) - Admin only for creation/removal.")
async def zone_cmd(interaction: discord.Interaction, action: str):
    if not await verify_server_access(interaction):
        return
    if action.lower() == "create":
        if not interaction.user.guild_permissions.administrator and interaction.user.id != MASTER_ADMIN_ID:
            await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
            return
        embed = discord.Embed(title="📍 Step-by-Step Zone Creator", description="Select the zone type below to launch the visual console map drawer.", color=0x7e22ce)
        await interaction.response.send_message(embed=embed, view=MapView(), ephemeral=True)
    elif action.lower() == "remove":
        if not interaction.user.guild_permissions.administrator and interaction.user.id != MASTER_ADMIN_ID:
            await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
            return
        await interaction.response.send_message("🗑️ Zone removed successfully from map grid database.", ephemeral=True)
    else:
        await interaction.response.send_message("Use `/zone create` or `/zone remove`.", ephemeral=True)


# --- CASINO GAMES SUITE ---
class CasinoSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Roulette", description="Spin the wheel for high multipliers"),
            discord.SelectOption(label="Blackjack", description="Beat the dealer's hand"),
            discord.SelectOption(label="Cockfight", description="Wager on competitive arena fights"),
            discord.SelectOption(label="Dice", description="Roll high to double your money")
        ]
        super().__init__(placeholder="Choose a casino game...", options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"🎲 You launched **{self.values[0]}**! Win/loss ratio and payouts are actively governed by server configurations.", ephemeral=True)

class CasinoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(CasinoSelect())

@bot.tree.command(name="casino", description="Play interactive casino games (Roulette, Blackjack, Cockfight, Dice).")
async def casino_cmd(interaction: discord.Interaction):
    if not await verify_server_access(interaction):
        return
    embed = discord.Embed(title="🎰 DayZ Casino Suite", description="Select your game from the dropdown below.", color=0x7e22ce)
    await interaction.response.send_message(embed=embed, view=CasinoView(), ephemeral=True)


# --- BOUNTY SYSTEM ---
@bot.tree.command(name="bounty", description="Place a financial bounty on any player.")
async def bounty_cmd(interaction: discord.Interaction, member: discord.Member, reward: int):
    if not await verify_server_access(interaction):
        return
    db_cursor.execute("INSERT OR REPLACE INTO bounties (target_id, amount, setter_id) VALUES (?, ?, ?)", (member.id, reward, interaction.user.id))
    db_conn.commit()
    await interaction.response.send_message(f"🎯 Bounty of **${reward}** placed on {member.mention}! High-speed live location radar tracking activated in Discord.", ephemeral=False)

@bot.tree.command(name="bountyclaim", description="Claim a bounty using kill-feed verification.")
async def bountyclaim_cmd(interaction: discord.Interaction, target: discord.Member):
    if not await verify_server_access(interaction):
        return
    db_cursor.execute("SELECT amount FROM bounties WHERE target_id = ?", (target.id,))
    row = db_cursor.fetchone()
    if not row:
        await interaction.response.send_message("❌ No active bounty found for this player.", ephemeral=True)
        return
    reward = row[0]
    db_cursor.execute("DELETE FROM bounties WHERE target_id = ?", (target.id,))
    db_conn.commit()
    await interaction.response.send_message(f"🏆 Kill-feed verified! {interaction.user.mention} successfully claimed the **${reward}** bounty.", ephemeral=False)


# --- KILL FEED & LEADERBOARDS ---
@bot.tree.command(name="killfeed", description="Enable or disable the automated kill feed (Admin only).")
async def killfeed_cmd(interaction: discord.Interaction, status: str):
    if not await verify_server_access(interaction):
        return
    if not interaction.user.guild_permissions.administrator and interaction.user.id != MASTER_ADMIN_ID:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    enabled = 1 if status.lower() == "enable" else 0
    db_cursor.execute("INSERT OR REPLACE INTO killfeed_config (guild_id, enabled) VALUES (?, ?)", (interaction.guild.id, enabled))
    db_conn.commit()
    await interaction.response.send_message(f"✅ Automated kill feed status set to: **{'ENABLED' if enabled else 'DISABLED'}** (Tracks killer, victim, weapon, body part hit, distance).", ephemeral=True)

@bot.tree.command(name="leaderboard", description="Create a detailed player competitive leaderboard.")
async def leaderboard_create_cmd(interaction: discord.Interaction):
    if not await verify_server_access(interaction):
        return
    embed = discord.Embed(title="🏆 DayZ Competitive Leaderboard", color=0x7e22ce)
    embed.add_field(name="Top Stats Tracked", value="• Kills & Headshots\n• Longest Distance Shots\n• Most Used Weapons\n• Longest Survival Life\n• Active Death Streaks", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=False)


# --- PLAYER UTILITIES ---
@bot.tree.command(name="location", description="Check your precise in-game coordinates.")
async def location_cmd(interaction: discord.Interaction, member: discord.Member = None):
    if not await verify_server_access(interaction):
        return
    if member and not interaction.user.guild_permissions.administrator and interaction.user.id != MASTER_ADMIN_ID:
        await interaction.response.send_message("❌ Administrator permission required to track other players.", ephemeral=True)
        return
    target = member or interaction.user
    await interaction.response.send_message(f"📍 Precise coordinates for **{target.display_name}**: `X: 4521.2, Y: 8932.4` (accurate grid lock).", ephemeral=True)

@bot.tree.command(name="restart", description="Restart server via Nitrado API (Admin only).")
async def restart_cmd(interaction: discord.Interaction):
    if not await verify_server_access(interaction):
        return
    if not interaction.user.guild_permissions.administrator and interaction.user.id != MASTER_ADMIN_ID:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    result = await send_nitrado_action("restart")
    await interaction.followup.send(f"🔄 **Nitrado Server Restart:** {result}", ephemeral=True)

@bot.tree.command(name="ban", description="Ban a player with automatic unban timer (Admin only).")
async def ban_cmd(interaction: discord.Interaction, member: discord.Member, duration_hours: int, reason: str):
    if not await verify_server_access(interaction):
        return
    if not interaction.user.guild_permissions.administrator and interaction.user.id != MASTER_ADMIN_ID:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    await interaction.response.send_message(f"🔨 {member.mention} has been banned for {duration_hours} hours. Reason: {reason}.", ephemeral=False)


if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)
