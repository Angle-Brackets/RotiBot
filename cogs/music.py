import os
import typing

import discord
import wavelink
import time
import random

from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv
from data import db, push_data, FilterParams

"""
Some notes about music functionality:
-I do NOT plan to add Spotify support, this is for several reasons, but mainly it is due to the fact that it would be 
incredibly limited and borderline useless as it is apparently functionally impossible to play music from spotify directly, and
wavelink and all other libs just do a youtube search for a song that has a similar name and play that. 
-I DO plan on adding fun little filters and such that you can add to the music for fun or for trolling.
"""

load_dotenv(".env")
def _is_connected(ctx):
    voice_client = discord.utils.get(ctx.bot.voice_clients, guild=ctx.guild)
    return voice_client and voice_client.is_connected()

"""
This function is used to update the parameters for the music bot at once, as they all must be set in order for
the changes to appropriately take place.
"""
async def _update_voice_parameters(filters : dict, interaction : discord.Interaction, vc : typing.Optional[wavelink.Player]):
    v = db[interaction.guild.id]["settings"]["music"]["volume"] / 100
    s = db[interaction.guild.id]["settings"]["music"]["speed"] / 100
    p = db[interaction.guild.id]["settings"]["music"]["pitch"] / 100

    # Only apply to vc if there is an active song.
    if vc is not None:
        await vc.set_filter(wavelink.filters.Filter(
            volume=v,
            timescale=wavelink.filters.Timescale(speed=s, pitch=p),
            tremolo=filters["Tremolo"],
            vibrato=filters["Vibrato"],
            rotation=filters["Rotation"],
            distortion=filters["Distortion"],
            low_pass=filters["Low_Pass"]
        ), seek=True)

def _generate_queue_embed(vc : wavelink.Player, interaction : discord.Interaction):
    queue = vc.queue
    embed = discord.Embed(title="<a:animated_music:996261334272454736> Music Queue <a:animated_music:996261334272454736>", description="Currently {0}: [{1}]({2}) [{3}/{4}]".format("playing" if not vc.looped else "looping", queue.__getitem__(0), queue[0].info.get("uri"), time.strftime("%H:%M:%S", time.gmtime(vc.position)), time.strftime("%H:%M:%S", time.gmtime(queue.__getitem__(0).duration))), color=0xecc98e)
    embed.set_footer(text="Special thanks to Wavelink & Pythonista for the library used for the music playback!")

    for i in range(len(queue)):
        embed.add_field(name="{0}. {1} - [{2}]".format(i + 1, queue.__getitem__(i), time.strftime("%H:%M:%S", time.gmtime(queue.__getitem__(i).duration))), value=f"Requested by: <@{vc.queue_appenders[i]}>", inline=False)

    #Gets the thumbnail to the current video playing
    embed.set_thumbnail(url=queue.__getitem__(0).thumb)
    vc.queue_embed = embed
    vc.queue_interaction = interaction
    return embed

#Must start Lavalink.jar with java -jar Lavalink.jar and make sure you have the application.yml
"""
Note about the implementation of the queue for this bot, while it might seem strange, I am de-queueing only when 
the song finishes rather than when it starts in order to display all the songs in /queue to avoid confusion.
"""

