import os
import typing

import discord
import wavelink
import time
import random
import logging

from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv
from database.data import RotiDatabase
from time import strftime, gmtime
from utils.RotiUtilities import cog_command

"""
Some notes about music functionality:
-I do NOT plan to add Spotify support, this is for several reasons, but mainly it is due to the fact that it would be 
incredibly limited and borderline useless as it is apparently functionally impossible to play music from spotify directly, and
wavelink and all other libs just do a youtube search for a song that has a similar name and play that. 
-I DO plan on adding fun little filters and such that you can add to the music for fun or for trolling.
"""

load_dotenv(".env")

"""
This function is used to update the parameters for the music bot at once, as they all must be set in order for
the changes to appropriately take place.
"""
async def _update_voice_parameters(db : RotiDatabase, filters : wavelink.Filters, interaction : discord.Interaction, vc : typing.Optional[wavelink.Player]):
    v = db[interaction.guild_id, "settings", "music", "volume"].unwrap() / 100
    s = db[interaction.guild_id, "settings", "music", "speed"].unwrap() / 100
    p = db[interaction.guild_id, "settings", "music", "pitch"].unwrap() / 100

    filters.volume = v
    filters.timescale.set(speed=s, pitch=p, rate=1.0)

    # Only apply to vc if there is an active song.
    if vc is not None:
        await vc.set_filters(filters, seek=True)

def _generate_queue_embed(vc : wavelink.Player, interaction : discord.Interaction):
    queue = vc.queue.copy()
    if vc.playing:
        queue.put_at(0, vc.current)
    
    embed = discord.Embed(
        title="<a:animated_music:996261334272454736> Music Queue <a:animated_music:996261334272454736>",
        description=f"Currently {"playing" if not vc.looped else "looping"}: [{queue[0].title}]({queue[0].uri}) [{time.strftime("%H:%M:%S", time.gmtime(vc.position))}/{time.strftime("%H:%M:%S", time.gmtime(queue[0].length))}]", 
        color=0xecc98e
    )
    
    embed.set_footer(text="Special thanks to Wavelink & Pythonista for the library used for the music playback!")

    for i in range(len(queue)):
        embed.add_field(name=f"{i+1}. {queue[i]} - [{time.strftime("%H:%M:%S", time.gmtime(queue[i].length // 1000))}]", value=f"Requested by: <@{vc.queue_appenders[i]}>", inline=False)

    #Gets the thumbnail to the current video playing
    embed.set_thumbnail(url=vc.current.artwork)
    vc.queue_embed = embed
    vc.queue_interaction = interaction
    return embed

#Must start Lavalink.jar with java -jar Lavalink.jar and make sure you have the application.yml
"""
Note about the implementation of the queue for this bot, while it might seem strange, I am de-queueing only when 
the song finishes rather than when it starts in order to display all the songs in /queue to avoid confusion.
"""

