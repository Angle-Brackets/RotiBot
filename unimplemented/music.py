import random
import discord
import wavelink
from discord.ext import commands, tasks
from discord_slash import cog_ext, SlashContext

import data
from data import db

"""
STILL HAVE NOT ADDED THIS BECAUSE THE ENTIRE LIBRARY WAS REWRITTEN SO IT REQUIRES A REWRITE!
"""

def _generate_queue_embed(queue):
	embed = discord.Embed(title="Music Queue:", color=0xecc98e)

	for i in range(len(queue)):
		embed.add_field(name="{0}. {1}".format(i + 1, queue[i]), value='\u200b', inline=False)
		
	return embed

class Music(commands.Cog):
	def __init__(self, bot):
		self.bot = bot

		if not hasattr(bot, 'wavelink'):
			self.bot.wavelink = wavelink.Client(bot = self.bot)
		
		self.bot.loop.create_task(self.start_nodes())
	
	async def start_nodes(self):
		await self.bot.wait_until_ready()
		
		await self.bot.wavelink.initiate_node(
			host = "0.0.0.0",
			port = 2333,
			rest_uri = "http://0.0.0.0:2333",
			password = "youshallnotpass",
			identifier = "MAIN",
			region = "us_central"
		)
		print("Nodes Connected")

	play_options = [
		{
			"name": "video",
			"description": "A valid Youtube URL for the bot to play.",
			"required": True,
			"type": 3
		}
	]

	@cog_ext.cog_slash(name="join", description="Makes the bot join a valid voice channel.")
	async def _join(self, ctx : SlashContext, *, channel : discord.VoiceChannel = None):
		if not channel:
			try:
				channel = ctx.author.voice.channel
			except AttributeError:
				await ctx.send("No channel to join, please specify a valid channel or join one.")
				return
		
		player = self.bot.wavelink.get_player(ctx.guild.id)
		await ctx.send(f"Connecting to **`{channel.name}`**")
		await player.connect(channel.id)

	
	@cog_ext.cog_slash(name="disconnect", description="Makes the bot disconnect from a voice channel.")
	async def _disconnect(self, ctx: SlashContext):
		await ctx.defer()
		await ctx.voice_client.disconnect(force=True)
		db[ctx.guild.id]["music_queue"].clear()
		data.push_data(ctx.guild.id, "music_queue")
		await ctx.send("Disconnected from voice.")
	
	@cog_ext.cog_slash(name="pause", description="Pauses the audio Roti's playing.")
	async def _pause(self, ctx : SlashContext):
		await ctx.defer()
		await ctx.voice_client.pause()
		await ctx.send("Paused music in voice.")
	
	@cog_ext.cog_slash(name="resume", description="Resumes the audio Roti was playing.")
	async def _resume(self, ctx : SlashContext):
		await ctx.defer()
		await ctx.voice_client.resume()
		await ctx.send("Resuming music in voice.")
	
	@cog_ext.cog_slash(name="play", description="The bot will audio from a valid URL in a voice channel.", options=play_options)
	async def _play(self, ctx : SlashContext, *, video = str):
		tracks = await self.bot.wavelink.get_tracks(f'ytsearch:{video}')

		if not tracks:
			return await ctx.send("Could not find any soungs with that query.")
		
		player = self.bot.wavelink.get_player(ctx.guild.id)

		if not player.is_connected:
			await ctx.invoke(self._join)
		
		await ctx.send(f"Added {str(tracks[0])} to the queue.")
		await player.play(tracks[0])


def setup(bot):
	bot.add_cog(Music(bot))
	