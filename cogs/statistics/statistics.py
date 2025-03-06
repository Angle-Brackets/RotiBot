import discord
import itertools

from typing import Dict
from discord.ext import commands
from discord import app_commands
from database.data import RotiDatabase
from utils.RotiUtilities import cog_command
from cogs.statistics.statistics_helpers import FunctionStatistics, get_statistics, pretty_print_usage_statistics

@cog_command
class Statistics(commands.GroupCog, group_name="statistics"):
    def __init__(self, bot : commands.Bot):
        super().__init__()
        self.bot = bot
        self.db = RotiDatabase()

    @app_commands.command(name="performance", description="View the performance statistics for Roti.")
    async def _perf_statistics(self, interaction : discord.Interaction):
        await interaction.response.send_message(embed=self._build_statistic_embed(), ephemeral=True)
    
    @app_commands.command(name="usage", description="View the usage statistics for Roti.")
    async def _usage_statistics(self, interaction : discord.Interaction):
        await interaction.response.send_message(pretty_print_usage_statistics(self.db, [guild.id for guild in self.bot.guilds]), ephemeral=True)

    def _build_statistic_embed(self) -> discord.Embed:
        """
        Builds the displayed embed for the statistics, groups by categories.
        """
        stats : Dict[str, FunctionStatistics] = get_statistics()
        stats  = sorted(stats.items(), key=lambda item: (item[1].function_info.category is None, item[1].function_info.category))
        embed = discord.Embed(
            title="Roti Statistics",
            description="These are some global statistics on how Roti is performing across all the servers it's in. They're mostly for debug purposes, but they're still fun to look at.",
            colour=0xecc98e
        )

        for category, group in itertools.groupby(iterable=stats, key=lambda item : item[1].function_info.category):
            for func, stat in group:
                embed.add_field(
                    name=stat.function_info.display_name,
                    value= \
                    f"""
                    Shortest Execution Time: {stat.shortest_exec_time:.6f}s
                    Longest Execution Time: {stat.longest_exec_time:.6f}s
                    Average Execution Time: {stat.average_exec_time:.6f}s
                    Times Invoked: {stat.times_invoked}
                    """,
                    inline=False
                )
        
        return embed

async def setup(bot : commands.Bot):
    await bot.add_cog(Statistics(bot))