@cog_command
class Music(commands.Cog):
    def __init__(self, bot : commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        # These are not saved when the bot exits the channel or when shut down.
        self.filters = wavelink.Filters()
        self.db = RotiDatabase()

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload) -> None:
        self.logger.info("Wavelink Node connected: %s | Resumed %s", payload.node, payload.resumed)

    @tasks.loop(seconds=1)
    async def _update_queue_embed_time(self, vc : wavelink.Player):
        try:
            if vc and vc.queue_embed and vc.queue_interaction:
                position_seconds = vc.position // 1000  # Convert milliseconds to seconds
                duration_seconds = vc.current.length // 1000  # Convert milliseconds to seconds if needed

                vc.queue_embed.description = "Currently {0}: [{1}]({2}) [{3}/{4}]".format(
                    "playing" if not vc.looped else "looping",  # Status
                    vc.current.title,  # Track title
                    vc.current.uri,  # Track URI
                    strftime("%H:%M:%S", gmtime(position_seconds)),  # Current position
                    strftime("%H:%M:%S", gmtime(duration_seconds))  # Total duration
                )
                
                await vc.queue_interaction.edit_original_response(embed=vc.queue_embed)
            else:
                self._update_queue_embed_time.stop()
        except Exception as e:
            self._update_queue_embed_time.stop()

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
    async def on_wavelink_track_start(self, payload : wavelink.TrackStartEventPayload):
        vc : wavelink.Player | None = payload.player
        if not vc:
            await vc.home.send("An error has occured, try again later.")
            return
        
        original : wavelink.Playable | None = payload.original # unmodified object with extra data associated.
        track : wavelink.Playable = payload.track

        await vc.home.send(f"Now playing **{track.title}**!")

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload : wavelink.TrackEndEventPayload):
        vc : wavelink.Player | None = payload.player
        if not vc:
            return

        original : wavelink.Playable | None = payload.original # unmodified object with extra data associated.
        track : wavelink.Playable = payload.track
        reason :str = payload.reason

        if not vc.skipped and vc.looped:
            await vc.play(track)
        else:
            vc.queue_appenders.pop(0)
            vc.skipped = False
            if not vc.queue.is_empty:
                new_track = vc.queue.get()
                await vc.play(new_track)

                vc.queue_embed = _generate_queue_embed(vc, vc.queue_interaction)
                await vc.queue_interaction.edit_original_response(embed=vc.queue_embed)
    
    # This is not used in _play() as the wavelink context would not be transferred when joining.    
    @app_commands.command(name="join", description="Makes the bot join a valid voice channel")
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

                await interaction.followup.send(f"Successfully connected to `{interaction.user.voice.channel}`!")
            else:
                await interaction.guild.voice_client.move_to(interaction.user.voice.channel)
                await interaction.followup.send(f"Successfully moved to `{interaction.user.voice.channel}`!")

    @app_commands.command(name="play", description="Play audio from a URL or from a search query.")
    @app_commands.describe(query="A valid Youtube URL or Query.")
    async def _play(self, interaction : discord.Interaction, *, query : str):
        await interaction.response.defer()

        if not interaction.guild:
            return

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
        
        # Lock the player to this channel...
        if not hasattr(vc, "home"):
            vc.home = interaction.channel
        elif vc.home != interaction.channel:
            await interaction.followup.send(f"You can only play songs in {vc.home.mention}, as the player has already started there.", ephemeral=True)
            return

        tracks : wavelink.Search = await wavelink.Playable.search(query)

        if not tracks:
            await interaction.followup.send("Failed to search for given video. Try with another query!", ephemeral=True)
            return
        
        if isinstance(tracks, wavelink.Playlist):
            added : int = await vc.queue.put_wait(tracks)
            await interaction.followup.send(f"Added the playlist **{tracks.name}** to the queue with {added} songs!")
            vc.queue_appenders.append(interaction.user.id)
        else:
            track = wavelink.Playable = tracks[0]
            await vc.queue.put_wait(track)
            await interaction.followup.send(f"Added {track.title} to the queue!") 
            vc.queue_appenders.append(interaction.user.id)
        
        if not vc.playing:
            await _update_voice_parameters(self.db, self.filters, interaction, vc)
            await vc.play(vc.queue.get())
            

    @app_commands.command(name="pause", description="Pauses the music.")
    async def _pause(self, interaction : discord.Interaction):
        await interaction.response.defer()

        if interaction.user.voice is None or not interaction.guild.voice_client:
            await interaction.followup.send("I'm not in a voice channel!")
        else:
            vc : wavelink.Player = interaction.guild.voice_client

            if not vc.paused:
                await vc.pause(True)
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

            if not vc.paused:
                await interaction.followup.send("Music is not currently paused! Use /pause to stop the music!")
            else:
                await vc.pause(False)
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
        if not interaction.user.voice or not interaction.guild.voice_client:
            await interaction.followup.send("I am not in a voice channel!")
        else:
            vc: wavelink.Player = interaction.guild.voice_client
            if not vc.queue.is_empty or vc.playing:
                await interaction.followup.send(f"Skipped {vc.current.title}")
                vc.skipped = True  # Necessary to override looped parameter
                await vc.skip(force=True) # Fires the end_track listener
            else:
                await interaction.followup.send("Queue is empty.")

    @app_commands.command(name="queue", description="Displays the queue")
    async def _queue(self, interaction : discord.Interaction):
        await interaction.response.defer()
        if interaction.user.voice is None or not interaction.guild.voice_client:
            await interaction.followup.send("You're not in a voice channel!")
        else:
            vc : wavelink.Player = interaction.guild.voice_client
            if not vc.queue.is_empty or vc.playing:
                view = MusicNav(self.db, vc, interaction.guild_id)

                vc.queue_embed = _generate_queue_embed(vc, interaction)
                view.message = await interaction.followup.send(embed=vc.queue_embed, view=view)
                view.message = await interaction.original_response()

                if not self._update_queue_embed_time.is_running():
                    vc.queue_interaction = interaction
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
        if not volume:
            await interaction.followup.send(f"The current volume is: {self.db[interaction.guild_id, "settings", "music", "volume"].unwrap()}%",ephemeral=True)
        else:
            self.db[interaction.guild_id, "settings", "music", "volume"] = volume
            if interaction.user.voice is None or not interaction.guild.voice_client:
                await interaction.followup.send(f"Changed volume to {volume}%")
            else:
                vc : wavelink.Player = interaction.guild.voice_client
                volume /= 100
                await _update_voice_parameters(self.db, self.filters, interaction, vc)
                await interaction.followup.send(f"Now playing at {round(volume * 100)}% volume.")
                return

    @app_commands.command(name="speed", description="Modify the playback speed of songs (Default is 100%).")
    @app_commands.describe(speed="An integer between 0 and 200%, default speed is 100%")
    async def _speed(self, interaction : discord.Interaction, *, speed : typing.Optional[app_commands.Range[int, 0, 200]]):
        await interaction.response.defer()
        if speed is None:
            await interaction.followup.send(
                f"The current speed is: {self.db[interaction.guild_id, "settings", "music", "speed"].unwrap()}%",
                ephemeral=True)
        else:
            self.db[interaction.guild_id, "settings", "music", "speed"] = speed
            if interaction.user.voice is None or not interaction.guild.voice_client:
                await interaction.followup.send(f"Changed playback speed to {speed}%")
            else:
                vc : wavelink.Player = interaction.guild.voice_client
                speed /= 100
                await _update_voice_parameters(self.db, self.filters, interaction, vc)
                await interaction.followup.send(f"Now playing at {round(speed * 100)}% speed.")
                return

    @app_commands.command(name="pitch", description="Modify the playback pitch of songs (Default is 100%).")
    @app_commands.describe(pitch="An integer between 0 and 200%, default is 100%")
    async def _pitch(self, interaction : discord.Interaction, *, pitch : typing.Optional[app_commands.Range[int, 0, 200]]):
        await interaction.response.defer()
        if pitch is None:
            await interaction.followup.send(
                f"The current pitch is: {self.db[interaction.guild_id, "settings", "music", "pitch"].unwrap()}%", ephemeral=True)
        else:
            self.db[interaction.guild_id, "settings", "music", "pitch"] = pitch
            if interaction.user.voice is None or not interaction.guild.voice_client:
                await interaction.followup.send(f"Changed playback pitch to {pitch}%")
            else:
                vc: wavelink.Player = interaction.guild.voice_client
                pitch /= 100
                await _update_voice_parameters(self.db, self.filters, interaction, vc)
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

        await _update_voice_parameters(self.db, self.filters, interaction, self.vc)
        await interaction.response.send_message("Successfully modified filter.", ephemeral=True)

