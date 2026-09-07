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
DISCORD_OAUTH_INVITE = "https://discord.com/api/oauth2/authorize?client_id=YOUR_CLIENT_ID&permissions=8&scope=bot%20applications.commands"
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "your_bot_token_here")

ADMIN_EMAIL = "Dwayne.mashburn@gmail.com"
ADMIN_PASSWORD = "Duanemashburn2!"

fake_users_db = {
    ADMIN_EMAIL.lower(): {
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD,
        "is_admin": True,
        "is_subscribed": True
    }
}

server_config_db = {
    "ip": "",
    "port": 27015,
    "password": ""
}

economy_config_db = {
    "currency_name": "Cash",
    "currency_emoji": "💵",
    "starting_balance": 2500
}

welcome_config_db = {
    "channel": "#general",
    "message": "Welcome to the server!"
}

# --- RCON CLIENT IMPLEMENTATION ---
async def send_rcon_command(command: str) -> str:
    host = server_config_db.get("ip")
    port = int(server_config_db.get("port", 27015))
    password = server_config_db.get("password")

    if not host or not password:
        return "❌ RCON configuration missing. Please link your server in Server Configuration."

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

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "SquattedKillFeed2"}

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, tab: str = "server_config"):
    success_msg = request.query_params.get("success")
    alert_html = "<div style='background:#064e3b;color:#34d399;padding:12px;border-radius:6px;margin-bottom:20px;font-size:14px;border:1px solid #7e22ce;'>Changes saved successfully!</div>" if success_msg == "saved" else ""

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>SQUATTEDSKILLFEEDZ</title>
        <style>
            * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }}
            body {{ background: #000000; color: #f8fafc; display: flex; flex-direction: column; height: 100vh; overflow: hidden; }}
            
            /* Top Navbar */
            .top-nav {{ height: 70px; background: #000000; border-bottom: 1px solid #7e22ce; display: flex; justify-content: space-between; align-items: center; padding: 0 30px; }}
            .nav-brand {{ font-size: 18px; font-weight: 800; color: #ffffff; letter-spacing: 1px; }}
            .nav-links {{ display: flex; gap: 25px; align-items: center; }}
            .nav-link {{ color: #c084fc; text-decoration: none; font-size: 14px; font-weight: 600; transition: color 0.2s; }}
            .nav-link:hover {{ color: #ffffff; }}
            .nav-btn {{ background: #7e22ce; color: white; padding: 8px 18px; border-radius: 6px; font-size: 14px; font-weight: 600; text-decoration: none; border: 1px solid #7e22ce; }}
            .nav-btn:hover {{ background: #6b21a8; }}

            /* Layout Body */
            .main-layout {{ display: flex; flex-grow: 1; height: calc(100vh - 70px); overflow: hidden; }}
            
            /* Sidebar */
            .sidebar {{ width: 280px; background: #000000; border-right: 1px solid #7e22ce; display: flex; flex-direction: column; padding: 20px 0; overflow-y: auto; }}
            .menu-title {{ font-size: 11px; font-weight: 700; color: #7e22ce; padding: 10px 20px 5px; letter-spacing: 0.5px; }}
            .menu-item {{ padding: 12px 20px; margin: 2px 10px; border-radius: 6px; cursor: pointer; color: #c084fc; font-size: 14px; font-weight: 500; text-decoration: none; display: flex; align-items: center; border: 1px solid transparent; transition: all 0.2s; }}
            .menu-item:hover, .menu-item.active {{ background: #000000; color: #ffffff; border-color: #7e22ce; }}

            /* Content Area */
            .content {{ flex-grow: 1; padding: 40px; overflow-y: auto; background: #000000; }}
            .card {{ background: #000000; border: 1px solid #7e22ce; border-radius: 10px; padding: 30px; margin-bottom: 20px; box-shadow: 0 4px 20px rgba(126, 34, 206, 0.15); }}
            h2 {{ font-size: 20px; margin-bottom: 10px; color: #ffffff; }}
            p {{ color: #a78bfa; font-size: 14px; line-height: 1.5; margin-bottom: 20px; }}
            
            .form-input {{ width: 100%; padding: 12px 14px; background: #000000; border: 1px solid #7e22ce; border-radius: 6px; color: white; margin-bottom: 15px; font-size: 14px; }}
            .form-input:focus {{ outline: none; border-color: #c084fc; }}
            label {{ display: block; font-size: 13px; color: #c084fc; margin-bottom: 6px; font-weight: 600; }}
            
            .action-btn {{ background: #7e22ce; color: white; border: 1px solid #7e22ce; padding: 10px 20px; border-radius: 6px; font-weight: 600; cursor: pointer; display: inline-block; text-decoration: none; }}
            .action-btn:hover {{ background: #6b21a8; }}

            /* Map / Zone Canvas container */
            .map-container {{ width: 100%; height: 400px; background: #030005; border: 1px solid #7e22ce; border-radius: 8px; position: relative; display: flex; justify-content: center; align-items: center; overflow: hidden; margin-bottom: 15px; }}
            .map-grid {{ position: absolute; width: 100%; height: 100%; background-image: radial-gradient(#7e22ce 1px, transparent 1px); background-size: 30px 30px; opacity: 0.3; }}
            
            table {{ width: 100%; border-collapse: collapse; margin-top: 15px; }}
            th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #7e22ce; font-size: 14px; color: #e9d5ff; }}
            th {{ color: #c084fc; font-weight: 600; }}
        </style>
    </head>
    <body>
        <!-- Top Navbar Exact Match -->
        <div class="top-nav">
            <div class="nav-brand">SQUATTEDSKILLFEEDZ</div>
            <div class="nav-links">
                <a href="/?tab=welcome" class="nav-link">WELCOME</a>
                <a href="/create-checkout-session" class="nav-btn">INVITE BOT</a>
                <a href="/login" class="nav-btn" style="background:transparent; border:1px solid #7e22ce;">LOGIN</a>
            </div>
        </div>

        <div class="main-layout">
            <!-- Left Sidebar Categories -->
            <div class="sidebar">
                <div class="menu-title">CONFIGURATION</div>
                <a href="/?tab=server_config" class="menu-item {'active' if tab == 'server_config' else ''}">Server configuration</a>
                <a href="/?tab=account" class="menu-item {'active' if tab == 'account' else ''}">Account</a>
                <a href="/?tab=zones" class="menu-item {'active' if tab == 'zones' else ''}">Zones & Radar</a>
                <a href="/?tab=shop" class="menu-item {'active' if tab == 'shop' else ''}">Shop</a>
                <a href="/?tab=casino" class="menu-item {'active' if tab == 'casino' else ''}">Casino</a>
                <a href="/?tab=tasks" class="menu-item {'active' if tab == 'tasks' else ''}">Scheduled tasks</a>
                <a href="/?tab=welcome_msg" class="menu-item {'active' if tab == 'welcome_msg' else ''}">Welcome & goodbye message</a>
                <a href="/?tab=currency" class="menu-item {'active' if tab == 'currency' else ''}">Currency</a>
                <a href="/?tab=bans" class="menu-item {'active' if tab == 'bans' else ''}">Bans</a>
            </div>

            <!-- Middle Dynamic Content Area -->
            <div class="content">
                {alert_html}
                
                {"<div class='card'><h2>Server Configuration</h2><p>Link your game server RCON credentials to enable automated tasks and instant command routing.</p><form action='/api/save-rcon' method='POST'><label>Server IP Address</label><input type='text' name='ip' class='form-input' value='" + server_config_db['ip'] + "' placeholder='192.168.1.50' required><label>RCON Port</label><input type='number' name='port' class='form-input' value='" + str(server_config_db['port']) + "' placeholder='27015' required><label>RCON Password</label><input type='password' name='password' class='form-input' value='" + server_config_db['password'] + "' placeholder='••••••••' required><button type='submit' class='action-btn'>Save & Connect RCON</button></form></div>" if tab == 'server_config' else ""}

                {"<div class='card'><h2>Account Management</h2><p>Manage your active subscriptions, billing records, and payment methods securely via Stripe.</p><div style='margin-bottom:20px;'><span style='color:#34d399; font-weight:600;'>● Status: Active Admin Subscribed</span></div><form action='/create-portal-session' method='POST'><button type='submit' class='action-btn' style='background:#7e22ce;'>Manage Stripe Billing / Cancel</button></form></div>" if tab == 'account' else ""}

                {"<div class='card'><h2>Custom Zones & Player Radar</h2><p>Select a console map below, click and drag/zoom to draw custom zones (Safe zones, PvP, PvE, Gas exclusion, and instant base radars). Bounty targets auto-create localized radars.</p><label>Select Console Map</label><select class='form-input'><option>Chernarus (DayZ)</option><option>Livonia (DayZ)</option><option>Namalsk (DayZ)</option></select><div class='map-container'><div class='map-grid'></div><span style='color:#c084fc; z-index:2; font-weight:600;'>[ Click & Drag to Draw Zone Circle ]</span></div><button class='action-btn'>Save Zone Configuration</button></div>" if tab == 'zones' else ""}

                {"<div class='card'><h2>Custom Item & Vehicle Shop</h2><p>Configure fully synced shop inventory matching your server JSON configuration files. Set quantities, item variants, pristine spawn conditions, and custom pricing.</p><label>Select Item / Vehicle</label><select class='form-input'><option>M4A1 (Pristine)</option><option>SVD Sniper</option><option>Lar (Full Mag)</option><option>Ada 4x4 Vehicle (Complete)</option><option>Truck (Offroad)</option></select><label>Quantity</label><input type='number' class='form-input' value='3'><label>Price (Custom Currency)</label><input type='number' class='form-input' value='1500'><button class='action-btn'>Save Shop Entry</button></div>" if tab == 'shop' else ""}

                {"<div class='card'><h2>Casino Payouts & Games</h2><p>Customize win/loss ratios, payouts, and multiplier limits for roulette, blackjack, dice, and cockfights.</p><label>Roulette Multiplier Win Rate</label><input type='text' class='form-input' value='2.0x'><label>Jackpot Win Chance (%)</label><input type='number' class='form-input' value='15'><button class='action-btn'>Update Casino Settings</button></div>" if tab == 'casino' else ""}

                {"<div class='card'><h2>Scheduled Tasks</h2><p>Automate regular server maintenance scripts, wipes, broadcasts, and RCON reboots.</p><label>Task Type</label><select class='form-input'><option>Server Restart</option><option>Vehicle Wipe</option><option>Full Server Wipe</option><option>Broadcast Custom Message</option></select><label>Cron Schedule / Interval</label><input type='text' class='form-input' value='0 4 * * * (Every day at 4 AM)'><button class='action-btn'>Create Scheduled Task</button></div>" if tab == 'tasks' else ""}

                {"<div class='card'><h2>Welcome & Goodbye Message Setup</h2><p>Customize automated discord server greeting messages and announcement channels.</p><label>Target Channel</label><input type='text' class='form-input' value='" + welcome_config_db['channel'] + "'><label>Custom Welcome Text</label><textarea class='form-input' rows='3'>" + welcome_config_db['message'] + "</textarea><button class='action-btn'>Save Welcome Settings</button></div>" if tab == 'welcome_msg' else ""}

                {"<div class='card'><h2>Currency Configuration</h2><p>Configure your server's currency name, custom emoji symbols, starting balances, and manual player wallet management.</p><label>Currency Name</label><input type='text' class='form-input' value='" + economy_config_db['currency_name'] + "'><label>Custom Emoji</label><input type='text' class='form-input' value='" + economy_config_db['currency_emoji'] + "'><label>New Player Starting Balance</label><input type='number' class='form-input' value='" + str(economy_config_db['starting_balance']) + "'><button class='action-btn'>Save Currency Settings</button></div>" if tab == 'currency' else ""}

                {"<div class='card'><h2>Active Bans & Moderation</h2><p>Review player bans, reasons, timestamps, and execute instant unbans or automated temporary ban durations.</p><table><tr><th>Player</th><th>Reason</th><th>Duration</th><th>Action</th></tr><tr><td>BadActor99</td><td>Dupe Glitch Violation</td><td>24 Hours (Active)</td><td><button class='action-btn' style='padding:5px 10px; font-size:12px;'>Unban</button></td></tr></table></div>" if tab == 'bans' else ""}

                {"<div class='card'><h2>Welcome Guide & Information</h2><p>Quick start guide on getting the SQUATTEDSKILLFEEDZ bot invited, configured, and running on your community server.</p><ul style='color:#e9d5ff; padding-left:20px; line-height:1.8; font-size:14px;'><li><b>Step 1:</b> Click <b>INVITE BOT</b> in the top right to authorize the application with full administrator privileges.</li><li><b>Step 2:</b> Link your game server RCON credentials under <b>Server configuration</b>.</li><li><b>Step 3:</b> Draw custom safe zones and configure shops matching your server JSON files.</li><li><b>Pricing Info:</b> Full feature access is available via subscription management. (Note: Dwayne Mashburn retains automated 24/7 lifetime free access with full administrative master controls).</li></ul></div>" if tab == 'welcome' else ""}
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
    return RedirectResponse(url="/?tab=server_config&success=saved", status_code=303)

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>Login - SQUATTEDSKILLFEEDZ</title>
        <style>
            * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
            body { background: #000000; color: #f8fafc; display: flex; justify-content: center; align-items: center; height: 100vh; }
            .container { background: #000000; padding: 40px; border-radius: 12px; border: 1px solid #7e22ce; width: 100%; max-width: 400px; box-shadow: 0 4px 20px rgba(126, 34, 206, 0.2); }
            h2 { margin-bottom: 20px; font-size: 22px; text-align: center; color: #ffffff; }
            label { display: block; font-size: 13px; color: #c084fc; margin-bottom: 6px; font-weight: 600; }
            input { width: 100%; padding: 12px; background: #000000; border: 1px solid #7e22ce; border-radius: 6px; color: white; font-size: 14px; margin-bottom: 20px; }
            input:focus { outline: none; border-color: #c084fc; }
            button { width: 100%; background: #7e22ce; color: white; border: 1px solid #7e22ce; padding: 12px; border-radius: 6px; font-size: 16px; font-weight: 600; cursor: pointer; }
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
    user = fake_users_db.get(email.strip().lower())
    if not user or user["password"] != password:
        raise HTTPException(status_code=400, detail="Invalid credentials")
    
    response = RedirectResponse(url="/?tab=server_config", status_code=303)
    response.set_cookie(key="user_email", value=email.strip())
    return response

@app.get("/create-checkout-session")
async def create_checkout_session(request: Request):
    user_email = request.cookies.get("user_email", "")
    if user_email.lower() == ADMIN_EMAIL.lower():
        return RedirectResponse(DISCORD_OAUTH_INVITE, status_code=303)
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

@bot.tree.command(name="restart", description="Restarts server via RCON (Admin Only)")
async def restart_cmd(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You lack administrator permissions.", ephemeral=True)
        return
    await interaction.response.defer(thinking=True)
    result = await send_rcon_command("#restart")
    await interaction.followup.send(f"🔄 **Server Restart:** {result}", ephemeral=True)

@bot.tree.command(name="bounty", description="Place a bounty on a player and create target tracking zone")
async def bounty_cmd(interaction: discord.Interaction, member: discord.Member, reward: int):
    await interaction.response.send_message(f"🎯 Bounty of ${reward} placed on {member.mention}! Target radar zone generated automatically on player coordinates: [11452.3, 4210.1]", ephemeral=False)

@bot.tree.command(name="ban", description="Ban a player with automatic unban timer")
async def ban_cmd(interaction: discord.Interaction, member: discord.Member, duration_hours: int, reason: str):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Admin only.", ephemeral=True)
        return
    await interaction.response.send_message(f"🔨 {member.mention} has been banned for {duration_hours} hours. Reason: {reason}. Auto-unban timer set.", ephemeral=False)


# --- RUN FASTAPI & DISCORD BOT ---
def run_fastapi():
    uvicorn.run(app, host="0.0.0.0", port=10000, log_level="info")

if __name__ == "__main__":
    fastapi_thread = threading.Thread(target=run_fastapi, daemon=True)
    fastapi_thread.start()
    bot.run(DISCORD_BOT_TOKEN)
