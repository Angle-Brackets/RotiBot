import discord
import os
from discord.ext import commands
from discord_slash import cog_ext, SlashContext


class Motd(commands.Cog):
	def __init__(self, bot):
		self.bot = bot

	@cog_ext.cog_slash(name="motd", description="WIP")
	async def _motd(self, ctx: SlashContext):
		await ctx.send("testing...")

def setup(bot):
	bot.add_cog(Motd(bot))
