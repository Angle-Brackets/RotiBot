import os
import typing

import discord
import wavelink
import time
from discord.ext import commands
from discord import app_commands
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
    def __init__(self, bot : commands.Bot):
        self.bot = bot
        bot.loop.create_task(self.connect_nodes())

    async def connect_nodes(self):
        await self.bot.wait_until_ready()
        await wavelink.NodePool.create_node(
            bot=self.bot,
            host=os.getenv("MUSIC_IP"),
            port=2333,
            password=os.getenv("MUSIC_PASS")
        )

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node : wavelink.Node):
        print(f"Node: <{node.identifier}> is ready!")

    @commands.Cog.listener()
    #Handles disconnecting
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
        # Handling looping of the song
        if not player.queue.is_empty and not player.skipped and player.looped:
            await player.play(player.queue.__getitem__(0))
        else:
            if not player.queue.is_empty:
                player.queue.get()  # Dequeues current song
                player.skipped = False
                if not player.queue.is_empty:
                    track = player.queue.__getitem__(0)  # DO NOT DEQUEUE THIS UNTIL ITS DONE!!!
                    await player.play(track)
                # Not sure how to send a message to say a new song is playing...

    @app_commands.command(name="join", description="Makes the bot join a valid voice channel")
    # This is not used in _play() as the wavelink context would not be transferred when joining.
    async def _join(self, interaction : discord.Interaction):
        await interaction.response.defer()
        if interaction.user.voice is None:
            await interaction.followup.send("You're not in a voice channel!")
        else:
            if not interaction.guild.voice_client:
                vc : wavelink.Player = await interaction.user.voice.channel.connect(cls=wavelink.Player)

                vc.looped = False # Field to describe is current song is looped - overriden by skipped
                vc.skipped = False # Field to describe if current song was skipped - used to override loop

                await interaction.followup.send("Successfully connected to `{0}`!".format(interaction.user.voice.channel))
            else:
                await interaction.guild.voice_client.move_to(interaction.user.voice.channel)
                await interaction.followup.send(f"Successfully moved to `{interaction.user.voice.channel}`!")

    @app_commands.command(name="play", description="Play audio from a URL or from a search query.")
    @app_commands.describe(video="A valid Youtube URL or Query.")
    async def _play(self, interaction : discord.Interaction, *, video : str):
        await interaction.response.defer()
        try:
            if not interaction.guild.voice_client:
                vc: wavelink.Player = await interaction.user.voice.channel.connect(cls=wavelink.Player)
                vc.looped = False # Initializes custom parameter looped
                vc.skipped = False # Field to describe if current song was skipped - used to override loop
            else:
                vc: wavelink.Player = interaction.guild.voice_client
        except Exception as e:
            await interaction.followup.send("Unable to join channel, please specify a valid channel or join one.")
            return

        track = await wavelink.YouTubeTrack.search(query=video, return_first=True)
        #Will add queue interaction and pause checking soon
        if not vc.queue.is_empty:
            vc.queue.put(track)
            await interaction.followup.send(f"Added {track.title} to the queue!")
        else:
            await vc.play(track)
            vc.queue.put(track)
            await interaction.followup.send("Now playing: " + track.title)

    @app_commands.command(name="pause", description="Pauses the music.")
    async def _pause(self, interaction : discord.Interaction):
        await interaction.response.defer()
        if interaction.user.voice is None or not interaction.guild.voice_client:
            await interaction.followup.send("I'm not in a voice channel!")
        else:
            vc : wavelink.Player = interaction.guild.voice_client

            if not vc.is_paused():
                await vc.pause()
                await interaction.followup.send("Paused!")
            else:
                await interaction.followup.send("Music is currently paused! Use /resume to resume music!")

    @app_commands.command(name="resume", description="Resumes the music.")
    async def _resume(self, interaction : discord.Interaction):
        await interaction.response.defer()
        if interaction.user.voice is None or not interaction.guild.voice_client:
            await interaction.followup.send("I'm not in a voice channel!")
        else:
            vc: wavelink.Player = interaction.guild.voice_client

            if not vc.is_paused():
                await interaction.followup.send("Music is not currently paused! Use /pause to stop the music!")
            else:
                await vc.resume()
                await interaction.followup.send("Resumed!")

    @app_commands.command(name="loop", description="Loops the current track playing.")
    @app_commands.describe(mode="The new looping mode")
    async def _loop(self, interaction : discord.Interaction, mode : typing.Optional[bool]):
        await interaction.response.defer()
        if interaction.user.voice is None or not interaction.guild.voice_client:
            await interaction.followup.send("I'm not in a voice channel!")
        else:
            vc: wavelink.Player = interaction.guild.voice_client
            vc.looped = mode

            if mode:
                await interaction.followup.send("Will loop the most recently queued song!")
            else:
                await interaction.followup.send("Will stop looping this song!")

    @app_commands.command(name="skip", description="Skips the current track playing")
    async def _skip(self, interaction : discord.Interaction):
        await interaction.response.defer()
        if interaction.user.voice is None or not interaction.guild.voice_client:
            await interaction.followup.send("I am not in a voice channel!")
        else:
            vc: wavelink.Player = interaction.guild.voice_client
            if not vc.queue.is_empty:
                await interaction.followup.send(f"Skipped {vc.queue.__getitem__(0)}")
                vc.skipped = True  # Necessary to override looped parameter
                await vc.stop()
                # Might seem strange, but this fires the on_wavelink_track_end event, so its automatically handled
            else:
                await interaction.followup.send("Queue is empty.")

    @app_commands.command(name="queue", description="Displays the queue")
    async def _queue(self, interaction : discord.Interaction):
        await interaction.response.defer()
        if interaction.user.voice is None or not interaction.guild.voice_client:
            await interaction.followup.send("I'm not in a voice channel!")
        else:
            vc : wavelink.Player = interaction.guild.voice_client
            if not vc.queue.is_empty:
                await interaction.followup.send(embed=_generate_queue_embed(vc))
            else:
                await interaction.followup.send("The Queue is empty.")

    @app_commands.command(name="disconnect", description="Disconnects the bot from voice")
    async def _disconnect(self, interaction : discord.Interaction):
        await interaction.response.defer()
        if interaction.user.voice is None or not interaction.guild.voice_client:
            await interaction.followup.send("I'm not in a voice channel!")
        else:
            vc : wavelink.Player = interaction.guild.voice_client
            vc.queue.clear()
            await interaction.guild.voice_client.disconnect(force=True)
            await interaction.followup.send("Disconnected from voice!")

async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
