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
                <a href="/?tab=dashboard" class="menu-item {'active' if tab == 'dashboard' else ''}">Dashboard</a>
                <a href="/?tab=currency" class="menu-item {'active' if tab == 'currency' else ''}">Currency</a>
                <a href="/?tab=casino" class="menu-item {'active' if tab == 'casino' else ''}">Casino</a>
                <a href="/?tab=shop" class="menu-item {'active' if tab == 'shop' else ''}">Shop</a>
                <a href="/?tab=zones" class="menu-item {'active' if tab == 'zones' else ''}">Zones & Radars</a>
                <a href="/?tab=welcome" class="menu-item {'active' if tab == 'welcome' else ''}">Welcome / Goodbye</a>
                <a href="/?tab=tasks" class="menu-item {'active' if tab == 'tasks' else ''}">Scheduled Tasks</a>
            </ul>
        </div>

        <div class="main-container">
            <div class="header">
                <a href="/create-checkout-session" class="btn-header btn-invite">Invite Bot</a>
                <a href="/login" class="btn-header btn-login">Login</a>
            </div>

            <div class="content">
                {"<div class='card'><h2>Subscription & Server Dashboard</h2><p>Manage your bot license, view subscription status, and control billing.</p><div class='toggle-row'><span>Active Subscription Status</span><b style='color: #c084fc;'>Active ($12.99/mo)</b></div><div style='margin-top: 20px;'><form action='/create-portal-session' method='POST'><button type='submit' class='action-btn' style='background: #b91c1c;'>Cancel Subscription</button></form></div></div>" if tab == 'dashboard' else ""}
                {"<div class='card'><h2>Currency Settings</h2><p>Customize custom emojis, starting balances, and automated role/job payouts.</p><div class='toggle-row'><span>Enable Currency Module</span><label class='switch'><input type='checkbox' checked><span class='slider'></span></label></div><br><label style='color:#c084fc;'>Currency Name / Emoji</label><input type='text' class='form-input' value='🪙 Gold'><label style='color:#c084fc;'>Starting Balance for New Players</label><input type='number' class='form-input' value='5000'><button class='action-btn'>Save Currency Config</button></div>" if tab == 'currency' else ""}
                {"<div class='card'><h2>Casino Payouts & Ratios</h2><p>Fine-tune win/loss percentages and specific payout multipliers for server games.</p><div class='toggle-row'><span>Enable Casino System</span><label class='switch'><input type='checkbox' checked><span class='slider'></span></label></div><br><label style='color:#c084fc;'>Jackpot Payout Multiplier</label><input type='text' class='form-input' value='3.5x'><button class='action-btn'>Update Ratios</button></div>" if tab == 'casino' else ""}
                {"<div class='card'><h2>Item & Vehicle Shop Builder</h2><p>Configure complete vehicle spawns, clothing, and item prices synced directly with your JSON configs.</p><div class='toggle-row'><span>Enable Custom Shop</span><label class='switch'><input type='checkbox' checked><span class='slider'></span></label></div><br><p style='color:#a78bfa;'>JSON Sync Active: Complete vehicle spawns match server configuration parameters.</p></div>" if tab == 'shop' else ""}
                {"<div class='card'><h2>Console Maps & Radar Zones</h2><p>Interactive map coordinate visualizer. Draw circular zones for 30-60 second precise player tracking, base radars, and gas zones.</p><div class='toggle-row'><span>High-Speed Player Radar (30-60s Ping)</span><label class='switch'><input type='checkbox' checked><span class='slider'></span></label></div></div>" if tab == 'zones' else ""}
                {"<div class='card'><h2>Welcome & Goodbye Messages</h2><p>Configure automated entry greetings, departure notices, and reaction-role verification triggers.</p><label style='color:#c084fc;'>Custom Welcome Message</label><input type='text' class='form-input' value='Welcome to the server, user! Check the rules to get verified.'><button class='action-btn'>Save Messages</button></div>" if tab == 'welcome' else ""}
                {"<div class='card'><h2>Scheduled Tasks & Server Automation</h2><p>Automate restarts, server wipes, and toggle base/container damage states.</p><div class='toggle-row'><span>Automated Server Restarts</span><label class='switch'><input type='checkbox' checked><span class='slider'></span></label></div><div class='toggle-row'><span>Base & Container Damage Toggle</span><label class='switch'><input type='checkbox' checked><span class='slider'></span></label></div><div style='margin-top:20px;'><button class='action-btn' style='background:#b91c1c;'>Trigger Manual Wipe</button></div></div>" if tab == 'tasks' else ""}
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


# --- DISCORD BOT SETUP ---
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

@bot.tree.command(name="currency", description="Manage or check custom currency balances")
async def currency_cmd(interaction: discord.Interaction, action: str, amount: int = 0):
    await interaction.response.send_message(f"Currency action '{action}' executed with amount {amount}.", ephemeral=True)

@bot.tree.command(name="casino", description="Play custom casino games")
async def casino_cmd(interaction: discord.Interaction, game: str, bet: int):
    await interaction.response.send_message(f"Casino game {game} played with bet {bet}.", ephemeral=True)

@bot.tree.command(name="shop", description="Browse or buy items and vehicles from shop")
async def shop_cmd(interaction: discord.Interaction, item: str):
    await interaction.response.send_message(f"Shop request processed for: {item}", ephemeral=True)

@bot.tree.command(name="radar", description="Toggle or configure high-speed player radars")
async def radar_cmd(interaction: discord.Interaction, state: str):
    await interaction.response.send_message(f"Radar state set to: {state}", ephemeral=True)

@bot.tree.command(name="server", description="Manage server tasks like restarts and wipes")
async def server_cmd(interaction: discord.Interaction, action: str):
    await interaction.response.send_message(f"Server task '{action}' initiated.", ephemeral=True)


# --- RUN BOTH FASTAPI & DISCORD BOT CONCURRENTLY ---
def run_fastapi():
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

if __name__ == "__main__":
    # Start FastAPI in a background thread
    fastapi_thread = threading.Thread(target=run_fastapi, daemon=True)
    fastapi_thread.start()
    
    # Run the Discord bot on the main thread
    bot.run(DISCORD_BOT_TOKEN)
