import discord
from discord.ext import commands
import json
import os

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

ECONOMY_FILE = "economy.json"

def load_economy():
    if not os.path.exists(ECONOMY_FILE):
        return {}
    with open(ECONOMY_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_economy(data):
    with open(ECONOMY_FILE, "w") as f:
        json.dump(data, f, indent=4)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name} (ID: {bot.user.id})")
    print("--------------------------------------------------")

@bot.command(name="addmoney")
@commands.has_permissions(administrator=True)
async def add_money(ctx, member: discord.Member, amount: int):
    if amount <= 0:
        await ctx.send("Please specify an amount greater than 0.")
        return

    data = load_economy()
    user_id = str(member.id)
    
    if user_id not in data:
        data[user_id] = {"balance": 0}
        
    data[user_id]["balance"] += amount
    save_economy(data)
    
    new_balance = data[user_id]["balance"]
    await ctx.send(f"Successfully added ${amount:,} to {member.mention}'s balance. New balance: ${new_balance:,}")

@bot.command(name="removemoney")
@commands.has_permissions(administrator=True)
async def remove_money(ctx, member: discord.Member, amount: int):
    if amount <= 0:
        await ctx.send("Please specify an amount greater than 0.")
        return

    data = load_economy()
    user_id = str(member.id)
    
    if user_id not in data:
        data[user_id] = {"balance": 0}
        
    data[user_id]["balance"] = max(0, data[user_id]["balance"] - amount)
    save_economy(data)
    
    new_balance = data[user_id]["balance"]
    await ctx.send(f"Successfully removed ${amount:,} from {member.mention}'s balance. New balance: ${new_balance:,}")

@add_money.error
@remove_money.error
async def economy_error(ctx, error):
    if isinstance(error, commands.MissingPermissions):
        await ctx.send("You do not have permission to use this command. Administrator rights are required.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send("Missing arguments. Usage: `!addmoney @User [amount]` or `!removemoney @User [amount]`")
    elif isinstance(error, commands.BadArgument):
        await ctx.send("Invalid argument format. Make sure you are mentioning a valid user and providing a whole number for the amount.")
    else:
        await ctx.send(f"An error occurred: {error}")

# bot.run('YOUR_BOT_TOKEN_HERE')
