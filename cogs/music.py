import os
import discord
import wavelink
from discord.ext import commands, tasks
from discord_slash import cog_ext, SlashContext
from dotenv import load_dotenv

import data
from data import db

load_dotenv(".env")
def _is_connected(ctx):
    voice_client = discord.utils.get(ctx.bot.voice_clients, guild=ctx.guild)
    return voice_client and voice_client.is_connected()


#Must start Lavalink.jar with java -jar Lavalink.jar
class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.loop.create_task(self.connect_nodes())

    play_options = [
        {
            "name": "video",
            "description": "A valid Youtube URL for the bot to play.",
            "required": True,
            "type": 3
        }
    ]

    async def connect_nodes(self):
        await self.bot.wait_until_ready()
        await wavelink.NodePool.create_node(
            bot=self.bot,
            host=os.getenv("MUSIC_IP"),
            port=2333,
            password=os.getenv("MUSIC_PASS")
        )

#Need to add handling disconnects as the bot bugs out
    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node: wavelink.Node):
        print(f'Node: <{node.identifier}> is ready!')


    @cog_ext.cog_slash(name="join", description="Makes the bot join a valid voice channel.")
    async def _join(self, ctx : SlashContext):
        #This is not used in _play() as the wavelink context would not be transferred when joining.
        await ctx.defer()
        if ctx.author.voice is None:
            await ctx.send("You're not in a voice channel!")
        else:
            if not ctx.voice_client:
                await ctx.author.voice.channel.connect(cls=wavelink.Player)
                await ctx.send("Successfully connected to {0}!".format(ctx.author.voice.channel))
            else:
                await ctx.voice_client.move_to(ctx.author.voice.channel)
                await ctx.send(f"Successfully moved to `{ctx.author.voice.channel}`!")


    @cog_ext.cog_slash(name="play", description="Play audio from a URL or from a search query.", options=play_options)
    async def _play(self, ctx : SlashContext, *, video : str):
        await ctx.defer()
        try:
            if not ctx.voice_client:
                vc: wavelink.Player = await ctx.author.voice.channel.connect(cls=wavelink.Player)
            else:
                vc: wavelink.Player = ctx.voice_client
        except Exception as e:
            await ctx.send("Unable to join channel, please specify a valid channel or join one.")

        track = await wavelink.YouTubeTrack.search(query=video, return_first=True)
        await vc.play(track)
        await ctx.send("Now playing: " + track.title)

    @cog_ext.cog_slash(name="disconnect", description="Disconnects the bot from voice")
    async def _disconnect(self, ctx : SlashContext):
        if ctx.author.voice is None or not ctx.voice_client:
            await ctx.send("You're not in a voice channel!")
        else:
            await ctx.voice_client.disconnect(force=True)
            await ctx.send("Disconnected from voice!")




def setup(bot):
    bot.add_cog(Music(bot))
