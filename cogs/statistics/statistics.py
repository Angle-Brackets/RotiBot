import discord

from discord.ext import commands
from discord import app_commands
from database.data import RotiDatabase
from utils.RotiUtilities import cog_command
from cogs.statistics.statistics_helpers import pretty_print_statistics, pretty_print_usage_statistics

@cog_command
class Statistics(commands.GroupCog, group_name="statistics"):
    def __init__(self, bot : commands.Bot):
        super().__init__()
        self.bot = bot
        self.db = RotiDatabase()

    @app_commands.command(name="performance", description="View the performance statistics for Roti.")
    async def _perf_statistics(self, interaction : discord.Interaction):
        await interaction.response.send_message(pretty_print_statistics(), ephemeral=True)
    
    @app_commands.command(name="usage", description="View the usage statistics for Roti.")
    async def _usage_statistics(self, interaction : discord.Interaction):
        await interaction.response.send_message(pretty_print_usage_statistics(self.db, [guild.id for guild in self.bot.guilds]), ephemeral=True)

async def setup(bot : commands.Bot):
    await bot.add_cog(Statistics(bot))