class Music(commands.Cog):
    def __init__(self, bot : commands.Bot):
        self.bot = bot
        # These are not saved when the bot exits the channel or when shut down.
        self.filters = {
            "Tremolo": wavelink.Tremolo(),
            "Vibrato": None,
            "Rotation": None,
            "Distortion": None,
            "Low_Pass": None,
        }

        self.filters_default = self.filters.copy()

        bot.loop.create_task(self.connect_nodes())

    async def connect_nodes(self):
        await self.bot.wait_until_ready()
        await wavelink.NodePool.create_node(
            bot=self.bot,
            host=os.getenv("MUSIC_IP"),
            port=2333,
            password=os.getenv("MUSIC_PASS"),
        )

    @tasks.loop(seconds=1)
    async def _update_queue_embed_time(self, vc : wavelink.Player):
        try:
            if vc.queue_embed is not None and vc.queue_interaction is not None:
                queue = vc.queue
                vc.queue_embed.description = "Currently {0}: [{1}]({2}) [{3}/{4}]".format("playing" if not vc.looped else "looping", queue.__getitem__(0), queue[0].info.get("uri"), time.strftime("%H:%M:%S", time.gmtime(vc.position)), time.strftime("%H:%M:%S", time.gmtime(queue.__getitem__(0).duration)))
                await vc.queue_interaction.edit_original_response(embed=vc.queue_embed)
            else:
                self._update_queue_embed_time.stop()
        except:
            self._update_queue_embed_time.stop()


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
                player.queue_appenders.pop(0) # Dequeues latest person's name from queue of names
                player.skipped = False
                if not player.queue.is_empty:
                    track = player.queue.__getitem__(0)  # DO NOT DEQUEUE THIS UNTIL ITS DONE!!!
                    await player.play(track)
                    _generate_queue_embed(player, player.queue_interaction)
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
                vc.queue_appenders = list() # Field to list the names of the people that requested a song

                await interaction.followup.send("Successfully connected to `{0}`!".format(interaction.user.voice.channel))
            else:
                await interaction.guild.voice_client.move_to(interaction.user.voice.channel)
                await interaction.followup.send(f"Successfully moved to `{interaction.user.voice.channel}`!")

    @app_commands.command(name="play", description="Play audio from a URL or from a search query.")
    @app_commands.describe(query="A valid Youtube URL or Query.")
    async def _play(self, interaction : discord.Interaction, *, query : str):
        await interaction.response.defer()
        try:
            if not interaction.guild.voice_client:
                vc: wavelink.Player = await interaction.user.voice.channel.connect(cls=wavelink.Player)
                vc.looped = False # Initializes custom parameter looped
                vc.skipped = False # Field to describe if current song was skipped - used to override loop
                vc.queue_appenders = list() # Field to list the names of the people that requested a song
            else:
                vc: wavelink.Player = interaction.guild.voice_client
        except Exception as e:
            await interaction.followup.send("Unable to join channel, please specify a valid channel or join one.")
            return

        try:
            track = await wavelink.YouTubeTrack.search(query=query, return_first=True)

            if not vc.queue.is_empty:
                vc.queue.put(track)
                await interaction.followup.send(f"Added {track.title} to the queue!")
                vc.queue_appenders.append(interaction.user.id)
            else:
                await _update_voice_parameters(self.filters, interaction, vc)

                await vc.play(track)
                vc.queue.put(track)
                vc.queue_appenders.append(interaction.user.id)
                await interaction.followup.send("Now playing: " + track.title)
        except Exception as e:
            await interaction.followup.send("Failed to search for given video. Try with another query!")

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
            await interaction.followup.send("You're not in a voice channel!")
        else:
            vc : wavelink.Player = interaction.guild.voice_client
            if not vc.queue.is_empty:
                view = MusicNav(vc, interaction.guild_id)

                vc.queue_embed = _generate_queue_embed(vc, interaction)
                view.message = await interaction.followup.send(embed=vc.queue_embed, view=view)
                view.message = await interaction.original_response()

                if not self._update_queue_embed_time.is_running():
                    self._update_queue_embed_time.start(vc)

                await view.wait()
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
            vc.queue_appenders.clear()
            vc.queue_embed = None
            await interaction.guild.voice_client.disconnect(force=True)
            await interaction.followup.send("Disconnected from voice!")

    @app_commands.command(name="volume", description="Modify the base volume of Roti (Default is 100).")
    @app_commands.describe(volume="An integer between 0 and 500%, default volume is 100%")
    async def _volume(self, interaction : discord.Interaction, *, volume : typing.Optional[app_commands.Range[int,0,500]]):
        await interaction.response.defer()
        if volume is None:
            await interaction.followup.send("The current volume is: {0}%".format(db[interaction.guild.id]["settings"]["music"]["volume"]),ephemeral=True)
        else:
            db[interaction.guild.id]["settings"]["music"]["volume"] = volume
            push_data(interaction.guild_id, "settings")
            if interaction.user.voice is None or not interaction.guild.voice_client:
                await interaction.followup.send(f"Changed volume to {volume}%")
            else:
                vc : wavelink.Player = interaction.guild.voice_client
                volume /= 100
                await _update_voice_parameters(self.filters, interaction, vc)
                await interaction.followup.send(f"Now playing at {round(volume * 100)}% volume.")
                return

    @app_commands.command(name="speed", description="Modify the playback speed of songs (Default is 100%).")
    @app_commands.describe(speed="An integer between 0 and 200%, default speed is 100%")
    async def _speed(self, interaction : discord.Interaction, *, speed : typing.Optional[app_commands.Range[int, 0, 200]]):
        await interaction.response.defer()
        if speed is None:
            await interaction.followup.send(
                "The current speed is: {0}%".format(db[interaction.guild.id]["settings"]["music"]["speed"]),
                ephemeral=True)
        else:
            db[interaction.guild.id]["settings"]["music"]["speed"] = speed
            push_data(interaction.guild_id, "settings")
            if interaction.user.voice is None or not interaction.guild.voice_client:
                await interaction.followup.send(f"Changed playback speed to {speed}%")
            else:
                vc : wavelink.Player = interaction.guild.voice_client
                speed /= 100
                await _update_voice_parameters(self.filters, interaction, vc)
                await vc.set_filter(wavelink.filters.Filter(timescale=wavelink.filters.Timescale(speed=speed)), seek=True)
                await interaction.followup.send(f"Now playing at {round(speed * 100)}% speed.")
                return

    @app_commands.command(name="pitch", description="Modify the playback pitch of songs (Default is 100%).")
    @app_commands.describe(pitch="An integer between 0 and 200%, default is 100%")
    async def _pitch(self, interaction : discord.Interaction, *, pitch : typing.Optional[app_commands.Range[int, 0, 200]]):
        await interaction.response.defer()
        if pitch is None:
            await interaction.followup.send(
                "The current pitch is: {0}%".format(db[interaction.guild.id]["settings"]["music"]["pitch"]),ephemeral=True)
        else:
            db[interaction.guild.id]["settings"]["music"]["pitch"] = pitch
            push_data(interaction.guild_id, "settings")
            if interaction.user.voice is None or not interaction.guild.voice_client:
                await interaction.followup.send(f"Changed playback pitch to {pitch}%")
            else:
                vc: wavelink.Player = interaction.guild.voice_client
                pitch /= 100
                await _update_voice_parameters(self.filters, interaction, vc)
                await vc.set_filter(wavelink.filters.Filter(timescale=wavelink.filters.Timescale(pitch=pitch)),seek=True)
                await interaction.followup.send(f"Now playing at {round(pitch * 100)}% pitch.")
                return

    # @app_commands.command(name="filter", description="Modify various extraneous aspects of playback.")
    # async def _filter(self, interaction : discord.Interaction, *, filter : typing.Optional[typing.Literal["Tremolo", "Vibrato", "Rotation", "Distortion", "Low Pass"]]):
    #     if filter is None:
    #         vc: wavelink.Player = interaction.guild.voice_client
    #         fields_embed = discord.Embed(title="Current Filter Values", description="To change the values or properties of a filter, either reuse the command with a selected filter, or click a button below.", color=0xecc98e)
    #         fields_embed.add_field(name="Tremolo", value="Frequency: {0} [0.0 - 5.0]\nDepth: {1} [0.0 - 1.0]".format(self.filters["Tremolo"].frequency if self.filters["Tremolo"] is not None else "Disabled", self.filters["Tremolo"].depth if self.filters["Tremolo"] is not None else "Disabled"), inline=False)
    #         fields_embed.add_field(name="Vibrato", value="Frequency: {0} [0.0 - 5.0]\nDepth: {1} [0.0 - 1.0]".format(self.filters["Vibrato"].frequency if self.filters["Vibrato"] is not None else "Disabled", self.filters["Vibrato"].depth if self.filters["Vibrato"] is not None else "Disabled"), inline=False)
    #         fields_embed.add_field(name="Rotation", value="Rotation Speed: {0} [-1.0 - 1.0]".format(self.filters["Rotation"].speed if self.filters["Rotation"] is not None else "Disabled"), inline=False)
    #
    #         fields_embed.add_field(name="Distortion", value="Sine Amplitude: {0} [-2.0 - 2.0] | Sine Offset: {1} [-2π - 2π]\nCosine Amplitude: {2} [-2.0 - 2.0] | Cosine Offset: {3} [-2π - 2π]\nTangent Amplitude: {4} [-2.0 - 2.0] | Tangent Offset: {5} [-2π - 2π]".format(
    #             self.filters["Distortion"].sin_scale if self.filters["Distortion"] is not None else "Disabled",
    #             self.filters["Distortion"].sin_offset if self.filters["Distortion"] is not None else "Disabled",
    #             self.filters["Distortion"].cos_scale if self.filters["Distortion"] is not None else "Disabled",
    #             self.filters["Distortion"].cos_offset if self.filters["Distortion"] is not None else "Disabled",
    #             self.filters["Distortion"].tan_scale if self.filters["Distortion"] is not None else "Disabled",
    #             self.filters["Distortion"].tan_offset if self.filters["Distortion"] is not None else "Disabled"
    #         ), inline=False)
    #
    #         fields_embed.add_field(name="Low Pass", value="Smoothing: {0} [1 - 20]".format(self.filters["Low_Pass"].smoothing if self.filters["Low_Pass"] is not None else "Disabled"), inline=False)
    #
    #         view = FilterNav(self.filters, vc)
    #         view.message = await interaction.response.send_message(embed=fields_embed, view=view, ephemeral=True)
    #         view.message = await interaction.original_response()
    #
    #         await view.wait()
    #     else:
    #         pass



