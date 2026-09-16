import os
import aiohttp
import sqlite3
import discord
from discord import app_commands
from discord.ui import View, Button

# --- CONFIGURATION & CREDENTIALS ---
TOKEN = os.getenv("DISCORD_TOKEN")
NITRADO_API_TOKEN = os.getenv("NITRADO_API_TOKEN")
NITRADO_SERVICE_ID = os.getenv("NITRADO_SERVICE_ID")

DEVELOPER_DISCORD_ID = 578271264779665438

# --- DATABASE SETUP (SQLite) ---
conn = sqlite3.connect("squatted_skill_feedz.db")
cursor = conn.cursor()
cursor.execute("""
    CREATE TABLE IF NOT EXISTS zones (
        server_id INTEGER,
        zone_name TEXT,
        zone_type TEXT,
        coords TEXT,
        radius REAL
    )
""")
conn.commit()

# --- BOT SETUP ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

class ZoneManagementView(View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Create Zone", style=discord.ButtonStyle.green, custom_id="create_zone_btn")
    async def create_zone(self, interaction: discord.Interaction, button: Button):
        await interaction.response.send_message("Zone creation workflow initiated. Enter zone name, type (Safe/PvP/Build Radar), and coordinates natively here.", ephemeral=True)

    @discord.ui.button(label="List Zones", style=discord.ButtonStyle.blurple, custom_id="list_zones_btn")
    async def list_zones(self, interaction: discord.Interaction, button: Button):
        cursor.execute("SELECT zone_name, zone_type FROM zones WHERE server_id = ?", (interaction.guild_id,))
        rows = cursor.fetchall()
        if not rows:
            await interaction.response.send_message("No custom zones configured for this server yet.", ephemeral=True)
            return
        zone_list = "\n".join([f"- **{name}** ({ztype})" for name, ztype in rows])
        await interaction.response.send_message(f"**Configured Zones:**\n{zone_list}", ephemeral=True)

@bot.event
async def on_ready():
    # Register persistent views to prevent UI timeouts
    bot.add_view(ZoneManagementView())
    # Sync slash commands with Discord
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s).")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
        
    print(f"Logged in as {bot.user} | Connected to Nitrado Service: {NITRADO_SERVICE_ID}")

@bot.tree.command(name="zones", description="Manage DayZ server safe zones, PvP boundaries, and build radars.")
async def zones_command(interaction: discord.Interaction):
    """Native Discord slash command interface for managing zones and radars."""
    if interaction.user.id != DEVELOPER_DISCORD_ID:
        # Standard subscription check logic can go here for non-developers
        pass

    embed = discord.Embed(
        title="SquattedSkillFeedZ - Native Zone & Radar System",
        description="Manage your DayZ server safe zones, PvP boundaries, and build radars directly through Discord.",
        color=discord.Color.dark_red()
    )
    embed.add_field(name="Nitrado Integration", value=f"Active Service ID: `{NITRADO_SERVICE_ID}`", inline=False)
    
    view = ZoneManagementView()
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@bot.tree.command(name="nitradotest", description="Tests the connection to the Nitrado API using your token and service ID.")
async def nitrado_test(interaction: discord.Interaction):
    """Tests the connection to the Nitrado API via slash command."""
    if interaction.user.id != DEVELOPER_DISCORD_ID:
        pass
        
    await interaction.response.defer(ephemeral=True)
    
    headers = {"Authorization": f"Bearer {NITRADO_API_TOKEN}"}
    url = f"https://api.nitrado.net/services/{NITRADO_SERVICE_ID}"
    
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                status = data.get("data", {}).get("service", {}).get("status", "unknown")
                await interaction.followup.send(f"Successfully connected to Nitrado! Server Status: `{status}`", ephemeral=True)
            else:
                await interaction.followup.send(f"Failed to connect to Nitrado API. HTTP Status: {resp.status}", ephemeral=True)

if __name__ == "__main__":
    if not TOKEN:
        print("Error: DISCORD_TOKEN is missing.")
    else:
        bot.run(TOKEN)
