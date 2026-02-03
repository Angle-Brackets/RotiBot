import typing
import os
import discord
import lavalink
import random
import logging

from discord.ext import commands, tasks
from discord import app_commands
from database.data import RotiDatabase, RotiState, MusicSettings
from time import strftime, gmtime
from utils.RotiUtilities import cog_command
from cogs.statistics.statistics_helpers import statistic

# --- Voice Client Handshake ---
class LavalinkVoiceClient(discord.VoiceProtocol):
    def __init__(self, client: discord.Client, channel: discord.abc.Connectable):
        self.client = client
        self.channel = channel
        self.guild_id = channel.guild.id
        self.lavalink = self.client.lavalink

    async def on_voice_server_update(self, data):
        await self.lavalink.voice_update_handler({'t': 'VOICE_SERVER_UPDATE', 'd': data})

    async def on_voice_state_update(self, data):
        if not data['channel_id']:
            await self.disconnect()
            return
        await self.lavalink.voice_update_handler({'t': 'VOICE_STATE_UPDATE', 'd': data})

    async def connect(self, *, timeout: float, reconnect: bool, self_deaf: bool = False, self_mute: bool = False) -> None:
        self.lavalink.player_manager.create(guild_id=self.channel.guild.id)
        await self.channel.guild.change_voice_state(channel=self.channel, self_mute=self_mute, self_deaf=self_deaf)

    async def disconnect(self, *, force: bool = False) -> None:
        player = self.lavalink.player_manager.get(self.guild_id)
        if not force and not player.is_connected:
            return
        await self.client.get_guild(self.guild_id).change_voice_state(channel=None)
        player.channel_id = None
        self.cleanup()

