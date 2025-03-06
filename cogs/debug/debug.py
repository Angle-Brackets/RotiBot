import discord
import pathlib
import json

from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
from utils.RotiUtilities import cog_command

# These commands don't have help pages because they are merely debug commands and aren't for normal use.
@cog_command
class Debug(commands.Cog):
    def __init__(self, bot : commands.Bot):
        super().__init__()
        self.bot = bot

    # Developer-only commands as message commands.
    @commands.is_owner()
    @commands.command(name="shuffle_status", help="DEBUG: Changes the bot's status")
    async def _shuffle_status(self, ctx: commands.Context):
        motd_cog = self.bot.get_cog("Motd")

        if not motd_cog:
            await ctx.send("MOTD Cog couldn't be found!", ephemeral=True)
            return

        new_motd = motd_cog.choose_motd(self.bot.activity.name if self.bot.activity else None)

        await ctx.message.delete()
        await self.bot.change_presence(activity=discord.Activity(name=new_motd, type=discord.ActivityType.playing))
        await ctx.send("Shuffled!", ephemeral=True)

    @commands.is_owner()
    @commands.command(name="say", help="DEBUG: Make Roti say anything")
    async def _say(self, ctx: commands.Context, *, text: str):
        await ctx.message.delete()  # Optionally delete the original message
        await ctx.send(text)

    @commands.is_owner()
    @commands.command(name="reload", help="DEBUG: Hot loads all commands")
    async def _reload(self, ctx: commands.Context):
        reloaded = []
        failed = []
        for extension in list(self.bot.extensions.keys()):
            try:
                await self.bot.reload_extension(extension)
            except commands.ExtensionError:
                failed.append(extension)
            except commands.ExtensionNotLoaded:
                continue
            else:
                reloaded.append(extension)

        result = f"Successfully Reloaded:\n{', '.join(reloaded)}\n\nFailed to reload:\n{', '.join(failed)}"
        await ctx.send(result,ephemeral=True)

    @commands.is_owner()
    @commands.command(name="leave", help="DEBUG: Instructs Roti to leave a server")
    async def _leave(self, ctx: commands.Context, guild_id: int):
        guild = discord.utils.get(self.bot.guilds, id=guild_id)
        
        if guild:
            await guild.leave()
            await ctx.send(f"Successfully left {guild.name}", ephemeral=True)
        else:
            await ctx.send("Invalid guild ID or Roti is not in a server with that ID.", ephemeral=True)
        await ctx.message.delete()

    @commands.is_owner()
    @commands.command(name="reload", description="DEBUG: Hot loads all commands")
    async def _reload(self, ctx: commands.Context):
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
        await ctx.send(result, ephemeral=True)
    
    @commands.is_owner()
    @commands.command(name="logs", description="DEBUG: Displays the last N logs")
    async def _logs(self, ctx: commands.Context, n : int = 5):
        # Checks if the directory exists, if not, makes it.
        log_file = pathlib.Path("logs/roti.log.jsonl")
        n = min(10, max(1, n))

        if not log_file.exists():
            await ctx.send("Log file not found.", ephemeral=True, delete_after=10)
            return

        msg = []
        with open(log_file, "r") as f:
            # Read last 10 lines 
            f.seek(0, 2)  # Move cursor to the end of file
            pos = f.tell()
            lines = []
            while pos > 0 and len(lines) < n:
                pos -= 1
                f.seek(pos)
                if f.read(1) == "\n":
                    line = f.readline().strip()
                    if line:
                        lines.append(line)

        # Parse logs and format messages
        for line in reversed(lines):
            log = json.loads(line)
            msg.append(f"[{log['level']}]\n{log['message'][:(1950//n)]}")

        result = f"```{"\n\n".join(msg[::-1])[:1950]}```"
        await ctx.send(result, ephemeral=True, delete_after=30)

    # Misc Debug Commands - Anyone can use.
    @app_commands.command(name="ping", description="DEBUG: Gets the latency of the bot")
    async def _ping(self, interaction: discord.Interaction):
        interaction_creation_time = interaction.created_at
        response_time = datetime.now(tz=timezone.utc)
        latency = (response_time - interaction_creation_time).total_seconds()
        await interaction.response.send_message(f'Pong! ({round(latency * 1000)}ms)', delete_after=5)

async def setup(bot : commands.Bot):
    await bot.add_cog(Debug(bot))