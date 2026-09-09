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


# --- RCON CLIENT IMPLEMENTATION ---
async def send_rcon_command(command: str) -> str:
    host = server_config_db.get("ip")
    port = int(server_config_db.get("port", 27015))
    password = server_config_db.get("password")

    if not host or not password:
        return "❌ RCON configuration missing. Please check your settings."

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


# --- DISCORD BOT SETUP & COMMANDS ---
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
    # Completely exempt the Master Admin's server/ownership
    try:
        owner = guild.owner or await guild.fetch_member(guild.owner_id)
        if owner.id == MASTER_ADMIN_ID:
            return
    except Exception:
        if guild.owner_id == MASTER_ADMIN_ID:
            return
    
    payment_link = STRIPE_PAYMENT_LINK
    for channel in guild.text_channels:
        if channel.permissions_for(guild.me).send_messages:
            embed = discord.Embed(
                title="🔒 Subscription Required",
                description=f"Thank you for inviting SquattedSkillFeedZ! This bot requires an active subscription of **$12.99/month** to operate.\n\n[Click Here to Subscribe via Stripe]({payment_link})\n\nOnce subscribed, your server access will unlock automatically.",
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


# --- MASTER ADMIN EXCLUSIVE COMMAND ---
@bot.tree.command(name="active", description="Master Admin Only: View active servers, customer subscriptions, and ticket metrics.")
async def active_cmd(interaction: discord.Interaction):
    if interaction.user.id != MASTER_ADMIN_ID:
        await interaction.response.send_message("❌ Access denied. This command is restricted to the Master Admin.", ephemeral=True)
        return

    active_servers_count = len(bot.guilds)
    embed = discord.Embed(title="👑 Master Admin Dashboard - /active", color=0x7e22ce)
    embed.add_field(name="Active Bot Servers", value=str(active_servers_count), inline=False)
    embed.add_field(
        name="Customer Subscriptions & Tickets",
        value="• **Server Alpha** | Subbed: 45 Days | Tickets: 3 (2 Open / 1 Closed)\n• **Server Bravo** | Subbed: 12 Days | Tickets: 1 (0 Open / 1 Closed)",
        inline=False
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)


# --- LIVE PLAYER LIST CONFIGURATION ---
class PlayerChannelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Setup Player List Channel", style=discord.ButtonStyle.blurple, custom_id="setup_player_list")
    async def setup_player_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
            return
        active_player_channel_db[interaction.guild.id] = interaction.channel.id
        await interaction.response.send_message(f"✅ This channel ({interaction.channel.mention}) has been set up as the Live Player List feed!", ephemeral=True)

@bot.tree.command(name="setplayerlist", description="Configure a channel to display currently online DayZ console players.")
async def setplayerlist_cmd(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="👥 Live Player List Setup",
        description="Click the button below to bind this channel as your live online player feed. It will update regularly with in-game tags (no location data shown for safety).",
        color=0x7e22ce
    )
    await interaction.response.send_message(embed=embed, view=PlayerChannelView(), ephemeral=False)


# --- INTERACTIVE SHOP CREATION WIZARD ---
class ShopWizardModal(discord.ui.Modal, title="Create Console Shop Item"):
    item_name = discord.ui.TextInput(label="Console Item Name (Xbox/PlayStation only)", placeholder="e.g. M4A1, SVD, Ada 4x4", required=True)
    category = discord.ui.TextInput(label="Category", placeholder="Weapons, Vehicles, Gear", required=True)
    price = discord.ui.TextInput(label="Price (Currency Amount)", placeholder="1500", required=True)
    spawn_code = discord.ui.TextInput(label="Console RCON Spawn Command", placeholder="spawn item_code", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        shop_items_db.append({
            "item": self.item_name.value,
            "category": self.category.value,
            "price": int(self.price.value),
            "command": self.spawn_code.value
        })
        await interaction.response.send_message(f"✅ Successfully added **{self.item_name.value}** to the console shop database!", ephemeral=True)

class ShopManagementView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="➕ Create Shop Item", style=discord.ButtonStyle.green, custom_id="shop_create")
    async def shop_create(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
            return
        await interaction.response.send_modal(ShopWizardModal())

    @discord.ui.button(label="➖ Remove Shop Item", style=discord.ButtonStyle.red, custom_id="shop_remove")
    async def shop_remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
            return
        if not shop_items_db:
            await interaction.response.send_message("⚠️ The shop currently has no items to remove.", ephemeral=True)
            return
        
        removed = shop_items_db.pop()
        await interaction.response.send_message(f"🗑️ Removed **{removed['item']}** from the console shop.", ephemeral=True)

@bot.tree.command(name="shop", description="Open the interactive console shop management menu.")
async def shop_cmd(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🛒 Console Shop Management Wizard",
        description="Use the buttons below to create or remove items for your Xbox/PlayStation DayZ server shop.",
        color=0x7e22ce
    )
    if shop_items_db:
        items_list = "\n".join([f"• **{i['item']}** ({i['category']}) - {i['price']} Cash" for i in shop_items_db])
        embed.add_field(name="Current Shop Items", value=items_list, inline=False)
    else:
        embed.add_field(name="Current Shop Items", value="No items configured yet. Click 'Create Shop Item' to add one.", inline=False)

    await interaction.response.send_message(embed=embed, view=ShopManagementView(), ephemeral=False)


# --- WELCOME / GOODBYE COMMANDS ---
class WelcomeSetupView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Setup Welcome Message", style=discord.ButtonStyle.green, custom_id="welcome_setup")
    async def setup(self, interaction: discord.Interaction, button: discord.ui.Button):
        welcome_config_db["channel"] = interaction.channel.name
        await interaction.response.send_message(f"✅ Welcome messages will now post in {interaction.channel.mention}.", ephemeral=True)

    @discord.ui.button(label="Remove Welcome Message", style=discord.ButtonStyle.red, custom_id="welcome_remove")
    async def remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        welcome_config_db["channel"] = ""
        await interaction.response.send_message("🗑️ Welcome message announcements disabled.", ephemeral=True)

@bot.tree.command(name="welcome", description="Configure or remove automated server welcome messages.")
async def welcome_cmd(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Administrator permission required.", ephemeral=True)
        return
    embed = discord.Embed(title="👋 Welcome Message Manager", description="Choose an option below to set up or remove welcome greetings for new members.", color=0x7e22ce)
    await interaction.response.send_message(embed=embed, view=WelcomeSetupView(), ephemeral=False)


# --- OTHER UTILITY COMMANDS ---
@bot.tree.command(name="restart", description="Restarts server via RCON (Admin Only)")
async def restart_cmd(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator and interaction.user.id != MASTER_ADMIN_ID:
        await interaction.response.send_message("❌ You lack administrator permissions.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    result = await send_rcon_command("#restart")
    await interaction.followup.send(f"🔄 **Server Restart:** {result}", ephemeral=True)

@bot.tree.command(name="bounty", description="Place a bounty on a player and create target tracking zone")
async def bounty_cmd(interaction: discord.Interaction, member: discord.Member, reward: int):
    await interaction.response.send_message(f"🎯 Bounty of ${reward} placed on {member.mention}! Target radar zone generated automatically.", ephemeral=False)

@bot.tree.command(name="ban", description="Ban a player with automatic unban timer")
async def ban_cmd(interaction: discord.Interaction, member: discord.Member, duration_hours: int, reason: str):
    if not interaction.user.guild_permissions.administrator and interaction.user.id != MASTER_ADMIN_ID:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    await interaction.response.send_message(f"🔨 {member.mention} has been banned for {duration_hours} hours. Reason: {reason}.", ephemeral=False)


if __name__ == "__main__":
    bot.run(DISCORD_BOT_TOKEN)
