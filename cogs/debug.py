import discord
import pathlib
import os

from .motd import choose_motd
from discord.ext import commands
from discord import app_commands
from discord.app_commands import checks
from datetime import datetime, timezone

# These commands don't have help pages because they are merely debug commands and aren't for normal use.
class Debug(commands.Cog):
    def __init__(self, bot : commands.Bot):
        super().__init__()
        self.bot = bot

    # Developer only commands.
    @commands.is_owner()
    @app_commands.command(name="shuffle_status", description="DEBUG: Changes the bot's status")
    async def _shuffle_status(self, interaction: discord.Interaction):
        await self.bot.change_presence(activity=discord.Activity(name=choose_motd(self.bot.activity.name if self.bot.activity is not None else None), type=1))
        await interaction.response.send_message("Shuffled!", ephemeral=True)

    @commands.is_owner()
    @app_commands.command(name="say", description="DEBUG: Make Roti say anything")
    async def _say(self, interaction : discord.Interaction, text : str):
        await interaction.response.defer()
        await interaction.followup.send(text)

    @commands.is_owner()
    @app_commands.command(name="reload", description="DEBUG: Hot loads all commands")
    async def _reload(self, interaction : discord.Interaction):
        reloaded = []
        failed = []
        for extension in list(self.bot.extensions.keys()):
            # From: https://gist.github.com/AXVin/08ed554a458fc7aee4da162f4c53d086
            try:
                await self.bot.reload_extension(extension)
            except commands.ExtensionError:
                failed.append(extension)
            except commands.ExtensionNotLoaded:
                continue
            else:
                reloaded.append(extension)

        result = f"Successfully Reloaded:\n{"\n".join(reloaded)}\n\nFailed to reload:\n{"\n".join(failed)}"
        await interaction.response.send_message(result, ephemeral=True)

    # Misc Debug Commands - Anyone can use.
    @app_commands.command(name="ping", description="DEBUG: Gets the latency of the bot")
    async def _ping(self, interaction: discord.Interaction):
        interaction_creation_time = interaction.created_at
        response_time = datetime.now(tz=timezone.utc)
        latency = (response_time - interaction_creation_time).total_seconds()
        await interaction.response.send_message(f'Pong! ({round(latency * 1000)}ms)', delete_after=5)
    

async def setup(bot : commands.Bot):
    await bot.add_cog(Debug(bot))