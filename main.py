import os
import threading
import discord
from discord.ext import commands
from fastapi import FastAPI, Request, HTTPException, status, Form
from fastapi.responses import HTMLResponse, RedirectResponse
import uvicorn
import stripe

# --- CONFIGURATION ---
stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "sk_test_placeholder")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID", "price_placeholder")
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

# --- FASTAPI WEB APP SETUP ---
app = FastAPI()

@app.get("/", response_class=HTMLResponse)
async def home(request: Request, tab: str = "dashboard"):
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
            
            /* Sidebar Grid Layout */
            .sidebar {{ width: 260px; background: #0a0510; border-right: 1px solid #2e1065; display: flex; flex-direction: column; }}
            .brand {{ padding: 20px; font-size: 15px; font-weight: 800; color: #c084fc; border-bottom: 1px solid #2e1065; letter-spacing: 0.5px; background: #030007; }}
            .menu-list {{ list-style: none; padding: 15px; overflow-y: auto; flex-grow: 1; }}
            .menu-item {{ padding: 12px 15px; margin-bottom: 6px; border-radius: 6px; cursor: pointer; color: #a78bfa; font-size: 14px; font-weight: 500; text-decoration: none; display: flex; justify-content: space-between; align-items: center; transition: all 0.2s; }}
            .menu-item:hover, .menu-item.active {{ background: #2e1065; color: #ffffff; }}
            
            /* Top Header & Main Layout */
            .main-container {{ flex-grow: 1; display: flex; flex-direction: column; height: 100vh; }}
            .header {{ height: 70px; background: #0a0510; border-bottom: 1px solid #2e1065; display: flex; justify-content: flex-end; align-items: center; padding: 0 30px; gap: 15px; }}
            .btn-header {{ padding: 10px 20px; border-radius: 6px; font-size: 14px; font-weight: 600; text-decoration: none; cursor: pointer; }}
            .btn-invite {{ background: #1e1b4b; color: #e9d5ff; border: 1px solid #6b21a8; }}
            .btn-invite:hover {{ background: #2e1065; }}
            .btn-login {{ background: #7e22ce; color: #ffffff; border: none; }}
            .btn-login:hover {{ background: #6b21a8; }}
            
            /* Content Area */
            .content {{ padding: 40px; overflow-y: auto; flex-grow: 1; background: #000000; }}
            .card {{ background: #0a0510; border: 1px solid #2e1065; border-radius: 10px; padding: 30px; margin-bottom: 20px; box-shadow: 0 4px 20px rgba(126, 34, 206, 0.1); }}
            h2 {{ font-size: 20px; margin-bottom: 15px; color: #ffffff; }}
            p {{ color: #c084fc; font-size: 14px; line-height: 1.5; margin-bottom: 20px; }}
            
            /* Toggle Switch */
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
        </style>
    </head>
    <body>
        <div class="sidebar">
            <div class="brand">SQUATTEDS SKILL FEEDZ</div>
            <ul class="menu-list">
                <a href="/?tab=dashboard" class="menu-item {'active' if tab == 'dashboard' else ''}">Dashboard & Admin Controls</a>
                <a href="/?tab=economy" class="menu-item {'active' if tab == 'economy' else ''}">Economy & Shop</a>
                <a href="/?tab=factions" class="menu-item {'active' if tab == 'factions' else ''}">Factions & Bounties</a>
                <a href="/?tab=stats" class="menu-item {'active' if tab == 'stats' else ''}">Live Stats & Leaderboards</a>
            </ul>
        </div>

        <div class="main-container">
            <div class="header">
                <a href="/create-checkout-session" class="btn-header btn-invite">Invite Bot</a>
                <a href="/login" class="btn-header btn-login">Login</a>
            </div>

            <div class="content">
                {"<div class='card'><h2>Admin Controls & Server Management</h2><p>Manage strict permissions, server restarts, wipes, and member moderation.</p><div class='toggle-row'><span>Admin-Locked Commands Restriction</span><label class='switch'><input type='checkbox' checked><span class='slider'></span></label></div><div style='margin-top:20px;'><button class='action-btn' style='background:#b91c1c; margin-right:10px;'>Trigger /restart</button><button class='action-btn' style='background:#b91c1c; margin-right:10px;'>Trigger /server wipe</button><button class='action-btn' style='background:#b91c1c;'>Trigger Vehicle Wipe</button></div><br><div style='margin-top:20px;'><form action='/create-portal-session' method='POST'><button type='submit' class='action-btn' style='background: #b91c1c;'>Cancel Subscription</button></form></div></div>" if tab == 'dashboard' else ""}
                {"<div class='card'><h2>Economy, Bank & Shop</h2><p>Manage currency balances, cash/bank transfers, shops, and rentals.</p><label style='color:#c084fc;'>Starting Cash Balance</label><input type='number' class='form-input' value='2500'><button class='action-btn'>Save Economy Config</button></div>" if tab == 'economy' else ""}
                {"<div class='card'><h2>Factions & Bounties System</h2><p>Configure faction creation rules and live bounty tracking coordinates.</p><div class='toggle-row'><span>Bounty Radar Coordinate Tracking</span><label class='switch'><input type='checkbox' checked><span class='slider'></span></label></div></div>" if tab == 'factions' else ""}
                {"<div class='card'><h2>Live Stats & Leaderboards</h2><p>Real-time tracking for longest kills, headshots, kill/death streaks, and specific kill weapon data.</p><p style='color:#a78bfa;'>Status: Live-updating connection active.</p></div>" if tab == 'stats' else ""}
            </div>
        </div>
    </body>
    </html>
    """

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
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{'price': STRIPE_PRICE_ID, 'quantity': 1}],
            mode='subscription',
            subscription_data={'trial_period_days': 3},
            allow_promotion_codes=True,
            success_url=str(request.base_url) + '?success=true',
            cancel_url=str(request.base_url) + '?canceled=true',
        )
        return RedirectResponse(checkout_session.url, status_code=303)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

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

# --- Admin-Locked Server & Money Controls ---
@bot.tree.command(name="restart", description="Restarts server (Admin Only)")
async def restart_cmd(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You lack administrator permissions to execute this command.", ephemeral=True)
        return
    await interaction.response.send_message("🔄 Server restart sequence initiated.", ephemeral=True)

@bot.tree.command(name="server_wipe", description="Wipes server data (Admin Only)")
async def server_wipe_cmd(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You lack administrator permissions to execute this command.", ephemeral=True)
        return
    await interaction.response.send_message("⚠️ Server wipe sequence initiated.", ephemeral=True)

@bot.tree.command(name="vehicle_wipe", description="Wipes and resets vehicles to spawns (Admin Only)")
async def vehicle_wipe_cmd(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ You lack administrator permissions to execute this command.", ephemeral=True)
        return
    await interaction.response.send_message("🚗 Vehicle wipe and reset completed.", ephemeral=True)

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
