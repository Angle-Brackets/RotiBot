import discord
import random
import database.data as data
import logging

from returns.result import Success, Failure
from typing import Optional
from discord import app_commands
from discord.ext import commands, tasks
from database.data import RotiDatabase, MotdTable
from utils.RotiUtilities import cog_command

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
        await interaction.response.defer(ephemeral=True)

        if len(motd) > 128:
            await interaction.followup.send("Failed to add given Message of the Day - Message exceeded max of 128 characters.")
        else:
            old = await self.db.select(MotdTable, user_id=interaction.user.id)
            self.db.upsert(MotdTable, user_id=interaction.user.id, motd=motd)

            if old and old.motd:
                await interaction.followup.send(f"Successfully added new message of the day: \"{motd}\"\n Overwrote previous entry: \"{old.motd}\"")
            else:
                await interaction.followup.send(f"Successfully added new message of the day: \"{motd}\"")

    @app_commands.command(name="clear", description="Removes the \"Message of the Day\" associated with you.")
    async def _motd_clear(self, interaction : discord.Interaction):
        await interaction.response.defer()
        old = await self.db.select(MotdTable, user_id=interaction.user.id)

        if old and old.motd:
            self.db.update(MotdTable, user_id=interaction.user.id, motd="") # Blank String is the same as none, cheaper than an entire DELETE.
            await interaction.followup.send(f"Successfully cleared MOTD associated with you {old.motd}")
        else:
            await interaction.followup.send("There is no MOTD associated with you currently, add one using /motd add!")

    @app_commands.command(name="show", description="Shows the \"Message of the Day\" associated with you.")
    async def _motd_show(self, interaction : discord.Interaction):
        await interaction.response.defer()
        old = await self.db.select(MotdTable, user_id=interaction.user.id)
        if old and old.motd:
            await interaction.followup.send(f"The current MOTD associated with you is: \"{old}\"")
        else:
            await interaction.followup.send("There is no MOTD associated with you currently, add one using /motd add!")


    async def choose_motd(self, current_motd : Optional[str]):
        # Escape single quotes by doubling them
        safe_current = current_motd.replace("'", "''") if current_motd else ""
        
        query = f"""
        SELECT * FROM "Motd"
        WHERE "motd" != '{safe_current}' AND "motd" != ''
        ORDER BY RANDOM()
        LIMIT 1
        """

        match await self.db.raw_query(query):
            case Success(row):
                return self.db._dict_to_dataclass(MotdTable, row[0]).motd
            case Failure(error):
                self.logger.error(f"Failed to read MOTD table %s", error)
                return ""
        
    @tasks.loop(hours=3)
    async def motd_swap(self):
        new_motd = await self.choose_motd(self.bot.activity.name if self.bot.activity else "")
        await self.bot.change_presence(activity=discord.Activity(name=new_motd, type=discord.ActivityType.playing))

    @motd_swap.before_loop
    async def startup(self):
        self.logger.info("Initializing MOTD...")
        await self.bot.wait_until_ready()
        self.logger.info("MOTD Initialization Complete.")

async def setup(bot: commands.Bot):
    await bot.add_cog(Motd(bot))