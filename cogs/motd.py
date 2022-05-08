import discord
import random
import data
from discord import app_commands
from discord.ext import commands, tasks
from data import db

def choose_motd(current_motd=None):
    keys = list(db.keys())

    # Removes current MOTD present on bot (prevents repeats) and blank MOTDs.
    # It's written this way because sets are unordered, meaning the list will be unordered, so this ignores order and just compares strings.
    for key in keys:
        if (current_motd is not None and db[key]["motd"] is current_motd) or not db[key]["motd"]:
            keys.remove(key)

    return db[random.choice(keys)]["motd"]

class Motd(commands.GroupCog, group_name="motd"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.motd_swap.start()

    @app_commands.describe(motd = "A phrase to displayed in Roti's status.")
    @app_commands.command(name="add", description="Add a \"Message of the Day\" to the bot to be displayed in its status")
    async def _motd_add(self, interaction : discord.Interaction, motd : str):
        await interaction.response.defer()
        motd_entry = str(db[interaction.guild_id]["motd"])

        if len(motd) > 128:
            await interaction.followup.send("Failed to add given Message of the Day - Message exceeded max of 128 characters.")
        else:
            db[interaction.guild_id]["motd"] = motd
            data.push_data(interaction.guild_id, "motd")

            # If the motd database entry is empty for a server
            if motd_entry:
                await interaction.followup.send("Successfully added new message of the day: \"{0}\"\n Overwrote previous entry: \"{1}\"".format(
                        motd, motd_entry))
            else:
                await interaction.followup.send("Successfully added new message of the day: \"{0}\"".format(motd))

    @app_commands.command(name="clear", description="Removes the \"Message of the Day\" associated with this guild.")
    async def _motd_clear(self, interaction : discord.Interaction):
        await interaction.response.defer()
        motd_entry = db[interaction.guild_id]["motd"]

        if motd_entry:
            db[interaction.guild_id]["motd"] = ""
            data.push_data(interaction.guild_id, "motd")
            await interaction.followup.send("Successfully cleared MOTD associated with this guild: {0}".format(motd_entry))
        else:
            await interaction.followup.send("There is no MOTD associated with this server currently, add one using /motd add!")

    @app_commands.command(name="show", description="Shows the \"Message of the Day\" associated with this guild.")
    async def _motd_show(self, interaction : discord.Interaction):
        await interaction.response.defer()
        if db[interaction.guild_id]["motd"]:
            await interaction.followup.send("The current MOTD associated with this server is: \"{0}\"".format(db[interaction.guild_id]["motd"]))
        else:
            await interaction.followup.send("There is no MOTD associated with this server currently, add one using /motd add!")

    @tasks.loop(hours=3)
    async def motd_swap(self):
        await self.bot.change_presence(activity=discord.Activity(name=choose_motd(self.bot.activity.name if self.bot.activity is not None else None), type=1))

    @motd_swap.before_loop
    async def startup(self):
        print("Initializing...")
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(Motd(bot))