import discord
import random
import database.data as data
import logging

from typing import Optional
from discord import app_commands
from discord.ext import commands, tasks
from database.data import RotiDatabase
from utils.command_utils import cog_command

@cog_command
class Motd(commands.GroupCog, group_name="motd"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.motd_swap.start()
        self.db = RotiDatabase()

    @app_commands.describe(motd = "A phrase to displayed in Roti's status.")
    @app_commands.command(name="add", description="Add a \"Message of the Day\" to the bot to be displayed in its status")
    async def _motd_add(self, interaction : discord.Interaction, motd : str):
        await interaction.response.defer()
        motd_entry = self.db[interaction.guild_id, "motd"].unwrap()

        if len(motd) > 128:
            await interaction.followup.send("Failed to add given Message of the Day - Message exceeded max of 128 characters.")
        else:
            self.db[interaction.guild_id, "motd"] = motd

            # If the motd database entry is non-empty for a server
            if motd_entry:
                await interaction.followup.send(f"Successfully added new message of the day: \"{motd}\"\n Overwrote previous entry: \"{motd_entry}\"")
            else:
                await interaction.followup.send(f"Successfully added new message of the day: \"{motd}\"")

    @app_commands.command(name="clear", description="Removes the \"Message of the Day\" associated with this guild.")
    async def _motd_clear(self, interaction : discord.Interaction):
        await interaction.response.defer()
        motd_entry = self.db[interaction.guild_id, "motd"].unwrap()

        if motd_entry:
            self.db[interaction.guild_id, "motd"] = ""
            await interaction.followup.send(f"Successfully cleared MOTD associated with this guild: {motd_entry}")
        else:
            await interaction.followup.send("There is no MOTD associated with this server currently, add one using /motd add!")

    @app_commands.command(name="show", description="Shows the \"Message of the Day\" associated with this guild.")
    async def _motd_show(self, interaction : discord.Interaction):
        await interaction.response.defer()
        motd = self.db[interaction.guild_id, "motd"].unwrap()
        if motd:
            await interaction.followup.send(f"The current MOTD associated with this server is: \"{motd}\"")
        else:
            await interaction.followup.send("There is no MOTD associated with this server currently, add one using /motd add!")


    def choose_motd(self, current_motd : Optional[str]):
        guild_ids = {guild.id for guild in self.bot.guilds}
        to_remove = set()
        
         # Removes current MOTD present on bot (prevents repeats) and blank MOTDs.
        if current_motd:
            for guild_id in guild_ids:
                if not self.db[guild_id, "motd"].unwrap() or self.db[guild_id, "motd"].unwrap() == current_motd:
                    to_remove.add(guild_id)
        
        guild_ids -= to_remove
        return self.db[random.choice(list(guild_ids)), "motd"].unwrap()

    @tasks.loop(hours=3)
    async def motd_swap(self):
        await self.bot.change_presence(activity=discord.Activity(name=self.choose_motd(self.bot.activity.name if self.bot.activity else None), type=discord.ActivityType.playing))

    @motd_swap.before_loop
    async def startup(self):
        self.logger.info("Initializing MOTD...")
        await self.bot.wait_until_ready()
        self.logger.info("MOTD Initialization Complete.")

async def setup(bot: commands.Bot):
    await bot.add_cog(Motd(bot))