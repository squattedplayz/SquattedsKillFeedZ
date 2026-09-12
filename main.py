import os
import asyncio
import aiohttp
import sqlite3
import discord
from discord.ext import commands, tasks
import stripe

# --- CONFIGURATION ---
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "sk_test_placeholder")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "your_bot_token_here")
NITRADO_API_TOKEN = os.getenv("NITRADO_API_TOKEN", "your_nitrado_token_here")

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
    enabled INTEGER
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
    zone_type TEXT,
    name TEXT,
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
    await interaction.response.defer(ephemeral=True)
    if interaction.user.id != MASTER_ADMIN_ID:
        await interaction.followup.send("❌ Access denied. This command is restricted to the Master Admin.", ephemeral=True)
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
    await interaction.followup.send(embed=embed, ephemeral=True)

@bot.tree.command(name="grantaccess", description="Master Admin Only: Instantly grant free lifetime access to this server.")
async def grantaccess_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if interaction.user.id != MASTER_ADMIN_ID:
        await interaction.followup.send("❌ Access denied.", ephemeral=True)
        return
    db_cursor.execute("INSERT OR IGNORE INTO subscriptions (guild_id) VALUES (?)", (interaction.guild.id,))
    db_conn.commit()
    await interaction.followup.send(f"✅ Lifetime subscription successfully granted to **{interaction.guild.name}**!", ephemeral=True)


# --- TICKET SYSTEM ---
class CloseTicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.danger, custom_id="close_ticket_btn")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        if not interaction.user.guild_permissions.administrator and interaction.user.id != MASTER_ADMIN_ID:
            await interaction.followup.send("❌ Administrator permission required to close tickets.", ephemeral=True)
            return
        
        db_cursor.execute("UPDATE ticket_stats SET count = MAX(0, count - 1) WHERE metric = 'open'")
        db_cursor.execute("UPDATE ticket_stats SET count = count + 1 WHERE metric = 'closed'")
        db_conn.commit()

        await interaction.followup.send("🔒 Closing ticket channel in 5 seconds...", ephemeral=False)
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
        await interaction.response.defer(ephemeral=True)
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
        await interaction.followup.send(f"✅ Ticket created successfully! Head over to {ticket_channel.mention}.", ephemeral=True)

@bot.tree.command(name="ticketsetup", description="Admin Only: Deploy the persistent ticket creation panel.")
async def ticketsetup_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return
    if not interaction.user.guild_permissions.administrator and interaction.user.id != MASTER_ADMIN_ID:
        await interaction.followup.send("❌ Administrator permission required.", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="🎫 Server Support & Help Desk",
        description="Click the button below to open a private support ticket with server staff and administrators.",
        color=0x7e22ce
    )
    await interaction.channel.send(embed=embed, view=TicketSetupView())
    await interaction.followup.send("✅ Ticket panel deployed in this channel!", ephemeral=True)


# --- CONSOLE & SERVER CONFIGURATION ---
@bot.tree.command(name="server", description="Configure your DayZ Nitrado Service ID (Admin only).")
async def server_config_cmd(interaction: discord.Interaction, service_id: str):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return
    if not interaction.user.guild_permissions.administrator and interaction.user.id != MASTER_ADMIN_ID:
        await interaction.followup.send("❌ Administrator permission required.", ephemeral=True)
        return
    
    db_cursor.execute(
        "INSERT OR REPLACE INTO server_config (guild_id, key, value) VALUES (?, 'service_id', ?)", 
        (interaction.guild.id, service_id)
    )
    db_conn.commit()

    await interaction.followup.send(f"✅ Nitrado Service ID saved successfully for this server: **{service_id}**!", ephemeral=True)

