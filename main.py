@bot.tree.command(name="rob", description="Attempt to rob another user's pocket cash")
async def rob_player(interaction: discord.Interaction, target: discord.Member):
    if target.id == interaction.user.id:
        await interaction.response.send_message("You cannot rob yourself!", ephemeral=True)
        return

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT pocket_balance FROM economy WHERE discord_id = ?", (interaction.user.id,))
    author_row = cursor.fetchone()
    author_pocket = author_row[0] if author_row else 0.0

    cursor.execute("SELECT pocket_balance FROM economy WHERE discord_id = ?", (target.id,))
    target_row = cursor.fetchone()
    target_pocket = target_row[0] if target_row else 0.0

    if author_pocket < 100.0:
        conn.close()
        await interaction.response.send_message("You need at least $100.00 in your pocket cash to attempt a robbery!", ephemeral=True)
        return

    if target_pocket < 50.0:
        conn.close()
        await interaction.response.send_message("That target doesn't have enough pocket cash worth stealing.", ephemeral=True)
        return

    success = random.choice([True, False])
    if success:
        steal_amount = round(target_pocket * random.uniform(0.1, 0.3), 2)
        cursor.execute("UPDATE economy SET pocket_balance = pocket_balance + ? WHERE discord_id = ?", (steal_amount, interaction.user.id))
        cursor.execute("UPDATE economy SET pocket_balance = pocket_balance - ? WHERE discord_id = ?", (steal_amount, target.id))
        conn.commit()
        conn.close()
        await interaction.response.send_message(f"🥷 **Successful Heist!** You ambushed {target.mention} and successfully stole **${steal_amount:,.2f}** from their pocket.")
    else:
        fine_amount = min(author_pocket, 150.0)
        cursor.execute("UPDATE economy SET pocket_balance = pocket_balance - ? WHERE discord_id = ?", (fine_amount, interaction.user.id))
        conn.commit()
        conn.close()
        await interaction.response.send_message(f"🚨 **Busted!** You tried to rob {target.mention}, got caught, and paid a fine of **${fine_amount:,.2f}**.")