def _generate_queue_embed(player: lavalink.DefaultPlayer, interaction: discord.Interaction):
    current = player.current
    if not current:
        return discord.Embed(description="Nothing is playing right now.", color=0xecc98e)

    # 1. Remaining time on current track
    current_remaining = current.duration - player.position
    
    # 2. Total duration of all songs in the queue
    queue_duration = sum(t.duration for t in player.queue)
    
    # 3. Total time until music stops
    total_remaining_ms = current_remaining + queue_duration
    total_remaining_str = strftime('%H:%M:%S', gmtime(total_remaining_ms // 1000))

    pos = strftime('%H:%M:%S', gmtime(player.position // 1000))
    dur = strftime('%H:%M:%S', gmtime(current.duration // 1000))
    
    loop_status = "playing" if player.loop == 0 else "looping"

    embed = discord.Embed(
        title="<a:animated_music:996261334272454736> Music Queue <a:animated_music:996261334272454736>",
        description=f"Currently {loop_status}: [{current.title}]({current.uri}) [{pos}/{dur}]", 
        color=0xecc98e
    )

    # --- Queue List Display ---
    QUEUE_LENGTH = 10
    if player.queue:
        for i, track in enumerate(player.queue[:QUEUE_LENGTH], start=1):
            track_dur = strftime('%H:%M:%S', gmtime(track.duration // 1000))
            embed.add_field(
                name=f"{i}. {track.title} - [{track_dur}]", 
                value=f"Requested by: <@{track.requester}>", 
                inline=False
            )
        
        # Check if there are hidden songs
        remaining_count = len(player.queue) - QUEUE_LENGTH
        if remaining_count > 0:
            embed.add_field(
                name=f"... and {remaining_count} more songs.",
                value=f"**Total Estimated Time:** {total_remaining_str}",
                inline=False
            )
        else:
            embed.set_footer(text=f"Total Estimated Time: {total_remaining_str}")
    else:
        embed.set_footer(text=f"Queue empty | Ends in: {strftime('%H:%M:%S', gmtime(current_remaining // 1000))}")

    if current and hasattr(current, 'artwork_url'):
        embed.set_thumbnail(url=current.artwork_url)
    
    player.store('queue_embed', embed)
    player.store('queue_interaction', interaction)
    return embed

@cog_command
class Music(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.db = RotiDatabase()
        self.state = RotiState()
        self.MAX_TRACKS = 100
        
        if not hasattr(bot, 'lavalink'):
            bot.lavalink = lavalink.Client(bot.user.id)
            
        self.lavalink = bot.lavalink
        if not self.lavalink._event_hooks:
            self.lavalink.add_event_hooks(self)
        
    async def cog_load(self):
        host = self.state.credentials.music_ip
        port = int(os.getenv('LAVALINK_PORT', '2333'))
        password = self.state.credentials.music_pass
        
        if not self.lavalink.node_manager.nodes:
            self.lavalink.add_node(host, port, password, 'us', 'default-node')

    @lavalink.listener(lavalink.events.TrackStartEvent)
    async def track_start(self, event: lavalink.events.TrackStartEvent):
        player = event.player
        guild = self.bot.get_guild(player.guild_id)
        
        # 1. Standard "Now Playing" message
        cid = player.fetch('channel')
        if cid:
            channel = self.bot.get_channel(cid)
            if channel:
                await channel.send(f"Now playing **{event.track.title}**!", delete_after=20)

        # 2. Voice Status Feature
        if guild.me.guild_permissions.manage_channels:
            voice_channel = guild.get_channel(int(player.channel_id))
            if voice_channel:
                status = f"Playing: {event.track.title}"
                if len(status) > 32:
                    status = status[:29] + "..."
                
                try:
                    await voice_channel.edit(status=status)
                except Exception as e:
                    self.logger.error(f"Failed to set voice status: {e}")

    @lavalink.listener(lavalink.events.TrackEndEvent)
    async def track_end(self, event: lavalink.events.TrackEndEvent):
        player = event.player
        interaction = player.fetch('queue_interaction')
        if interaction:
            try:
                embed = _generate_queue_embed(player, interaction)
                await interaction.edit_original_response(embed=embed)
            except:
                pass
                
        if not player.queue and not player.is_playing:
            guild = self.bot.get_guild(player.guild_id)
            voice_channel = guild.get_channel(int(player.channel_id))
            if voice_channel and guild.me.guild_permissions.manage_channels:
                await voice_channel.edit(status=None)
    
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # We only care if someone leaves a channel
        if before.channel is not None and after.channel is None:
            # Check if the channel they left is the one the bot is in
            player = self.lavalink.player_manager.get(before.channel.guild.id)
            if not player or not player.is_connected:
                return

            if before.channel.id == int(player.channel_id):
                # Check if there are any non-bot members left
                if not any(not m.bot for m in before.channel.members):
                    # Reset the Voice Status (the feature we just added)
                    if before.channel.guild.me.guild_permissions.manage_channels:
                        try:
                            await before.channel.edit(status=None)
                        except: pass
                    
                    # Clear the player and disconnect
                    await player.stop()
                    player.queue.clear()
                    player.delete('queue_interaction')
                    player.delete('queue_embed')
                    await self.bot.get_guild(before.channel.guild.id).change_voice_state(channel=None)
                    
                    # Send a notification to the last text channel used
                    cid = player.fetch('channel')
                    if cid:
                        channel = self.bot.get_channel(cid)
                        if channel:
                            await channel.send("Leaving voice channel as it is empty. ✌️", delete_after=10)

    @tasks.loop(seconds=1)
    async def _update_queue_embed_time(self, player: lavalink.DefaultPlayer):
        try:
            interaction = player.fetch('queue_interaction')
            embed = player.fetch('queue_embed')
            if player and embed and interaction and player.is_playing:
                pos = strftime("%H:%M:%S", gmtime(player.position // 1000))
                dur = strftime("%H:%M:%S", gmtime(player.current.duration // 1000))

                status = "playing" if player.loop == 0 else "looping"
                embed.description = f"Currently {status}: [{player.current.title}]({player.current.uri}) [{pos}/{dur}]"
                
                await interaction.edit_original_response(embed=embed)
            else:
                self._update_queue_embed_time.stop()
        except:
            self._update_queue_embed_time.stop()
    
    @app_commands.command(name="join", description="Join your current voice channel.")
    async def _join(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not interaction.user.voice:
            return await interaction.followup.send("You are not in a voice channel!")
        
        player = self.lavalink.player_manager.create(interaction.guild.id)
        if player.is_connected:
            return await interaction.followup.send("I'm already in a voice channel!")
            
        player.store('channel', interaction.channel.id)
        await interaction.user.voice.channel.connect(cls=LavalinkVoiceClient)
        await interaction.followup.send(f"Joined **{interaction.user.voice.channel.name}**!")
    
    @statistic(display_name="Music Queries", category="Music")
    async def _get_tracks(self, player : lavalink.BasePlayer, query : str) -> lavalink.LoadResult:
        return await player.node.get_tracks(query if query.startswith('http') else f'ytsearch:{query}')

    @app_commands.command(name="play", description="Play audio from a URL or query.")
    async def _play(self, interaction: discord.Interaction, *, query: str):
        await interaction.response.defer()
        
        if not interaction.user.voice:
            return await interaction.followup.send("You need to join a voice channel first!")

        player = self.lavalink.player_manager.create(interaction.guild.id)
        
        if not player.is_connected:
            player.store('channel', interaction.channel.id)
            await interaction.user.voice.channel.connect(cls=LavalinkVoiceClient)

        results = await self._get_tracks(player, query)
        
        if not results or not results.tracks:
            return await interaction.followup.send("No results found.")
        if len(player.queue) >= self.MAX_TRACKS:
            return await interaction.followup.send(f"The queue is currently full at {self.MAX_TRACKS} songs!")

        if results.load_type == lavalink.LoadType.PLAYLIST:
            tracks_to_add = results.tracks

            if len(tracks_to_add) + len(player.queue) <= self.MAX_TRACKS:
                for track in tracks_to_add:
                    player.add(requester=interaction.user.id, track=track)
                
                await interaction.followup.send(
                    f"Added playlist **{results.playlist_info.name}** "
                    f"({len(tracks_to_add)} tracks)."
                )
            else:
                remaining_space = self.MAX_TRACKS - len(player.queue)

                for track in tracks_to_add[:remaining_space]:
                    player.add(requester=interaction.user.id, track=track)

                await interaction.followup.send(
                    f"Playlist **{results.playlist_info.name}** is too large! "
                    f"Added the first **{remaining_space}** tracks."
                )
        else:
            track = results.tracks[0]
            player.add(requester=interaction.user.id, track=track)
            await interaction.followup.send(f"Added **{track.title}** to queue!")

        if not player.is_playing:
            row = await self.db.select(MusicSettings, server_id=interaction.guild_id)
            await player.set_volume(row.volume)
            await player.play()
    
    @app_commands.command(name="skip", description="Skips the current track playing")
    async def _skip(self, interaction: discord.Interaction):
        await interaction.response.defer()
        player = self.lavalink.player_manager.get(interaction.guild.id)

        if not player or not player.is_connected:
            return await interaction.followup.send("I'm not in a voice channel!")
        
        if not player.current:
            return await interaction.followup.send("Nothing is playing.")

        # If this is the last song in the queue, clear status.
        if not player.queue:
            guild = interaction.guild
            voice_channel = guild.get_channel(int(player.channel_id))
            if voice_channel and guild.me.guild_permissions.manage_channels:
                await voice_channel.edit(status=None)

        await interaction.followup.send(f"Skipped {player.current.title}")
        await player.skip()
            
    
    @app_commands.command(name="disconnect", description="Disconnects the bot.")
    async def _disconnect(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        player = self.lavalink.player_manager.get(interaction.guild.id)

        if not player or not player.is_connected:
            return await interaction.followup.send("I'm not connected!")

        if player:
            if interaction.guild.me.guild_permissions.manage_channels:
                vc = interaction.guild.get_channel(int(player.channel_id))
                if vc:
                    await vc.edit(status=None)

        await player.stop()
        player.queue.clear()
        player.delete('queue_interaction')
        player.delete('queue_embed')
        await self.bot.get_guild(interaction.guild.id).change_voice_state(channel=None)
        await interaction.followup.send("Disconnected!")
            
    @app_commands.command(name="queue", description="Displays the queue")
    async def _queue(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        player = self.lavalink.player_manager.get(interaction.guild.id)
        
        if player and (player.queue or player.is_playing):
            row = await self.db.select(MusicSettings, server_id=interaction.guild_id)
            view = MusicNav(player, row)
            embed = _generate_queue_embed(player, interaction)
            
            # Send and store message in view for auto-deletion
            message = await interaction.followup.send(embed=embed, view=view)
            view.message = message 

            if not self._update_queue_embed_time.is_running():
                self._update_queue_embed_time.start(player)
        else:
            await interaction.followup.send("The Queue is empty.")
    
    @app_commands.command(name="loop", description="Cycle through loop modes: Off, Single, or Queue.")
    async def _loop(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        player = self.lavalink.player_manager.get(interaction.guild_id)
        
        if not player or not player.is_playing:
            return await interaction.followup.send("Nothing is playing right now!")

        # Lavalink.py loop modes: 0 = Off, 1 = Single Track, 2 = Queue
        new_loop = (player.loop + 1) % 3
        player.set_loop(new_loop)
        
        modes = {
            0: "Looping disabled. ➡️",
            1: "Looping the **current track**. 🔂",
            2: "Looping the **entire queue**. 🔁"
        }
        
        await interaction.followup.send(modes[new_loop])
    
    @app_commands.command(name="speed", description="Modify playback speed.")
    async def _speed(self, interaction: discord.Interaction, speed: typing.Optional[app_commands.Range[int, 0, 200]]):
        await interaction.response.defer(ephemeral=True)
        if speed is None:
            row = self.db.select(MusicSettings, server_id=interaction.guild_id)
            return await interaction.followup.send(f"Current speed: {row.speed}%")
        self.db.update(MusicSettings, server_id=interaction.guild_id, speed=speed)
        player = self.lavalink.player_manager.get(interaction.guild_id)
        if player: await player.set_filter(lavalink.filters.Timescale(speed=speed/100))
        await interaction.followup.send(f"Speed set to {speed}%")

    @app_commands.command(name="pitch", description="Modify playback pitch.")
    async def _pitch(self, interaction: discord.Interaction, pitch: typing.Optional[app_commands.Range[int, 0, 200]]):
        await interaction.response.defer(ephemeral=True)
        if pitch is None:
            row = await self.db.select(MusicSettings, server_id=interaction.guild_id)
            return await interaction.followup.send(f"Current pitch is {row.pitch}%")

        self.db.update(MusicSettings, server_id=interaction.guild_id, pitch=pitch)
        player = self.lavalink.player_manager.get(interaction.guild_id)
        if player:
            await player.set_filter(lavalink.filters.Timescale(pitch=pitch/100))
        await interaction.followup.send(f"Pitch set to {pitch}%")

    @app_commands.command(name="volume", description="Modify the base volume.")
    async def _volume(self, interaction: discord.Interaction, volume: typing.Optional[app_commands.Range[int, 0, 500]]):
        await interaction.response.defer(ephemeral=True)
        if volume is None:
            row = await self.db.select(MusicSettings, server_id=interaction.guild_id)
            return await interaction.followup.send(f"Current volume: {row.volume}%")
        
        self.db.update(MusicSettings, server_id=interaction.guild_id, volume=volume)
        player = self.lavalink.player_manager.get(interaction.guild_id)
        if player: await player.set_volume(volume)
        await interaction.followup.send(f"Volume set to {volume}%")

# --- UI View with Timeout and Pitch ---
class MusicNav(discord.ui.View):
    def __init__(self, player: lavalink.DefaultPlayer, row : MusicSettings):
        super().__init__(timeout=60)
        self.player = player
        self.message = None # Will be set in the /queue command
        
        self._volume_label.label = f"{row.volume}%"
        self._speed_label.label = f"{row.speed}%"
        self._pitch_label.label = f"{row.pitch}%"
        
        self._volume_label.emoji = "🔇" if row.volume == 0 else discord.PartialEmoji(name="kirbin", id=996961280919355422, animated=True)
        self._speed_label.emoji = discord.PartialEmoji(name="sonic_waiting", id=996961282639024171, animated=True) if row.speed < 100 else discord.PartialEmoji(name="sonic_running", id=996961281837908008, animated=True)

    async def on_timeout(self):
        """Auto-delete the message when the UI times out."""
        if self.message:
            try:
                await self.message.delete()
            except:
                pass
        self.player.delete('queue_interaction')
        self.stop()

    @discord.ui.button(emoji="<:playbtn:994759843749580861>", style=discord.ButtonStyle.secondary)
    async def _unpause(self, it: discord.Interaction, btn):
        await self.player.set_pause(False)
        await it.response.send_message("Resumed!", ephemeral=True)

    @discord.ui.button(emoji="<:pausebtn:994763090413498388>", style=discord.ButtonStyle.secondary)
    async def _pause(self, it: discord.Interaction, btn):
        await self.player.set_pause(True)
        await it.response.send_message("Paused!", ephemeral=True)

    @discord.ui.button(emoji="<:loopicon:994754841710702733>", style=discord.ButtonStyle.secondary)
    async def _loop(self, it: discord.Interaction, btn):
        new_mode = (self.player.loop + 1) % 3
        self.player.set_loop(new_mode)
        await it.response.send_message(f"Loop mode changed!", ephemeral=True)

    @discord.ui.button(emoji="<:skipbtn:994763472522977290>", style=discord.ButtonStyle.secondary)
    async def _skip(self, it: discord.Interaction, btn):
        await self.player.skip()
        await it.response.send_message("Skipped!", ephemeral=True)
    
    @discord.ui.button(emoji="<:disconnectbtn:996156534927130735>", style=discord.ButtonStyle.secondary)
    async def _disconnect(self, it: discord.Interaction, btn):
        # 1. Clear player data and stop updates
        await self.player.stop()
        self.player.queue.clear()
        self.player.delete('queue_interaction')
        self.player.delete('queue_embed')
        
        # 2. Reset the Voice Status (top of the VC)
        if it.guild.me.guild_permissions.manage_channels:
            vc = it.guild.get_channel(int(self.player.channel_id))
            if vc:
                try:
                    await vc.edit(status=None)
                except: pass

        # 3. Disconnect from Voice
        await it.guild.change_voice_state(channel=None)

        # 5. Cleanup the UI
        try:
            await it.message.delete()
        except:
            pass
        self.stop()

    @discord.ui.button(label="Vol", style=discord.ButtonStyle.primary)
    async def _volume_label(self, it: discord.Interaction, btn):
        await it.response.send_message("It's just a label..." if random.random() < 0.95 else "https://tinyurl.com/c9wcjhsc", ephemeral=True)

    @discord.ui.button(label="Spd", style=discord.ButtonStyle.primary)
    async def _speed_label(self, it: discord.Interaction, btn):
        await it.response.send_message("It's just a label..." if random.random() < 0.95 else "https://tinyurl.com/c9wcjhsc", ephemeral=True)

    @discord.ui.button(label="Pit", emoji="<:treble:996969244963131473>", style=discord.ButtonStyle.primary)
    async def _pitch_label(self, it: discord.Interaction, btn):
        await it.response.send_message("It's just a label..." if random.random() < 0.95 else "https://tinyurl.com/c9wcjhsc", ephemeral=True)
    
    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger)
    async def _close(self, it: discord.Interaction, btn):
        await it.message.delete()
        self.stop()

async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))