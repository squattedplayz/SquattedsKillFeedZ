import os
import sqlite3
import random
import asyncio
import threading
import uvicorn
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
from fastapi import FastAPI, Request

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# --- INITIALIZE BOTH DISCORD & FASTAPI ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

app = FastAPI()

class DayZBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(TicketCreateView())
        self.add_view(TicketCloseView())
        await self.tree.sync()
        print("Slash commands synced globally and persistent views loaded.")

bot = DayZBot()

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect("dayz_bot.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS server_configs (
            guild_id INTEGER PRIMARY KEY,
            rules_channel_id INTEGER,
            rules_role_id INTEGER,
            ticket_channel_id INTEGER,
            ticket_category_id INTEGER,
            killfeed_channel_id INTEGER
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS economy (
            user_id INTEGER PRIMARY KEY,
            wallet INTEGER DEFAULT 100,
            bank INTEGER DEFAULT 500
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS factions (
            faction_name TEXT PRIMARY KEY,
            leader_id INTEGER,
            color TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS faction_members (
            user_id INTEGER PRIMARY KEY,
            faction_name TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            killer TEXT,
            victim TEXT,
            weapon TEXT,
            distance INTEGER,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_balance(user_id: int):
    conn = sqlite3.connect("dayz_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT wallet, bank FROM economy WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO economy (user_id, wallet, bank) VALUES (?, 100, 500)", (user_id,))
        conn.commit()
        wallet, bank = 100, 500
    else:
        wallet, bank = row
    conn.close()
    return wallet, bank

def update_balance(user_id: int, wallet_change: int = 0, bank_change: int = 0):
    wallet, bank = get_balance(user_id)
    new_wallet = max(0, wallet + wallet_change)
    new_bank = max(0, bank + bank_change)
    conn = sqlite3.connect("dayz_bot.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE economy SET wallet = ?, bank = ? WHERE user_id = ?", (new_wallet, new_bank, user_id))
    conn.commit()
    conn.close()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("DayZ Master Bot is fully online, error-proofed, and ready!")

# --- FASTAPI WEBHOOK ENDPOINT (For DayZ Killfeeds) ---
@app.post("/killfeed")
async def receive_killfeed(request: Request):
    try:
        data = await request.json()
        print(f"Received Killfeed Data: {data}")
        
        # Example insertion into the kills table
        killer = data.get("killer", "Unknown")
        victim = data.get("victim", "Unknown")
        weapon = data.get("weapon", "Unknown")
        distance = data.get("distance", 0)

        conn = sqlite3.connect("dayz_bot.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO kills (killer, victim, weapon, distance) VALUES (?, ?, ?, ?)",
            (killer, victim, weapon, distance)
        )
        conn.commit()
        conn.close()
        
        return {"status": "success", "message": "Killfeed logged successfully"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@app.get("/")
async def root():
    return {"status": "Online", "service": "SquattedKillFeedZ API running"}

# --- RULES & VERIFICATION SYSTEM ---
class VerificationView(discord.ui.View):
    def __init__(self, role_id: int):
        super().__init__(timeout=None)
        self.role_id = role_id

    @discord.ui.button(label="✅ Click Here to Verify & Unlock Channels", style=discord.ButtonStyle.green, custom_id="verify_button_persist")
    async def verify_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        role = interaction.guild.get_role(self.role_id)
        if not role:
            await interaction.response.send_message("Verification role not found. Please contact an admin.", ephemeral=True)
            return
        try:
            await interaction.user.add_roles(role)
            await interaction.response.send_message("You have been verified! Channels unlocked.", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Failed to assign role. Check bot hierarchy. Error: {e}", ephemeral=True)

@bot.tree.command(name="setup_rules", description="Post the verification rules embed.")
@app_commands.checks.has_permissions(administrator=True)
async def setup_rules(interaction: discord.Interaction, role: discord.Role):
    conn = sqlite3.connect("dayz_bot.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO server_configs (guild_id, rules_channel_id, rules_role_id) VALUES (?, ?, ?)", 
                   (interaction.guild.id, interaction.channel.id, role.id))
    conn.commit()
    conn.close()

    embed = discord.Embed(
        title="⚠️ Server Rules & Verification",
        description="1. Respect all members.\n2. No toxic behavior, hate speech, or harassment.\n3. Follow platform Terms of Service.\n\nClick the button below to verify and unlock the server!",
        color=discord.Color.dark_red()
    )
    view = VerificationView(role.id)
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("Rules verification panel deployed successfully!", ephemeral=True)

# --- TICKET SYSTEM ---
class TicketCreateView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎫 Create Ticket", style=discord.ButtonStyle.blurple, custom_id="create_ticket_persist")
    async def create_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        guild = interaction.guild
        member = interaction.user

        existing_channel = discord.utils.get(guild.text_channels, name=f"ticket-{member.name.lower()}")
        if existing_channel:
            await interaction.response.send_message(f"You already have an open ticket here: {existing_channel.mention}", ephemeral=True)
            return

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True)
        }

        try:
            ticket_channel = await guild.create_text_channel(
                name=f"ticket-{member.name}",
                overwrites=overwrites,
                topic=f"Support ticket for {member.name} (ID: {member.id})"
            )
            
            embed = discord.Embed(
                title="🎫 Support Ticket",
                description=f"Welcome {member.mention}! Support staff will be with you shortly.\nClick the button below when you are ready to close this ticket.",
                color=discord.Color.blue()
            )
            await ticket_channel.send(embed=embed, view=TicketCloseView())
            await interaction.response.send_message(f"Ticket created successfully! Head over to {ticket_channel.mention}", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Failed to create ticket channel. Error: {e}", ephemeral=True)

class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🔒 Close Ticket", style=discord.ButtonStyle.red, custom_id="close_ticket_persist")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Closing ticket in 3 seconds...", ephemeral=True)
        await asyncio.sleep(3)
        await interaction.channel.delete()

@bot.tree.command(name="setup_tickets", description="Deploy the ticket creation panel.")
@app_commands.checks.has_permissions(administrator=True)
async def setup_tickets(interaction: discord.Interaction):
    embed = discord.Embed(
        title="Support",
        description="Click the button below to open a private support ticket with our staff team.",
        color=discord.Color.dark_theme()
    )
    view = TicketCreateView()
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("Ticket panel deployed successfully!", ephemeral=True)

# --- ECONOMY & BANKING COMMANDS ---
@bot.tree.command(name="balance", description="Check your wallet and bank balance.")
async def balance(interaction: discord.Interaction, member: discord.Member = None):
    target = member or interaction.user
    wallet, bank = get_balance(target.id)
    embed = discord.Embed(title=f"💰 Balance for {target.name}", color=discord.Color.gold())
    embed.add_field(name="Wallet", value=f"${wallet:,}", inline=True)
    embed.add_field(name="Bank", value=f"${bank:,}", inline=True)
    embed.add_field(name="Total Net Worth", value=f"${wallet + bank:,}", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="deposit", description="Deposit cash from your wallet into your bank.")
async def deposit(interaction: discord.Interaction, amount: int):
    wallet, bank = get_balance(interaction.user.id)
    if amount <= 0 or wallet < amount:
        await interaction.response.send_message("Invalid amount or insufficient wallet cash.", ephemeral=True)
        return
    update_balance(interaction.user.id, wallet_change=-amount, bank_change=amount)
    await interaction.response.send_message(f"Successfully deposited **${amount:,}** into your bank account.")

@bot.tree.command(name="withdraw", description="Withdraw cash from your bank to your wallet.")
async def withdraw(interaction: discord.Interaction, amount: int):
    wallet, bank = get_balance(interaction.user.id)
    if amount <= 0 or bank < amount:
        await interaction.response.send_message("Invalid amount or insufficient bank funds.", ephemeral=True)
        return
    update_balance(interaction.user.id, wallet_change=amount, bank_change=-amount)
    await interaction.response.send_message(f"Successfully withdrew **${amount:,}** to your wallet.")

@bot.tree.command(name="pay", description="Transfer cash from your wallet to another player.")
async def pay(interaction: discord.Interaction, member: discord.Member, amount: int):
    if member.id == interaction.user.id:
        await interaction.response.send_message("You can't pay yourself!", ephemeral=True)
        return
    if amount <= 0:
        await interaction.response.send_message("Amount must be greater than zero.", ephemeral=True)
        return
    sender_wallet, _ = get_balance(interaction.user.id)
    if sender_wallet < amount:
        await interaction.response.send_message("You don't have enough cash in your wallet for this transfer.", ephemeral=True)
        return
    update_balance(interaction.user.id, wallet_change=-amount)
    update_balance(member.id, wallet_change=amount)
    await interaction.response.send_message(f"Successfully transferred **${amount:,}** to {member.mention}.")

# --- CASINO & GAMBLING COMMANDS ---
@bot.tree.command(name="coinflip", description="Flip a coin and double your money or lose it.")
@app_commands.choices(choice=[app_commands.Choice(name="Heads", value="heads"), app_commands.Choice(name="Tails", value="tails")])
async def coinflip(interaction: discord.Interaction, amount: int, choice: str):
    wallet, _ = get_balance(interaction.user.id)
    if amount <= 0 or wallet < amount:
        await interaction.response.send_message("Invalid amount or insufficient wallet cash.", ephemeral=True)
        return
    outcome = random.choice(["heads", "tails"])
    if choice.lower() == outcome:
        update_balance(interaction.user.id, wallet_change=amount)
        await interaction.response.send_message(f"🪙 It landed on **{outcome}**! You won **${amount:,}**!")
    else:
        update_balance(interaction.user.id, wallet_change=-amount)
        await interaction.response.send_message(f"🪙 It landed on **{outcome}**. You lost **${amount:,}**.")

# --- FACTION MANAGEMENT SYSTEM ---
@bot.tree.command(name="createfaction", description="Register a new faction.")
async def createfaction(interaction: discord.Interaction, name: str, color: str):
    conn = sqlite3.connect("dayz_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT faction_name FROM faction_members WHERE user_id = ?", (interaction.user.id,))
    if cursor.fetchone():
        conn.close()
        await interaction.response.send_message("You are already in a faction! Leave your current one first.", ephemeral=True)
        return
    
    cursor.execute("SELECT faction_name FROM factions WHERE faction_name = ?", (name,))
    if cursor.fetchone():
        conn.close()
        await interaction.response.send_message("A faction with this name already exists.", ephemeral=True)
        return

    cursor.execute("INSERT INTO factions (faction_name, leader_id, color) VALUES (?, ?, ?)", (name, interaction.user.id, color))
    cursor.execute("INSERT INTO faction_members (user_id, faction_name) VALUES (?, ?)", (interaction.user.id, name))
    conn.commit()
    conn.close()
    await interaction.response.send_message(f"🛡️ Faction **{name}** has been successfully created with color **{color}**!")

# --- RUNNER FOR BOTH UVICORN AND DISCORD ---
def run_fastapi():
    port = int(os.getenv("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    fastapi_thread = threading.Thread(target=run_fastapi, daemon=True)
    fastapi_thread.start()
    bot.run(TOKEN)