class MusicNav(discord.ui.View):
    global guild_id
    def __init__(self, db : RotiDatabase, player : wavelink.Player, g_id : id):
        super().__init__()
        global guild_id
        self.timeout = 60
        self.db = db
        self.player = player
        self.guild_id = g_id
        self._volume_label.label = f"{self.db[self.guild_id, "settings", "music", "volume"].unwrap()}%"
        self._speed_label.label = f"{self.db[self.guild_id, "settings", "music", "speed"].unwrap()}%"
        self._pitch_label.label = f"{self.db[self.guild_id, "settings", "music", "pitch"].unwrap()}%"

        self._volume_label.emoji = "🔇" if self.db[self.guild_id, "settings", "music", "volume"].unwrap() == 0 else discord.PartialEmoji(name="kirbin", id=996961280919355422, animated=True)
        self._speed_label.emoji = discord.PartialEmoji(name="sonic_waiting", id=996961282639024171, animated=True) if self.db[self.guild_id, "settings", "music", "speed"].unwrap() < 100 else discord.PartialEmoji(name="sonic_running", id=996961281837908008, animated=True)

    @discord.ui.button(emoji="<:playbtn:994759843749580861>", style=discord.ButtonStyle.secondary)
    async def _unpause(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.voice is not None or interaction.guild.voice_client:
            if not self.player.paused:
                await interaction.response.send_message("Song is already unpaused!", ephemeral=True)
                return

            await self.player.pause(False)
            await interaction.response.send_message("Unpaused!", ephemeral=True)

    @discord.ui.button(emoji="<:pausebtn:994763090413498388>", style=discord.ButtonStyle.secondary)
    async def _pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.voice is not None or interaction.guild.voice_client:
            if self.player.paused:
                await interaction.response.send_message("Song already unpaused!", ephemeral=True)
                return

            await self.player.pause(True)
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
            if not self.player.queue.is_empty or self.player.playing:
                await interaction.response.send_message(f"Skipped {self.player.current}")
                self.player.skipped = True  # Necessary to override looped parameter
                await self.player.skip(force=True)
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
