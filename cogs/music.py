import os
import time

import discord
import discord_slash.model
import wavelink
from discord.ext import commands, tasks
from discord_slash import cog_ext, SlashContext
from dotenv import load_dotenv
load_dotenv(".env")


def _is_connected(ctx):
    voice_client = discord.utils.get(ctx.bot.voice_clients, guild=ctx.guild)
    return voice_client and voice_client.is_connected()


def _generate_queue_embed(vc : wavelink.Player):
    queue = vc.queue
    embed = discord.Embed(title="Music Queue:", description="Currently playing: {0} [{1}/{2}]".format(queue.__getitem__(0), time.strftime("%H:%M:%S", time.gmtime(vc.position)), time.strftime("%H:%M:%S", time.gmtime(queue.__getitem__(0).duration))), color=0xecc98e)

    for i in range(len(queue)):
        embed.add_field(name="{0}. {1} - [{2}]".format(i + 1, queue.__getitem__(i), time.strftime("%H:%M:%S", time.gmtime(queue.__getitem__(i).duration))), value='\u200b', inline=False)

    #Gets the thumbnail to the current video playing
    embed.set_thumbnail(url="https://img.youtube.com/vi/{0}/maxresdefault.jpg".format(queue.__getitem__(0).info.get("identifier")))
    return embed


#Must start Lavalink.jar with java -jar Lavalink.jar

"""
Note about the implementation of the queue for this bot, while it might seem strange, I am de-queueing only when 
the song finishes rather than when it starts in order to display all the songs in /queue to avoid confusion.
"""
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

    #Will update this later when I migrate everything to use interactions rather than the old slash library
    #TODO: Will later include track, queue, and single song looping options. Currently only supports single song.
    loop_options = [
        {
            "name": "mode",
            "description": "The new looping mode",
            "required": True,
            "type": discord_slash.SlashCommandOptionType.BOOLEAN
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

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node: wavelink.Node):
        print(f'Node: <{node.identifier}> is ready!')

    #Handles disconnecting
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if before.channel is not None and after.channel is None:
            if len(before.channel.members) >= 1:
                for connected in before.channel.members:
                    if not connected.bot:
                        return  # Exits the loop as there are members that are still in the channel that aren't bots

                # Will now disconnect and clear queue
                try:
                    vc: wavelink.Player = discord.utils.get(self.bot.voice_clients, guild=before.channel.guild)
                    await vc.stop() #Stops song immediately
                    vc.queue.reset()
                    await vc.disconnect()
                except AttributeError as ae:
                    pass

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, player: wavelink.Player, track, reason):
        #Handling looping of the song
        if not player.queue.is_empty and not player.skipped and player.looped:
            await player.play(player.queue.__getitem__(0))
        else:
            if not player.queue.is_empty:
                player.queue.get() #Dequeues current song
                player.skipped = False
                if not player.queue.is_empty:
                    track = player.queue.__getitem__(0) #DO NOT DEQUEUE THIS UNTIL ITS DONE!!!
                    await player.play(track)
                #Not sure how to send a message to say a new song is playing...

    @cog_ext.cog_slash(name="join", description="Makes the bot join a valid voice channel.")
    async def _join(self, ctx : SlashContext):
        #This is not used in _play() as the wavelink context would not be transferred when joining.
        await ctx.defer()
        if ctx.author.voice is None:
            await ctx.send("I'm not in a voice channel!")
        else:
            if not ctx.voice_client:
                vc : wavelink.Player = await ctx.author.voice.channel.connect(cls=wavelink.Player)

                vc.looped = False # Field to describe is current song is looped - overriden by skipped
                vc.skipped = False # Field to describe if current song was skipped - used to override loop

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
                vc.looped = False # Initializes custom parameter looped
                vc.skipped = False # Field to describe if current song was skipped - used to override loop
            else:
                vc: wavelink.Player = ctx.voice_client
        except Exception as e:
            await ctx.send("Unable to join channel, please specify a valid channel or join one.")
            return

        track = await wavelink.YouTubeTrack.search(query=video, return_first=True)
        #Will add queue interaction and pause checking soon
        if not vc.queue.is_empty:
            vc.queue.put(track)
            await ctx.send(f"Added {track.title} to the queue!")
        else:
            await vc.play(track)
            vc.queue.put(track)
            await ctx.send("Now playing: " + track.title)

    @cog_ext.cog_slash(name="pause", description="Pauses the Music.")
    async def _pause(self, ctx : SlashContext):
        await ctx.defer()
        if ctx.author.voice is None or not ctx.voice_client:
            await ctx.send("I'm not in a voice channel!")
        else:
            vc : wavelink.Player = ctx.voice_client

            if not vc.is_paused():
                await vc.pause()
                await ctx.send("Paused!")
            else:
                await ctx.send("Music is currently paused! Use /resume to resume music!")

    @cog_ext.cog_slash(name="resume", description="Resumes the Music.")
    async def resume(self, ctx: SlashContext):
        await ctx.defer()
        if ctx.author.voice is None or not ctx.voice_client:
            await ctx.send("I'm not in a voice channel!")
        else:
            vc: wavelink.Player = ctx.voice_client

            if not vc.is_paused():
                await ctx.send("Music is not currently paused! Use /pause to stop the music!")
            else:
                await vc.resume()
                await ctx.send("Resumed!")

    @cog_ext.cog_slash(name="loop", description="Loops the currently playing music", options=loop_options)
    async def _loop(self, ctx : SlashContext, mode : bool):
        await ctx.defer()
        if ctx.author.voice is None or not ctx.voice_client:
            await ctx.send("I'm not in a voice channel!")
        else:
            vc: wavelink.Player = ctx.voice_client
            vc.looped = mode

            if mode:
                await ctx.send("Will loop the most recently queued song!")
            else:
                await ctx.send("Will stop looping this song!")

    @cog_ext.cog_slash(name="skip", description="Skips the current song in the queue")
    async def _skip(self, ctx : SlashContext):
        await ctx.defer()
        if ctx.author.voice is None or not ctx.voice_client:
            await ctx.send("I am not in a voice channel!")
        else:
            vc : wavelink.Player = ctx.voice_client
            if not vc.queue.is_empty:
                await ctx.send(f"Skipped {vc.queue.__getitem__(0)}")
                vc.skipped = True #Necessary to override looped parameter
                await vc.stop()
                #Might seem strange, but this fires the on_wavelink_track_end event, so its automatically handled
            else:
                await ctx.send("Queue is empty.")

    @cog_ext.cog_slash(name="queue", description="Displays the current status of the queue (Ignores /loop).")
    async def _queue(self, ctx : SlashContext):
        await ctx.defer()
        if ctx.author.voice is None or not ctx.voice_client:
            await ctx.send("I'm not in a voice channel!")
        else:
            vc : wavelink.Player = ctx.voice_client
            if not vc.queue.is_empty:
                await ctx.send(embed=_generate_queue_embed(vc))
            else:
                await ctx.send("Queue is empty.")


    @cog_ext.cog_slash(name="disconnect", description="Disconnects the bot from voice")
    async def _disconnect(self, ctx : SlashContext):
        if ctx.author.voice is None or not ctx.voice_client:
            await ctx.send("I'm not in a voice channel!")
        else:
            vc : wavelink.Player = ctx.voice_client
            vc.queue.clear()
            await ctx.voice_client.disconnect(force=True)
            await ctx.send("Disconnected from voice!")




def setup(bot):
    bot.add_cog(Music(bot))
