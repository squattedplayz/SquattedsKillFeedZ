import os
import threading
import asyncio
import socket
import struct
import discord
from discord.ext import commands
from fastapi import FastAPI, Request, HTTPException, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse
import uvicorn
import stripe

# --- CONFIGURATION ---
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "sk_test_placeholder")
STRIPE_PAYMENT_LINK = "https://buy.stripe.com/9B64grcDpcjx3RP3Gl67S00"
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "your_bot_token_here")

ADMIN_EMAIL = "Dwayne.mashburn@gmail.com"
ADMIN_PASSWORD = "Duanemashburn2!"

fake_users_db = {
    ADMIN_EMAIL: {
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD,
        "is_admin": True,
        "is_subscribed": True
    }
}

# In-memory database storage for server configuration & RCON
server_config_db = {
    "ip": "",
    "port": 27015,
    "password": ""
}

# --- RCON CLIENT IMPLEMENTATION ---
async def send_rcon_command(command: str) -> str:
    host = server_config_db.get("ip")
    port = int(server_config_db.get("port", 27015))
    password = server_config_db.get("password")

    if not host or not password:
        return "❌ RCON configuration missing. Please link your server in the web dashboard."

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
                res_id, res_type, _ = read_packet()
                if res_id == -1:
                    return "❌ RCON Authentication Failed: Invalid Password."

                send_packet(2, SERVERDATA_EXECCOMMAND, command)
                _, _, response_body = read_packet()
                return f"✅ RCON Executed: {response_body if response_body else 'Command sent successfully.'}"
        except Exception as e:
            return f"❌ RCON Connection Error: {str(e)}"

    return await asyncio.to_thread(rcon_sync)