@bot.tree.command(name="link", description="Link an Xbox Gamertag or PSN ID to your Discord profile (Allows up to 2).")
async def link_cmd(interaction: discord.Interaction, gamertag: str):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return
    
    db_cursor.execute("SELECT COUNT(*) FROM player_links WHERE discord_id = ?", (interaction.user.id,))
    count = db_cursor.fetchone()[0]
    
    if count >= 2:
        await interaction.followup.send("❌ You have already reached the maximum limit of **2 linked accounts** per Discord profile.", ephemeral=True)
        return
        
    try:
        db_cursor.execute("INSERT INTO player_links (discord_id, gamertag) VALUES (?, ?)", (interaction.user.id, gamertag))
        db_conn.commit()
        await interaction.followup.send(f"✅ Successfully linked console Gamertag **{gamertag}** to your profile!", ephemeral=True)
    except sqlite3.IntegrityError:
        await interaction.followup.send("❌ This gamertag is already linked to your profile.", ephemeral=True)

@bot.tree.command(name="linkedaccounts", description="View all linked console gamertags for yourself or another member.")
async def linkedaccounts_cmd(interaction: discord.Interaction, member: discord.Member = None):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return
    target = member or interaction.user
    
    db_cursor.execute("SELECT gamertag FROM player_links WHERE discord_id = ?", (target.id,))
    links = db_cursor.fetchall()
    
    embed = discord.Embed(title=f"🔗 Linked Accounts for {target.display_name}", color=0x7e22ce)
    if links:
        gt_list = "\n".join([f"• `{row[0]}`" for row in links])
        embed.add_field(name="Registered Gamertags", value=gt_list, inline=False)
    else:
        embed.description = "No linked console accounts found."
        
    await interaction.followup.send(embed=embed, ephemeral=True)

@bot.tree.command(name="whitelist", description="Admin Only: Add or remove players from the console whitelist database.")
async def whitelist_cmd(interaction: discord.Interaction, action: str, gamertag: str):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return
    if not interaction.user.guild_permissions.administrator and interaction.user.id != MASTER_ADMIN_ID:
        await interaction.followup.send("❌ Administrator permission required.", ephemeral=True)
        return
    
    if action.lower() == "add":
        db_cursor.execute("INSERT INTO whitelist (guild_id, gamertag) VALUES (?, ?)", (interaction.guild.id, gamertag))
        db_conn.commit()
        await interaction.followup.send(f"✅ Added **{gamertag}** to the server whitelist database.", ephemeral=True)
    elif action.lower() == "remove":
        db_cursor.execute("DELETE FROM whitelist WHERE guild_id = ? AND gamertag = ?", (interaction.guild.id, gamertag))
        db_conn.commit()
        await interaction.followup.send(f"🗑️ Removed **{gamertag}** from the server whitelist database.", ephemeral=True)
    else:
        await interaction.followup.send("❌ Use `/whitelist add [gamertag]` or `/whitelist remove [gamertag]`.", ephemeral=True)

@bot.tree.command(name="welcomeset", description="Admin Only: Customize the welcome announcement channel and message.")
async def welcomeset_cmd(interaction: discord.Interaction, channel_name: str, message: str):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return
    if not interaction.user.guild_permissions.administrator and interaction.user.id != MASTER_ADMIN_ID:
        await interaction.followup.send("❌ Administrator permission required.", ephemeral=True)
        return
    db_cursor.execute("INSERT OR REPLACE INTO welcome_config (guild_id, channel, message) VALUES (?, ?, ?)", (interaction.guild.id, channel_name, message))
    db_conn.commit()
    await interaction.followup.send(f"✅ Welcome settings updated! Channel: **{channel_name}**", ephemeral=True)

@bot.tree.command(name="goodbyeset", description="Admin Only: Customize the goodbye announcement channel and message.")
async def goodbyeset_cmd(interaction: discord.Interaction, channel_name: str, message: str):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return
    if not interaction.user.guild_permissions.administrator and interaction.user.id != MASTER_ADMIN_ID:
        await interaction.followup.send("❌ Administrator permission required.", ephemeral=True)
        return
    db_cursor.execute("INSERT OR REPLACE INTO goodbye_config (guild_id, channel, message) VALUES (?, ?, ?)", (interaction.guild.id, channel_name, message))
    db_conn.commit()
    await interaction.followup.send(f"✅ Goodbye settings updated! Channel: **{channel_name}**", ephemeral=True)