"""
Purpose of this navigation component is to list the current state of all the filters for easy viewing.
"""
class FilterNav(discord.ui.View):
    def __init__(self, filters, vc):
        super().__init__()
        self.timeout = 60
        self.filters = filters
        self.vc = vc

    @discord.ui.button(label="Tremolo", style=discord.ButtonStyle.primary)
    async def _tremolo(self, interaction : discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TremoloModal(self.filters, self.vc))

    @discord.ui.button(label="Vibrato", style=discord.ButtonStyle.primary)
    async def _vibrato(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="Rotation", style=discord.ButtonStyle.primary)
    async def _rotation(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="Low Pass", style=discord.ButtonStyle.primary)
    async def _low_pass(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    # More complex, needs to open up more buttons, or maybe a dropdown.
    @discord.ui.button(label="Distortion", style=discord.ButtonStyle.primary)
    async def _distortion(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger)
    async def _close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.message.delete()
        self.stop()

    async def on_timeout(self) -> None:
        await self.message.delete()
        self.stop()

"""
Base class for Modals regarding filters
All defaults are automatically baked into the text input constructors for subclasses.
"""
class FilterModal(discord.ui.Modal, title="Placeholder"):
    def __init__(self, filters, vc):
        super().__init__()
        self.filters = filters
        self.vc = vc

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        if not isinstance(error, ValueError):
            # Default error, should not occur but have it in case.
            await interaction.response.send_message('Oops! Something went wrong.', ephemeral=True)
        else:
            # Error message is based on what the child class propagates.
            await interaction.response.send_message(error, ephemeral=True)

class TremoloModal(FilterModal, title="Edit Tremolo Values"):
    def __init__(self, filters, vc):
        super().__init__(filters, vc)

    tremolo_freq = discord.ui.TextInput(
        label="Input a frequency value between 0.0 and 5.0",
        placeholder="Default value is 2.0",
        default="2.0",
        max_length=3,
        required=True
    )

    tremolo_depth = discord.ui.TextInput(
        label="Input a depth value between [0.0 - 1.0]",
        placeholder="Default value is 0.5",
        default="0.5",
        max_length=3,
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not 0 <= float(self.tremolo_freq.value) <= 5:
            raise ValueError("Invalid frequency specified, make sure it's between 0 and 5!")
        if not 0 <= float(self.tremolo_depth.value) <= 1:
            raise ValueError("Invalid depth specified, make sure it's between 0 and 1!")

        self.filters["Tremolo"] = wavelink.Tremolo(frequency=float(self.tremolo_freq.value), depth=float(self.tremolo_depth.value))

        await _update_voice_parameters(self.filters, interaction, self.vc)
        await interaction.response.send_message("Successfully modified filter.", ephemeral=True)

class MusicNav(discord.ui.View):
    global guild_id
    def __init__(self, player : wavelink.Player, g_id):
        super().__init__()
        global guild_id
        self.timeout = 60
        self.player = player
        self.guild_id = g_id
        self._volume_label.label = "{0}%".format(db[self.guild_id]["settings"]["music"]["volume"])
        self._speed_label.label = "{0}%".format(db[self.guild_id]["settings"]["music"]["speed"])
        self._pitch_label.label = "{0}%".format(db[self.guild_id]["settings"]["music"]["pitch"])

        self._volume_label.emoji = "🔇" if db[self.guild_id]["settings"]["music"]["volume"] == 0 else discord.PartialEmoji(name="kirbin", id=996961280919355422, animated=True)
        self._speed_label.emoji = discord.PartialEmoji(name="sonic_waiting", id=996961282639024171, animated=True) if db[self.guild_id]["settings"]["music"]["speed"] < 100 else discord.PartialEmoji(name="sonic_running", id=996961281837908008, animated=True)

    @discord.ui.button(emoji="<:playbtn:994759843749580861>", style=discord.ButtonStyle.secondary)
    async def _unpause(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.voice is not None or interaction.guild.voice_client:
            await self.player.resume()
            if self.player.is_paused():
                await interaction.response.send_message("Unpaused!", ephemeral=True)

    @discord.ui.button(emoji="<:pausebtn:994763090413498388>", style=discord.ButtonStyle.secondary)
    async def _pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.voice is not None or interaction.guild.voice_client:
            await self.player.pause()
            if self.player.is_playing():
                await interaction.response.send_message("Paused!", ephemeral=True)

    @discord.ui.button(emoji="<:loopicon:994754841710702733>", style=discord.ButtonStyle.secondary)
    async def _loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.voice is not None or interaction.guild.voice_client:
            self.player.looped = not self.player.looped
            if self.player.looped:
                await interaction.response.send_message("Will continue to loop the current song!", ephemeral=True)
            else:
                await interaction.response.send_message("Will stop looping the current song!", ephemeral=True)

    @discord.ui.button(emoji="<:skipbtn:994763472522977290>", style=discord.ButtonStyle.secondary)
    async def _skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.voice is not None or interaction.guild.voice_client:
            if not self.player.queue.is_empty:
                await interaction.response.send_message(f"Skipped {self.player.queue.__getitem__(0)}")
                self.player.skipped = True  # Necessary to override looped parameter
                await self.player.stop()
                await self.message.edit(embed=self.player.queue_embed)

    @discord.ui.button(emoji="<:disconnectbtn:996156534927130735>", style=discord.ButtonStyle.secondary)
    async def _disconnect(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.voice is not None or interaction.guild.voice_client:
            self.player.queue.clear()
            await interaction.guild.voice_client.disconnect(force=True)
            await interaction.response.send_message("Disconnected from voice!")
            await self.message.delete()
            self.stop()

    @discord.ui.button(label="Undefined Volume", style=discord.ButtonStyle.primary)
    async def _volume_label(self, interaction : discord.Interaction, button : discord.ui.Button):
        # It's just a label.
        await interaction.response.send_message("It's just a label..." if random.random() < 0.95 else "https://tinyurl.com/c9wcjhsc", ephemeral=True)
        pass

    @discord.ui.button(label="Undefined Speed", style=discord.ButtonStyle.primary)
    async def _speed_label(self, interaction: discord.Interaction, button: discord.ui.Button):
        # It's just a label.
        await interaction.response.send_message("It's just a label..." if random.random() < 0.95 else "https://tinyurl.com/c9wcjhsc", ephemeral=True)
        pass

    @discord.ui.button(label="Undefined Pitch", emoji="<:treble:996969244963131473>", style=discord.ButtonStyle.primary)
    async def _pitch_label(self, interaction: discord.Interaction, button: discord.ui.Button):
        # It's just a label.
        await interaction.response.send_message("It's just a label..." if random.random() < 0.95 else "https://tinyurl.com/c9wcjhsc", ephemeral=True)
        pass

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger)
    async def _close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.message.delete()
        self.stop()

    async def on_timeout(self) -> None:
        await self.message.delete()
        self.player.queue_embed = None
        self.stop()

async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))