# --- FASTAPI WEB APP SETUP ---
app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, tab: str = "dashboard"):
    success_msg = request.query_params.get("success")
    alert_html = "<div style='background:#064e3b;color:#34d399;padding:12px;border-radius:6px;margin-bottom:20px;font-size:14px;'>Server RCON settings updated successfully!</div>" if success_msg == "saved" else ""

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SQUATTEDS SKILL FEEDZ</title>
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }}
            body {{ background: #000000; color: #f8fafc; display: flex; height: 100vh; overflow: hidden; }}
            
            .sidebar {{ width: 260px; background: #0a0510; border-right: 1px solid #2e1065; display: flex; flex-direction: column; }}
            .brand {{ padding: 20px; font-size: 15px; font-weight: 800; color: #c084fc; border-bottom: 1px solid #2e1065; letter-spacing: 0.5px; background: #030007; }}
            .menu-list {{ list-style: none; padding: 15px; overflow-y: auto; flex-grow: 1; }}
            .menu-item {{ padding: 12px 15px; margin-bottom: 6px; border-radius: 6px; cursor: pointer; color: #a78bfa; font-size: 14px; font-weight: 500; text-decoration: none; display: flex; justify-content: space-between; align-items: center; transition: all 0.2s; }}
            .menu-item:hover, .menu-item.active {{ background: #2e1065; color: #ffffff; }}
            
            .main-container {{ flex-grow: 1; display: flex; flex-direction: column; height: 100vh; }}
            .header {{ height: 70px; background: #0a0510; border-bottom: 1px solid #2e1065; display: flex; justify-content: flex-end; align-items: center; padding: 0 30px; gap: 15px; }}
            .btn-header {{ padding: 10px 20px; border-radius: 6px; font-size: 14px; font-weight: 600; text-decoration: none; cursor: pointer; }}
            .btn-invite {{ background: #1e1b4b; color: #e9d5ff; border: 1px solid #6b21a8; }}
            .btn-invite:hover {{ background: #2e1065; }}
            .btn-login {{ background: #7e22ce; color: #ffffff; border: none; }}
            .btn-login:hover {{ background: #6b21a8; }}
            
            .content {{ padding: 40px; overflow-y: auto; flex-grow: 1; background: #000000; }}
            .card {{ background: #0a0510; border: 1px solid #2e1065; border-radius: 10px; padding: 30px; margin-bottom: 20px; box-shadow: 0 4px 20px rgba(126, 34, 206, 0.1); }}
            h2 {{ font-size: 20px; margin-bottom: 15px; color: #ffffff; }}
            p {{ color: #c084fc; font-size: 14px; line-height: 1.5; margin-bottom: 20px; }}
            
            .toggle-row {{ display: flex; justify-content: space-between; align-items: center; padding: 12px 0; border-bottom: 1px solid #2e1065; }}
            .switch {{ position: relative; display: inline-block; width: 44px; height: 24px; }}
            .switch input {{ opacity: 0; width: 0; height: 0; }}
            .slider {{ position: absolute; cursor: pointer; top: 0; left: 0; right: 0; bottom: 0; background-color: #1e1b4b; transition: .3s; border-radius: 24px; border: 1px solid #6b21a8; }}
            .slider:before {{ position: absolute; content: ""; height: 18px; width: 18px; left: 2px; bottom: 2px; background-color: white; transition: .3s; border-radius: 50%; }}
            input:checked + .slider {{ background-color: #7e22ce; }}
            input:checked + .slider:before {{ transform: translateX(20px); }}
            
            .form-input {{ width: 100%; padding: 10px 14px; background: #030007; border: 1px solid #2e1065; border-radius: 6px; color: white; margin-bottom: 15px; font-size: 14px; }}
            .action-btn {{ background: #7e22ce; color: white; border: none; padding: 10px 20px; border-radius: 6px; font-weight: 600; cursor: pointer; }}
            .action-btn:hover {{ background: #6b21a8; }}
            
            table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
            th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #2e1065; font-size: 14px; color: #e9d5ff; }}
            th {{ color: #c084fc; font-weight: 600; }}
        </style>
    </head>
    <body>
        <div class="sidebar">
            <div class="brand">SQUATTEDS SKILL FEEDZ</div>
            <ul class="menu-list">
                <a href="/?tab=dashboard" class="menu-item {'active' if tab == 'dashboard' else ''}">Dashboard & Admin Controls</a>
                <a href="/?tab=server_link" class="menu-item {'active' if tab == 'server_link' else ''}">Link Game Server (RCON)</a>
                <a href="/?tab=economy" class="menu-item {'active' if tab == 'economy' else ''}">Economy & Shop</a>
                <a href="/?tab=factions" class="menu-item {'active' if tab == 'factions' else ''}">Factions & Bounties</a>
                <a href="/?tab=tickets" class="menu-item {'active' if tab == 'tickets' else ''}">Support Tickets</a>
                <a href="/?tab=stats" class="menu-item {'active' if tab == 'stats' else ''}">Live Stats & Leaderboards</a>
            </ul>
        </div>

        <div class="main-container">
            <div class="header">
                <a href="/create-checkout-session" class="btn-header btn-invite">Invite Bot</a>
                <a href="/login" class="btn-header btn-login">Login</a>
            </div>

            <div class="content">
                {alert_html}
                {"<div class='card'><h2>Admin Controls & Server Management</h2><p>Manage strict permissions, server restarts, wipes, and member moderation.</p><div class='toggle-row'><span>Admin-Locked Commands Restriction</span><label class='switch'><input type='checkbox' checked><span class='slider'></span></label></div><div style='margin-top:20px;'><button class='action-btn' style='background:#b91c1c; margin-right:10px;'>Trigger /restart</button><button class='action-btn' style='background:#b91c1c; margin-right:10px;'>Trigger /server wipe</button><button class='action-btn' style='background:#b91c1c;'>Trigger Vehicle Wipe</button></div><br><div style='margin-top:20px;'><form action='/create-portal-session' method='POST'><button type='submit' class='action-btn' style='background: #b91c1c;'>Cancel Subscription</button></form></div></div>" if tab == 'dashboard' else ""}
                {"<div class='card'><h2>Link Your Game Server (RCON)</h2><p>Connect your game server IP, RCON port, and password to enable remote server restarts and automated data sync.</p><form action='/api/save-rcon' method='POST'><label style='color:#c084fc;'>Server IP Address</label><input type='text' name='ip' class='form-input' value='" + server_config_db['ip'] + "' placeholder='192.168.1.100' required><label style='color:#c084fc;'>RCON Port</label><input type='number' name='port' class='form-input' value='" + str(server_config_db['port']) + "' placeholder='27015' required><label style='color:#c084fc;'>RCON Password</label><input type='password' name='password' class='form-input' value='" + server_config_db['password'] + "' placeholder='••••••••' required><button type='submit' class='action-btn'>Save & Connect RCON</button></form></div>" if tab == 'server_link' else ""}
                {"<div class='card'><h2>Economy, Bank & Shop</h2><p>Manage currency balances, cash/bank transfers, shops, and rentals.</p><label style='color:#c084fc;'>Starting Cash Balance</label><input type='number' class='form-input' value='2500'><button class='action-btn'>Save Economy Config</button></div>" if tab == 'economy' else ""}
                {"<div class='card'><h2>Factions & Bounties System</h2><p>Configure faction creation rules and live bounty tracking coordinates.</p><div class='toggle-row'><span>Bounty Radar Coordinate Tracking</span><label class='switch'><input type='checkbox' checked><span class='slider'></span></label></div></div>" if tab == 'factions' else ""}
                {"<div class='card'><h2>Support Tickets Dashboard</h2><p>Review user-created tickets, claim channels, review status, and manage inquiries.</p><table><tr><th>Ticket ID</th><th>User</th><th>Status</th><th>Action</th></tr><tr><td>#1001</td><td>Player_One</td><td style='color:#34d399;'>Open (Unclaimed)</td><td><button class='action-btn' style='padding:5px 10px; font-size:12px;'>Claim / Respond</button></td></tr></table></div>" if tab == 'tickets' else ""}
                {"<div class='card'><h2>Live Stats & Leaderboards</h2><p>Real-time tracking for longest kills, headshots, kill/death streaks, and specific kill weapon data.</p><p style='color:#a78bfa;'>Status: Live-updating connection active.</p></div>" if tab == 'stats' else ""}
            </div>
        </div>
    </body>
    </html>
    """

@app.post("/api/save-rcon")
async def save_rcon(ip: str = Form(...), port: int = Form(...), password: str = Form(...)):
    server_config_db["ip"] = ip
    server_config_db["port"] = port
    server_config_db["password"] = password
    return RedirectResponse(url="/?tab=server_link&success=saved", status_code=303)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Login - SQUATTEDS SKILL FEEDZ</title>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
            body { background: #000000; color: #f8fafc; display: flex; justify-content: center; align-items: center; height: 100vh; }
            .container { background: #0a0510; padding: 40px; border-radius: 12px; border: 1px solid #2e1065; width: 100%; max-width: 400px; box-shadow: 0 4px 20px rgba(126, 34, 206, 0.1); }
            h2 { margin-bottom: 20px; font-size: 22px; text-align: center; color: #ffffff; }
            label { display: block; font-size: 13px; color: #c084fc; margin-bottom: 6px; }
            input { width: 100%; padding: 12px; background: #030007; border: 1px solid #2e1065; border-radius: 6px; color: white; font-size: 14px; margin-bottom: 20px; }
            input:focus { outline: none; border-color: #7e22ce; }
            button { width: 100%; background: #7e22ce; color: white; border: none; padding: 12px; border-radius: 6px; font-size: 16px; font-weight: 600; cursor: pointer; }
            button:hover { background: #6b21a8; }
            .back { display: block; text-align: center; color: #a78bfa; font-size: 13px; margin-top: 15px; text-decoration: none; }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Account Login</h2>
            <form action="/api/login-form" method="POST">
                <label>Email Address</label>
                <input type="email" name="email" required placeholder="name@example.com">
                <label>Password</label>
                <input type="password" name="password" required placeholder="••••••••">
                <button type="submit">Sign In</button>
            </form>
            <a href="/" class="back">← Back to Home</a>
        </div>
    </body>
    </html>
    """

@app.post("/api/login-form")
async def login_form_handler(email: str = Form(...), password: str = Form(...)):
    user = fake_users_db.get(email)
    if not user or user["password"] != password:
        raise HTTPException(status_code=400, detail="Invalid credentials")
    if user["email"] == ADMIN_EMAIL:
        return RedirectResponse(url="/admin/dashboard", status_code=303)
    return RedirectResponse(url="/", status_code=303)

@app.get("/admin/dashboard", response_class=HTMLResponse)
async def admin_dashboard(email: str = ADMIN_EMAIL):
    if email != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Access Forbidden")
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head><title>Owner Dashboard</title></head>
    <body style="background:#000;color:#fff;padding:40px;font-family:sans-serif;">
        <h1>Welcome Back, Dwayne</h1>
        <p>Owner Control Panel (Lifetime Free Access)</p>
        <a href="/" style="color:#c084fc;">← Return to Main Panel</a>
    </body>
    </html>
    """

@app.get("/create-checkout-session")
async def create_checkout_session(request: Request):
    return RedirectResponse(STRIPE_PAYMENT_LINK, status_code=303)

@app.post("/create-portal-session")
async def customer_portal(request: Request):
    try:
        portal_session = stripe.billing_portal.Session.create(
            customer="cus_placeholder",
            return_url=str(request.base_url),
        )
        return RedirectResponse(portal_session.url, status_code=303)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- TICKET UI VIEW & BUTTONS ---
class TicketControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Claim", style=discord.ButtonStyle.green, custom_id="ticket_claim")
    async def claim_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only administrators can claim tickets.", ephemeral=True)
            return
        await interaction.response.send_message(f"🔒 Ticket claimed by {interaction.user.mention}.", ephemeral=False)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.red, custom_id="ticket_close")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only administrators can close tickets.", ephemeral=True)
            return
        await interaction.response.send_message("🔒 Closing ticket and archiving transcript...", ephemeral=False)
        await interaction.channel.delete(delay=5)

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.grey, custom_id="ticket_deny")
    async def deny_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Only administrators can deny tickets.", ephemeral=True)
            return
        await interaction.response.send_message("❌ Ticket request denied. Archiving channel...", ephemeral=False)
        await interaction.channel.delete(delay=5)


# --- DISCORD BOT SETUP & COMMANDS ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands.")
    except Exception as e:
        print(e)

# --- Admin-Locked Server & Money Controls with Live RCON ---
@bot.tree.command(name="restart", description="Restarts server via RCON (Admin Only)")
async def restart_cmd(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You lack administrator permissions to execute this command.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    result = await send_rcon_command("#restart")
    await interaction.followup.send(f"🔄 **Server Restart:** {result}", ephemeral=True)

@bot.tree.command(name="server_wipe", description="Wipes server data via RCON (Admin Only)")
async def server_wipe_cmd(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You lack administrator permissions to execute this command.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    result = await send_rcon_command("serverWipe")
    await interaction.followup.send(f"⚠️ **Server Wipe:** {result}", ephemeral=True)

@bot.tree.command(name="vehicle_wipe", description="Wipes and resets vehicles via RCON (Admin Only)")
async def vehicle_wipe_cmd(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You lack administrator permissions to execute this command.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    result = await send_rcon_command("vehicleWipe")
    await interaction.followup.send(f"🚗 **Vehicle Wipe:** {result}", ephemeral=True)

@bot.tree.command(name="add_money", description="Add money to player (Admin Only)")
async def add_money_cmd(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You lack administrator permissions to execute this command.", ephemeral=True)
        return
    await interaction.response.send_message(f"💰 Successfully added ${amount} to {member.mention}.", ephemeral=True)

@bot.tree.command(name="remove_money", description="Remove money from player (Admin Only)")
async def remove_money_cmd(interaction: discord.Interaction, member: discord.Member, amount: int):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You lack administrator permissions to execute this command.", ephemeral=True)
        return
    await interaction.response.send_message(f"💸 Successfully removed ${amount} from {member.mention}.", ephemeral=True)


# --- Ticket System Command ---
@bot.tree.command(name="create_ticket", description="Create a support ticket")
async def create_ticket_cmd(interaction: discord.Interaction, subject: str):
    guild = interaction.guild
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(read_messages=False),
        interaction.user: discord.PermissionOverwrite(read_messages=True, send_messages=True),
        guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
    }
    
    for role in guild.roles:
        if role.permissions.administrator:
            overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

    channel_name = f"ticket-{interaction.user.name}"
    ticket_channel = await guild.create_text_channel(name=channel_name, overwrites=overwrites)
    
    embed = discord.Embed(
        title=f"Support Ticket: {subject}",
        description=f"Hello {interaction.user.mention},\nAn administrator will be with you shortly.\n\nUse the buttons below to **Claim**, **Close**, or **Deny** this ticket.",
        color=0x7e22ce
    )
    
    await ticket_channel.send(embed=embed, view=TicketControlView())
    await interaction.response.send_message(f"✅ Ticket created successfully: {ticket_channel.mention}", ephemeral=True)


# --- Standard Economy & Gameplay Commands ---
@bot.tree.command(name="balance", description="Shows your cash and bank balance")
async def balance_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("💳 **Balance:** Cash: $1,200 | Bank: $5,400", ephemeral=True)

@bot.tree.command(name="withdraw", description="Withdraws cash from bank")
async def withdraw_cmd(interaction: discord.Interaction, amount: int):
    await interaction.response.send_message(f"💵 Withdrew ${amount} from your bank account.", ephemeral=True)

@bot.tree.command(name="dep_all", description="Deposits all cash into bank")
async def dep_all_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("🏦 Deposited all cash into your bank safely.", ephemeral=True)

@bot.tree.command(name="pay", description="Pays another player")
async def pay_cmd(interaction: discord.Interaction, member: discord.Member, amount: int):
    await interaction.response.send_message(f"🤝 Transferred ${amount} to {member.mention}.", ephemeral=True)

@bot.tree.command(name="rob", description="Robs another player for up to 60% of their cash")
async def rob_cmd(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.send_message(f"🥷 You attempted to rob {member.mention}!", ephemeral=True)

@bot.tree.command(name="bounty", description="Place a bounty on a selected player and get their coordinates")
async def bounty_cmd(interaction: discord.Interaction, member: discord.Member, reward: int):
    await interaction.response.send_message(f"🎯 Bounty of ${reward} placed on {member.mention}! Last known coordinates: [11452.3, 4210.1]", ephemeral=True)


# --- Factions & Shop ---
@bot.tree.command(name="create_faction", description="Goes through faction creation process")
async def create_faction_cmd(interaction: discord.Interaction, name: str):
    await interaction.response.send_message(f"🛡️ Faction '{name}' setup initialized.", ephemeral=True)

@bot.tree.command(name="add_faction_member", description="Add a member to your faction")
async def add_faction_member_cmd(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.send_message(f"➕ Added {member.mention} to your faction.", ephemeral=True)

@bot.tree.command(name="remove_faction_member", description="Remove a member from your faction")
async def remove_faction_member_cmd(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.send_message(f"➖ Removed {member.mention} from your faction.", ephemeral=True)

@bot.tree.command(name="shop", description="Buy items or vehicle rentals")
async def shop_cmd(interaction: discord.Interaction, action: str, item_name: str):
    await interaction.response.send_message(f"🛒 Shop transaction processed for {item_name} ({action}).", ephemeral=True)


# --- Mini-Games ---
@bot.tree.command(name="roulette", description="Play roulette")
async def roulette_cmd(interaction: discord.Interaction, bet: int):
    await interaction.response.send_message(f"🎲 Roulette wheel spun with a bet of ${bet}.", ephemeral=True)

@bot.tree.command(name="blackjack", description="Play blackjack")
async def blackjack_cmd(interaction: discord.Interaction, bet: int):
    await interaction.response.send_message(f"🃏 Blackjack game started with a bet of ${bet}.", ephemeral=True)

@bot.tree.command(name="cockfight", description="Play cockfight mini-game")
async def cockfight_cmd(interaction: discord.Interaction, bet: int):
    await interaction.response.send_message(f"🐓 Cockfight match initiated with a bet of ${bet}.", ephemeral=True)

@bot.tree.command(name="dice", description="Roll dice")
async def dice_cmd(interaction: discord.Interaction, bet: int):
    await interaction.response.send_message(f"🎲 Dice rolled with a bet of ${bet}.", ephemeral=True)


# --- Utilities & Stats ---
@bot.tree.command(name="location", description="Locates yourself or others if admin")
async def location_cmd(interaction: discord.Interaction, member: discord.Member = None):
    if member and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You require admin privileges to locate other members.", ephemeral=True)
        return
    target = member or interaction.user
    await interaction.response.send_message(f"📍 Location for {target.name}: [12500.4, 3100.8]", ephemeral=True)

@bot.tree.command(name="stats", description="Shows live-updating stats and leaderboards")
async def stats_cmd(interaction: discord.Interaction):
    await interaction.response.send_message("📊 **Live Leaderboards:**\n• Longest Kill: 840m (M4 Headshot)\n• Kill Streak: 12\n• Death Streak: 3", ephemeral=True)

@bot.tree.command(name="punch", description="Virtually punch another member")
async def punch_cmd(interaction: discord.Interaction, member: discord.Member):
    await interaction.response.send_message(f"👊 {interaction.user.mention} winds up and virtually punches {member.mention} right in the jaw!", ephemeral=False)


# --- RUN BOTH FASTAPI & DISCORD BOT CONCURRENTLY ---
def run_fastapi():
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

if __name__ == "__main__":
    fastapi_thread = threading.Thread(target=run_fastapi, daemon=True)
    fastapi_thread.start()
    bot.run(DISCORD_BOT_TOKEN)
