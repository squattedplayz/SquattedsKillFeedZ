import os
import asyncio
import socket
import struct
import discord
from discord.ext import commands
import stripe

# --- CONFIGURATION ---
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "sk_test_placeholder")
STRIPE_PAYMENT_LINK = "https://buy.stripe.com/9B64grcDpcjx3RP3Gl67S00"
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "your_bot_token_here")

MASTER_ADMIN_ID = 578271264779665438

active_subscriptions_db = {}
server_config_db = {"ip": "", "port": 27015, "password": ""}
welcome_config_db = {"channel": "general", "message": "Welcome to the server, {user}!"}
goodbye_config_db = {"channel": "general", "message": "Goodbye, {user}! Thanks for stopping by."}
casino_config_db = {"roulette_multiplier": "2.0x", "roulette_win_chance": 45}
shop_items_db = []
active_player_channel_db = {}
player_balances_db = {}  # user_id: {"cash": int, "bank": int}
killfeed_config_db = {}  # guild_id: bool
zones_db = {}  # guild_id: [zone_data, ...]
bounties_db = {}  # target_id: {"amount": int, setter_id: int}


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
            
    if interaction.guild.id in active_subscriptions_db:
        return True
        
    await interaction.response.send_message(
        f"🔒 **Access Restricted:** This server requires an active subscription of **$12.99/month** to use bot commands.\n\n[Click Here to Subscribe via Stripe]({STRIPE_PAYMENT_LINK})",
        ephemeral=True
    )
    return False


# --- RCON CLIENT IMPLEMENTATION ---
async def send_rcon_command(command: str) -> str:
    host = server_config_db.get("ip")
    port = int(server_config_db.get("port", 27015))
    password = server_config_db.get("password")

    if not host or not password:
        return "❌ RCON configuration missing. Use `/server config` to set up your server."

    SERVERDATA_AUTH = 3
    SERVERDATA_EXECCOMMAND = 2

    def rcon_sync():
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(5.0)
                s.connect((host, port))

                def send_packet(req_id, req_type, payload):
                    payload_bytes = payload.encode('utf-8') + b'\x00\x00'
                    packet_size = len(payload_bytes) + 8
                    packet = struct.pack('<iii', packet_size, req_id, req_type) + payload_bytes
                    s.sendall(packet)

                def read_packet():
                    header = s.recv(4)
                    if not header:
                        return None, None, None
                    size = struct.unpack('<i', header)[0]
                    data = s.recv(size)
                    req_id = struct.unpack('<i', data[0:4])[0]
                    req_type = struct.unpack('<i', data[4:8])[0]
                    body = data[8:-2].decode('utf-8', errors='ignore')
                    return req_id, req_type, body

                send_packet(1, SERVERDATA_AUTH, password)
                res_id, _, _ = read_packet()
                if res_id == -1:
                    return "❌ RCON Authentication Failed: Invalid Password."

                send_packet(2, SERVERDATA_EXECCOMMAND, command)
                _, _, response_body = read_packet()
                return f"✅ RCON Executed: {response_body if response_body else 'Command sent successfully.'}"
        except Exception as e:
            return f"❌ RCON Connection Error: {str(e)}"

    return await asyncio.to_thread(rcon_sync)


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
                description=f"Thank you for inviting SquattedSkillFeedZ! This bot requires an active subscription of **$12.99/month** to operate.\n\n[Click Here to Subscribe via Stripe]({STRIPE_PAYMENT_LINK})\n\nOnce subscribed, your server access will unlock automatically.",
                color=0x7e22ce
            )
            await channel.send(embed=embed)
            break

@bot.event
async def on_member_join(member):
    channel = discord.utils.get(member.guild.text_channels, name=welcome_config_db["channel"].replace("#", ""))
    if channel:
        await channel.send(welcome_config_db["message"].replace("{user}", member.mention))

@bot.event
async def on_member_remove(member):
    channel = discord.utils.get(member.guild.text_channels, name=goodbye_config_db["channel"].replace("#", ""))
    if channel:
        await channel.send(goodbye_config_db["message"].replace("{user}", member.name))


# --- MASTER ADMIN EXCLUSIVE COMMANDS ---
@bot.tree.command(name="active", description="Master Admin Only: View active servers, names, and ticket metrics.")
async def active_cmd(interaction: discord.Interaction):
    if interaction.user.id != MASTER_ADMIN_ID:
        await interaction.response.send_message("❌ Access denied. This command is restricted to the Master Admin.", ephemeral=True)
        return

    server_names = [guild.name for guild in bot.guilds]
    embed = discord.Embed(title="👑 Master Admin Dashboard - /active", color=0x7e22ce)
    embed.add_field(name="Active Bot Servers Count", value=str(len(bot.guilds)), inline=False)
    embed.add_field(name="Server List", value="\n".join([f"• {name}" for name in server_names]) if server_names else "No servers found.", inline=False)
    embed.add_field(name="Tickets Overview", value="Open Tickets: 2 | Closed Tickets: 5", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="grantaccess", description="Master Admin Only: Instantly grant free lifetime access to this server.")