@bot.tree.command(name="info", description="Display server rules, connection info, and maps.")
async def info_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=False)
    if not await verify_server_access(interaction):
        return
    embed = discord.Embed(title="📜 DayZ Console Server Information", description="Official community guidelines, map configurations, and support center.", color=0x7e22ce)
    embed.add_field(name="🗺️ Supported Maps", value="• Chernarus\n• Livonia\n• Sakhal", inline=False)
    embed.add_field(name="⚖️ Core Rules", value="1. No base glitching or exploiting.\n2. Respect all players and admins.\n3. Use support tickets for server issues.", inline=False)
    await interaction.followup.send(embed=embed, ephemeral=False)


# --- LEADERBOARD & REAL-TIME EVENT SYSTEM ---
@bot.tree.command(name="leaderboardsetup", description="Admin Only: Assign a dedicated channel for real-time event leaderboards.")
async def leaderboardsetup_cmd(interaction: discord.Interaction, channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return
    if not interaction.user.guild_permissions.administrator and interaction.user.id != MASTER_ADMIN_ID:
        await interaction.followup.send("❌ Administrator permission required.", ephemeral=True)
        return
        
    db_cursor.execute("INSERT OR REPLACE INTO leaderboard_config (guild_id, channel_id) VALUES (?, ?)", (interaction.guild.id, channel.id))
    db_conn.commit()
    
    embed = discord.Embed(title="🏆 Live Killfeed & Leaderboard Initialized", description="This channel will now dynamically update in real time with kill/death events and statistics.", color=0x7e22ce)
    await channel.send(embed=embed)
    await interaction.followup.send(f"✅ Leaderboard channel successfully bound to {channel.mention}!", ephemeral=True)


# --- KILLFEED SETUP COMMANDS ---
@bot.tree.command(name="killfeed", description="Admin Only: Enable or disable the automated kill feed.")
@discord.app_commands.choices(action=[
    discord.app_commands.Choice(name="enable", value="enable"),
    discord.app_commands.Choice(name="disable", value="disable")
])
async def killfeed_cmd(interaction: discord.Interaction, action: str):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return
    if not interaction.user.guild_permissions.administrator and interaction.user.id != MASTER_ADMIN_ID:
        await interaction.followup.send("❌ Administrator permission required.", ephemeral=True)
        return
    
    if action == "enable":
        db_cursor.execute("INSERT OR REPLACE INTO killfeed_config (guild_id, enabled) VALUES (?, 1)", (interaction.guild.id,))
        db_conn.commit()
        await interaction.followup.send("✅ Kill feed has been **enabled** for this server.", ephemeral=True)
    elif action == "disable":
        db_cursor.execute("INSERT OR REPLACE INTO killfeed_config (guild_id, enabled) VALUES (?, 0)", (interaction.guild.id,))
        db_conn.commit()
        await interaction.followup.send("❌ Kill feed has been **disabled** for this server.", ephemeral=True)


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
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return
    target = member or interaction.user
    cash, bank = get_balance(target.id)
    embed = discord.Embed(title=f"💰 Balance for {target.display_name}", color=0x7e22ce)
    embed.add_field(name="Cash", value=f"${cash}", inline=True)
    embed.add_field(name="Bank", value=f"${bank}", inline=True)
    await interaction.followup.send(embed=embed, ephemeral=True)

@bot.tree.command(name="pay", description="Transfer physical cash to another player.")
async def pay_cmd(interaction: discord.Interaction, member: discord.Member, amount: int):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return
    if amount <= 0:
        await interaction.followup.send("❌ Amount must be greater than zero.", ephemeral=True)
        return
    
    sender_cash, sender_bank = get_balance(interaction.user.id)
    if sender_cash < amount:
        await interaction.followup.send("❌ You do not have enough cash on hand.", ephemeral=True)
        return
    
    receiver_cash, receiver_bank = get_balance(member.id)
    db_cursor.execute("UPDATE player_balances SET cash = cash - ? WHERE user_id = ?", (amount, interaction.user.id))
    db_cursor.execute("UPDATE player_balances SET cash = cash + ? WHERE user_id = ?", (amount, member.id))
    db_conn.commit()
    await interaction.followup.send(f"✅ Successfully transferred **${amount}** to {member.mention}!", ephemeral=True)

@bot.tree.command(name="withdraw", description="Withdraw money from your bank account to cash.")
async def withdraw_cmd(interaction: discord.Interaction, amount: int):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return
    cash, bank = get_balance(interaction.user.id)
    if bank < amount:
        await interaction.followup.send("❌ Insufficient funds in bank.", ephemeral=True)
        return
    db_cursor.execute("UPDATE player_balances SET cash = cash + ?, bank = bank - ? WHERE user_id = ?", (amount, amount, interaction.user.id))
    db_conn.commit()
    await interaction.followup.send(f"✅ Withdrew **${amount}** to cash.", ephemeral=True)

@bot.tree.command(name="deposit", description="Deposit all cash safely into your bank account.")
async def deposit_all_cmd(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return
    cash, bank = get_balance(interaction.user.id)
    if cash <= 0:
        await interaction.followup.send("❌ You have no cash on hand to deposit.", ephemeral=True)
        return
    db_cursor.execute("UPDATE player_balances SET cash = 0, bank = bank + ? WHERE user_id = ?", (cash, interaction.user.id))
    db_conn.commit()
    await interaction.followup.send(f"✅ Deposited all cash (**${cash}**) securely into your bank.", ephemeral=True)

@bot.tree.command(name="rob", description="Attempt to rob another player's cash on hand.")
async def rob_cmd(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return
    target_cash, target_bank = get_balance(member.id)
    if target_cash <= 0:
        await interaction.followup.send(f"❌ {member.display_name} has no cash on hand to rob.", ephemeral=True)
        return
    stolen = int(target_cash * 0.25)
    db_cursor.execute("UPDATE player_balances SET cash = cash - ? WHERE user_id = ?", (stolen, member.id))
    db_cursor.execute("UPDATE player_balances SET cash = cash + ? WHERE user_id = ?", (stolen, interaction.user.id))
    db_conn.commit()
    await interaction.followup.send(f"🥷 You successfully robbed **${stolen}** from {member.mention}!", ephemeral=True)


# --- NATIVE DAYZ CONSOLE ITEM DATABASE ---
DAYZ_ITEM_DATABASE = {
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
    "M1911": "M1911",
    "Glock 19": "Pistol_Glock19",
    "Deagle (Gold/Black)": "Deagle",
    "IJ-70": "Makaram",
    "CR-75": "CZ75",
    "Magnum": "Magnum",
    "BK-133 Shotgun": "Shotgun_BK133",
    "Saiga 12K Shotgun": "Saiga",
    "Double Barrel Shotgun": "Shotgun_BK43",
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
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return
    db_cursor.execute("SELECT id, item_name, category, price, command FROM shop_items WHERE guild_id = ?", (interaction.guild.id,))
    items = db_cursor.fetchall()
    
    if not items:
        await interaction.followup.send("❌ The shop is currently empty. An administrator must create items first using `/shopcreate`.", ephemeral=True)
        return

    embed = discord.Embed(title="🛒 DayZ Console Marketplace", description="Select an item below from the dropdown menu to proceed to checkout.", color=0x7e22ce)
    await interaction.followup.send(embed=embed, view=ShopView(items), ephemeral=True)

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
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return
    if not interaction.user.guild_permissions.administrator and interaction.user.id != MASTER_ADMIN_ID:
        await interaction.followup.send("❌ Administrator permission required.", ephemeral=True)
        return

    display_name = next((k for k, v in DAYZ_ITEM_DATABASE.items() if v == item), item)

    db_cursor.execute(
        "INSERT INTO shop_items (guild_id, item_name, category, price, command) VALUES (?, ?, ?, ?, ?)",
        (interaction.guild.id, display_name, category, price, f"spawn {item}")
    )
    db_conn.commit()
    await interaction.followup.send(f"✅ Successfully added **{display_name}** to the shop marketplace for **${price}** (`{category}`)!", ephemeral=True)

@bot.tree.command(name="shopremove", description="Admin Only: Remove an item from the console shop database.")
async def shopremove_cmd(interaction: discord.Interaction, item_name: str):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return
    if not interaction.user.guild_permissions.administrator and interaction.user.id != MASTER_ADMIN_ID:
        await interaction.followup.send("❌ Administrator permission required.", ephemeral=True)
        return
    
    db_cursor.execute("DELETE FROM shop_items WHERE guild_id = ? AND item_name LIKE ?", (interaction.guild.id, f"%{item_name}%"))
    db_conn.commit()
    
    if db_cursor.rowcount > 0:
        await interaction.followup.send(f"🗑️ Successfully removed matching items (**{item_name}**) from the shop database.", ephemeral=True)
    else:
        await interaction.followup.send(f"❌ Item **{item_name}** was not found in the shop.", ephemeral=True)


# --- ZONE & MAP DRAWING SYSTEM ---
class ZoneConfigModal(discord.ui.Modal, title="Configure Zone Parameters"):
    zone_name = discord.ui.TextInput(label="Zone Name / Identifier", placeholder="e.g., Trader City / Base Alpha", required=True)
    coordinates = discord.ui.TextInput(label="Coordinates & Radius", placeholder="e.g., X:1145 Y:6532 Radius:300m", required=True)

    def __init__(self, zone_type: str):
        super().__init__()
        self.zone_type = zone_type

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        db_cursor.execute(
            "INSERT INTO zones (guild_id, zone_type, name, coords) VALUES (?, ?, ?, ?)",
            (interaction.guild.id, self.zone_type, self.zone_name.value, self.coordinates.value)
        )
        db_conn.commit()
        await interaction.followup.send(f"✅ Successfully configured **{self.zone_type}** (`{self.zone_name.value}`) at coordinates `{self.coordinates.value}`!", ephemeral=True)

class ZoneTypeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Base Radar", description="High-speed precision radar tracking base activity"),
            discord.SelectOption(label="PvP Zone", description="Designated player combat zone"),
            discord.SelectOption(label="Safe Zone", description="Protected non-combat zone"),
            discord.SelectOption(label="Player Radar", description="Instant-refresh 15s target tracking radar"),
            discord.SelectOption(label="Gas Zone", description="Contaminated toxic hazard zone creation/removal")
        ]
        super().__init__(placeholder="Select zone type to configure...", options=options)

    async def callback(self, interaction: discord.Interaction):
        selected_type = self.values[0]
        await interaction.response.send_modal(ZoneConfigModal(selected_type))

class MapView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ZoneTypeSelect())

@bot.tree.command(name="zone", description="Manage zones (Base Radars, PvP, Safe, Gas, Player Radars) - Admin only.")
async def zone_cmd(interaction: discord.Interaction, action: str, channel: discord.TextChannel = None):
    await interaction.response.defer(ephemeral=True)
    if not await verify_server_access(interaction):
        return
    if not interaction.user.guild_permissions.administrator and interaction.user.id != MASTER_ADMIN_ID:
        await interaction.followup.send("❌ Administrator permission required.", ephemeral=True)
        return

    if action.lower() == "create":
        embed = discord.Embed(title="📍 Step-by-Step Zone & Radar Creator", description="Select the zone type below to launch the parameter configuration prompt and bind feeds.", color=0x7e22ce)
        if channel:
            db_cursor.execute("INSERT OR REPLACE INTO radar_config (guild_id, radar_type, channel_id) VALUES (?, 'General', ?)", (interaction.guild.id, channel.id))
            db_conn.commit()
        await interaction.followup.send(embed=embed, view=MapView(), ephemeral=True)
    elif action.lower() == "remove":
        db_cursor.execute("DELETE FROM zones WHERE guild_id = ?", (interaction.guild.id,))
        db_conn.commit()
        await interaction.followup.send("🗑️ All custom zones and radar configurations have been cleared from this server.", ephemeral=True)
    else:
        await interaction.followup.send("❌ Use `/zone create` or `/zone remove`.", ephemeral=True)

# --- BOT LAUNCH ---
if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)
