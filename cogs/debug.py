import discord

from .motd import choose_motd
from discord.ext import commands
from discord import app_commands
from discord.app_commands import checks

# This checks if it is me
def is_dev(interaction: discord.Interaction):
    return interaction.user.id == 163045781316698112

# These commands don't have help pages because they are merely debug commands and aren't for normal use.
class Debug(commands.Cog):
    def __init__(self, bot : commands.Bot):
        super().__init__()
        self.bot = bot

    @app_commands.check(is_dev)
    @app_commands.command(name="shuffle_status", description="DEBUG: Changes the bot's status")
    async def _shuffle_status(self, interaction: discord.Interaction):
        await self.bot.change_presence(activity=discord.Activity(name=choose_motd(self.bot.activity.name if self.bot.activity is not None else None), type=1))
        await interaction.response.send_message("Shuffled!", ephemeral=True)

    @app_commands.command(name="ping", description="DEBUG: Gets the latency of the bot")
    async def _ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(f'Pong! ({round(interaction.client.latency * 1000)}ms)')


async def setup(bot : commands.Bot):
    await bot.add_cog(Debug(bot))