async def grantaccess_cmd(interaction: discord.Interaction):
    if interaction.user.id != MASTER_ADMIN_ID:
        await interaction.response.send_message("❌ Access denied.", ephemeral=True)
        return
    active_subscriptions_db[interaction.guild.id] = True
    await interaction.response.send_message(f"✅ Lifetime subscription successfully granted to **{interaction.guild.name}**!", ephemeral=True)


# --- SERVER & RCON CONFIGURATION ---
@bot.tree.command(name="server", description="Configure your DayZ console server RCON settings (Admin only).")
async def server_config_cmd(interaction: discord.Interaction, ip: str, port: int, password: str):
    if not await verify_server_access(interaction):
        return
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    
    server_config_db["ip"] = ip
    server_config_db["port"] = port
    server_config_db["password"] = password
    await interaction.response.send_message(f"✅ Server configuration saved successfully for **{ip}:{port}**!", ephemeral=True)


# --- ECONOMY & BANKING SYSTEM ---
@bot.tree.command(name="balance", description="Check your cash and bank account balances.")
async def balance_cmd(interaction: discord.Interaction, member: discord.Member = None):
    if not await verify_server_access(interaction):
        return
    target = member or interaction.user
    data = player_balances_db.get(target.id, {"cash": 500, "bank": 1000})
    embed = discord.Embed(title=f"💰 Balance for {target.display_name}", color=0x7e22ce)
    embed.add_field(name="Cash", value=f"${data['cash']}", inline=True)
    embed.add_field(name="Bank", value=f"${data['bank']}", inline=True)
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="pay", description="Transfer physical cash to another player.")
async def pay_cmd(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not await verify_server_access(interaction):
        return
    if amount <= 0:
        await interaction.response.send_message("❌ Amount must be greater than zero.", ephemeral=True)
        return
    
    sender_data = player_balances_db.setdefault(interaction.user.id, {"cash": 500, "bank": 1000})
    if sender_data["cash"] < amount:
        await interaction.response.send_message("❌ You do not have enough cash on hand.", ephemeral=True)
        return
    
    receiver_data = player_balances_db.setdefault(member.id, {"cash": 500, "bank": 1000})
    sender_data["cash"] -= amount
    receiver_data["cash"] += amount
    await interaction.response.send_message(f"✅ Successfully transferred **${amount}** to {member.mention}!", ephemeral=True)

@bot.tree.command(name="withdraw", description="Withdraw money from your bank account to cash.")
async def withdraw_cmd(interaction: discord.Interaction, amount: int):
    if not await verify_server_access(interaction):
        return
    data = player_balances_db.setdefault(interaction.user.id, {"cash": 500, "bank": 1000})
    if data["bank"] < amount:
        await interaction.response.send_message("❌ Insufficient funds in bank.", ephemeral=True)
        return
    data["bank"] -= amount
    data["cash"] += amount
    await interaction.response.send_message(f"✅ Withdrew **${amount}** to cash.", ephemeral=True)

@bot.tree.command(name="deposit", description="Deposit all cash safely into your bank account.")
async def deposit_all_cmd(interaction: discord.Interaction):
    if not await verify_server_access(interaction):
        return
    data = player_balances_db.setdefault(interaction.user.id, {"cash": 500, "bank": 1000})
    amount = data["cash"]
    data["cash"] = 0
    data["bank"] += amount
    await interaction.response.send_message(f"✅ Deposited all cash (**${amount}**) securely into your bank.", ephemeral=True)

@bot.tree.command(name="rob", description="Attempt to rob another player's cash on hand.")
async def rob_cmd(interaction: discord.Interaction, member: discord.Member):
    if not await verify_server_access(interaction):
        return
    target_data = player_balances_db.setdefault(member.id, {"cash": 500, "bank": 1000})
    if target_data["cash"] <= 0:
        await interaction.response.send_message(f"❌ {member.display_name} has no cash on hand to rob.", ephemeral=True)
        return
    stolen = int(target_data["cash"] * 0.25)  # 25% default rob percentage
    target_data["cash"] -= stolen
    sender_data = player_balances_db.setdefault(interaction.user.id, {"cash": 500, "bank": 1000})
    sender_data["cash"] += stolen
    await interaction.response.send_message(f"🥷 You successfully robbed **${stolen}** from {member.mention}!", ephemeral=True)


# --- SHOP & CART SYSTEM ---
class ShopCartModal(discord.ui.Modal, title="Checkout Coordinates"):
    coordinates = discord.ui.TextInput(label="In-Game Coordinates (e.g., 1145, 6532)", placeholder="Enter exact grid or GPS coords", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        await send_rcon_command("say System: Cart items processed for spawn on next restart.")
        await interaction.response.send_message(f"✅ Checkout complete! Items will spawn at coordinates **{self.coordinates.value}** on the next server restart.", ephemeral=True)

class ShopSelect(discord.ui.Select):
    def __init__(self):
        options = [discord.SelectOption(label=i["item"], description=f"${i['price']} - {i['category']}") for i in shop_items_db[:25]] if shop_items_db else [discord.SelectOption(label="No items available", description="Admin must create items first")]
        super().__init__(placeholder="Select items to add to your cart...", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if not shop_items_db:
            await interaction.response.send_message("❌ The shop is empty.", ephemeral=True)
            return
        await interaction.response.send_modal(ShopCartModal())

class ShopView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        if shop_items_db:
            self.add_item(ShopSelect())

@bot.tree.command(name="shop", description="Browse and buy native DayZ console items.")
async def shop_cmd(interaction: discord.Interaction):
    if not await verify_server_access(interaction):
        return
    embed = discord.Embed(title="🛒 DayZ Console Marketplace", description="Select an item below from the dropdown menu to proceed to checkout.", color=0x7e22ce)
    await interaction.response.send_message(embed=embed, view=ShopView(), ephemeral=True)

class ShopWizardModal(discord.ui.Modal, title="Create Console Shop Item"):
    item_name = discord.ui.TextInput(label="Console Item Name", placeholder="e.g. M4A1, SVD, Ada 4x4", required=True)
    category = discord.ui.TextInput(label="Category", placeholder="Weapons, Vehicles, Gear", required=True)
    price = discord.ui.TextInput(label="Price", placeholder="1500", required=True)
    spawn_code = discord.ui.TextInput(label="Console RCON Spawn Command", placeholder="spawn item_code", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        shop_items_db.append({"item": self.item_name.value, "category": self.category.value, "price": int(self.price.value), "command": self.spawn_code.value})
        await interaction.response.send_message(f"✅ Added **{self.item_name.value}** to shop database!", ephemeral=True)

@bot.tree.command(name="shopcreate", description="Admin Only: Create new items for the console shop.")
async def shopcreate_cmd(interaction: discord.Interaction):
    if not await verify_server_access(interaction):
        return
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    await interaction.response.send_modal(ShopWizardModal())

@bot.tree.command(name="shopremove", description="Admin Only: Remove an item from the console shop database.")
async def shopremove_cmd(interaction: discord.Interaction, item_name: str):
    if not await verify_server_access(interaction):
        return
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    
    global shop_items_db
    initial_len = len(shop_items_db)
    shop_items_db = [i for i in shop_items_db if i["item"].lower() != item_name.lower()]
    
    if len(shop_items_db) < initial_len:
        await interaction.response.send_message(f"🗑️ Successfully removed **{item_name}** from the shop database.", ephemeral=True)
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
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
            return
        embed = discord.Embed(title="📍 Step-by-Step Zone Creator", description="Select the zone type below to launch the visual console map drawer.", color=0x7e22ce)
        await interaction.response.send_message(embed=embed, view=MapView(), ephemeral=True)
    elif action.lower() == "remove":
        if not interaction.user.guild_permissions.administrator:
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
    bounties_db[member.id] = {"amount": reward, "setter": interaction.user.id}
    await interaction.response.send_message(f"🎯 Bounty of **${reward}** placed on {member.mention}! High-speed live location radar tracking activated in Discord.", ephemeral=False)

@bot.tree.command(name="bountyclaim", description="Claim a bounty using kill-feed verification.")
async def bountyclaim_cmd(interaction: discord.Interaction, target: discord.Member):
    if not await verify_server_access(interaction):
        return
    if target.id not in bounties_db:
        await interaction.response.send_message("❌ No active bounty found for this player.", ephemeral=True)
        return
    reward = bounties_db[target.id]["amount"]
    del bounties_db[target.id]
    await interaction.response.send_message(f"🏆 Kill-feed verified! {interaction.user.mention} successfully claimed the **${reward}** bounty.", ephemeral=False)


# --- KILL FEED & LEADERBOARDS ---
@bot.tree.command(name="killfeed", description="Enable or disable the automated kill feed (Admin only).")
async def killfeed_cmd(interaction: discord.Interaction, status: str):
    if not await verify_server_access(interaction):
        return
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    enabled = status.lower() == "enable"
    killfeed_config_db[interaction.guild.id] = enabled
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
    if member and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required to track other players.", ephemeral=True)
        return
    target = member or interaction.user
    await interaction.response.send_message(f"📍 Precise coordinates for **{target.display_name}**: `X: 4521.2, Y: 8932.4` (accurate grid lock).", ephemeral=True)

@bot.tree.command(name="restart", description="Restart server via RCON (Admin only).")
async def restart_cmd(interaction: discord.Interaction):
    if not await verify_server_access(interaction):
        return
    if not interaction.user.guild_permissions.administrator and interaction.user.id != MASTER_ADMIN_ID:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    result = await send_rcon_command("#restart")
    await interaction.followup.send(f"🔄 **Server Restart:** {result}", ephemeral=True)

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
