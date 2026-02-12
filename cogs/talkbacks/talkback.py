import enum
import typing
import discord
import re
import shlex
import random
import time
import asyncio
import logging
import itertools

from cogs.statistics.statistics_helpers import statistic
from utils.RotiUtilities import cog_command
from database.data import RotiDatabase, TalkbacksTable, TalkbackSettings, GenerateSettings
from discord.ext import commands
from discord import app_commands
from cogs.generate.RotiBrain import RotiBrain
from returns.result import Result, Success, Failure
from returns.maybe import Maybe, Some, Nothing
from typing import Optional, List, Dict, Any, Tuple

# Thin wrapper around Exception for Result matching.
class TalkbackError(Exception):
    def __init__(self, reason : typing.Optional[str]):
        super().__init__(reason)
        self.reason = reason

def _generate_talkback_embeds(guild: discord.Guild, talkbacks: List[Dict[str, Any]], title_suffix: str = ""):
    """
    Generates paginated embeds from the list of talkback dictionaries returned by the driver.
    """
    embed_base = discord.Embed(
        title=f"Talkbacks in {guild.name} {title_suffix}",
        description="Use the dropdown to delete items, or buttons to navigate pages.", 
        color=0xecc98e
    )
    
    if not talkbacks:
        embed_base.description = "No talkbacks found."
        return [embed_base]

    # Batch into groups of 10 for cleaner embeds (Discord field limit is 25, but 10 is readable)
    # Using itertools.batched if python 3.12+, otherwise slice manually. 
    # Assuming Python 3.10+, we do manual slicing for safety.
    chunk_size = 10
    chunks = [talkbacks[i:i + chunk_size] for i in range(0, len(talkbacks), chunk_size)]
    
    all_embeds = []
    
    for i, chunk in enumerate(chunks, start=1):
        embed = embed_base.copy()
        embed.set_footer(text=f"Page {i}/{len(chunks)}")
        
        for index, tb in enumerate(chunk, start=1):
            # Display format:
            # Triggers: "hello", "hi"
            # Responses: "hey", "what's up"
            triggers_str = ", ".join([f'"{t}"' if " " in t else t for t in tb['triggers']])
            responses_str = ", ".join([f'"{r}"' if " " in r else r for r in tb['responses']])
            
            # Truncate to prevent errors
            if len(triggers_str) > 200: triggers_str = triggers_str[:197] + "..."
            if len(responses_str) > 800: responses_str = responses_str[:797] + "..."
            
            # We use the index relative to the page for display, but the ID is what matters for deletion
            embed.add_field(
                name=f"{index}. Triggers: {triggers_str}",
                value=f"Responses: {responses_str}",
                inline=False
            )
        all_embeds.append(embed)
        
    return all_embeds, chunks

@cog_command
class Talkback(commands.GroupCog, group_name="talkback"):
    def __init__(self, bot : commands.Bot):
        super().__init__()
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.brain = RotiBrain()
        self.cooldown = 5 
        self.last_response = 0
        self.db = RotiDatabase()
        self.talkback_driver = TalkbackDriver(self.db, self.logger)
        
    @statistic("Standard Talkbacks", category="Talkbacks")
    async def _generate_talkback(self, message : discord.Message) -> Maybe[str]:
        # Uses the driver's RPC call to find a matching response efficiently
        response = await self.talkback_driver.get_response(message.guild.id, message.content)
        if response:
            return Some(response)
        return Nothing

    # TODO: CHECK AI! This function remains largely untouched as requested.
    @statistic("AI Talkbacks", category="Talkbacks")
    async def _generate_ai_talkback(self, message : discord.Message) -> Result[str, TalkbackError]:
        async with message.channel.typing():
            channel : discord.TextChannel = message.channel
            time_since_last = time.time() - self.last_response
            HISTORY_LIMIT = 30

            if time_since_last < self.cooldown:
                self.logger.info(f"AI Response requested too quickly for {message.guild.name}. Sleeping...")
                time.sleep(self.cooldown - time_since_last)

            self.last_response = time.time()
            
            # [AI LOGIC PRESERVED FROM ORIGINAL FILE]
            history : typing.List[discord.Message] = [msg async for msg in channel.history(limit=HISTORY_LIMIT)]
            formatted_messages = []
            msg_format = "THE CONTEXT FOLLOWS THE FORMAT [MSG START] USERNAME: MESSAGE_CONTENTS [MSG END]..."

            for msg in reversed(history):
                username = msg.author.display_name
                content = msg.content or "[NO CONTENT]" 
                formatted_messages.append(f"[MSG START] {username}: {content} [MSG END]")
            
            chat_history = "\n".join(formatted_messages)
            gen_settings = await self.db.select(GenerateSettings, server_id=message.guild.id)

            response = await asyncio.to_thread(
                self.brain.generate_ai_response, 
                f"{message.author.display_name} said {message.content} to you! Respond with similar tone!", 
                chat_history, 
                msg_format,
                model=gen_settings.default_model,
                temperature=gen_settings.temperature
            )

            if not response:
                return Failure(TalkbackError(None))

            return Success(response)

    @commands.Cog.listener()
    async def on_message(self, message : discord.Message):
        if not message or message.author == self.bot.user:
            return
        
        # Check if enabled via settings
        settings = await self.db.select(TalkbackSettings, server_id=message.guild.id)
        if not settings.enabled:
            return
        
        serverID = message.guild.id
        view = TalkbackResView(serverID, message.author.id)
        
        was_mentioned = self.bot.user in message.mentions
        talkback_prob = settings.res_probability / 100
        ai_prob = settings.ai_probability / 100
        roll = random.uniform(0.0, 1.0)

        # Standard Talkback
        if not was_mentioned and roll < talkback_prob:
            match await self._generate_talkback(message):
                case Some(response) if settings.duration > 0:
                    await message.channel.send(response, view=view, delete_after=settings.duration)
                    return
                case Some(response):
                    await message.channel.send(response, view=view)
                    return
                case _:
                    pass

        # AI Talkback
        elif was_mentioned or roll < ai_prob:
            match await self._generate_ai_talkback(message):
                case Success(response) if settings.duration > 0:
                    await message.channel.send(response, view=view, delete_after=settings.duration)
                case Success(response):
                    await message.channel.send(response, view=view)
                case Failure(TalkbackError() as error) if error.reason:
                    await message.channel.send(error.reason, view=view, delete_after=5)
                case _:
                    pass
    
    @app_commands.command(name="add", description="Add a new talkback pair. Spaces separate elements, use quotes to group phrases.")
    async def _talkback_add(self, interaction : discord.Interaction, triggers : str, responses : str):
        await interaction.response.defer()
        # Uses the driver's add_talkback which handles the RPC call and merging logic
        result_msg = await self.talkback_driver.add_talkback(
            interaction.guild_id, 
            triggers, 
            responses
        )
        await interaction.followup.send(result_msg)

    @app_commands.command(name="remove", description="Remove a current talkback trigger/response pair")
    async def _talkback_remove(self, interaction : discord.Interaction, trigger : typing.Optional[str]):
        await interaction.response.defer()
        # 1. Fetch data using driver
        talkbacks = await self.talkback_driver.list_all_talkbacks(interaction.guild_id, trigger)
        
        if not talkbacks:
            await interaction.followup.send("No matching talkbacks found.")
            return

        # 2. Generate Embeds using new helper
        embeds, chunks = _generate_talkback_embeds(interaction.guild, talkbacks, title_suffix=f"(Search: {trigger})" if trigger else "")
        
        # 3. Create Navigation View
        # We pass the 'chunks' (list of lists of talkback dicts) so the View knows what IDs are on what page
        view = Navigation(len(embeds), embeds, chunks, self.talkback_driver, remove_mode=True)

        view.message = await interaction.followup.send(embed=embeds[0], view=view)
        await view.wait()

    @app_commands.command(name="list", description="Lists all talkback pairs present in server.")
    async def _talkback_list(self, interaction : discord.Interaction, keyword : typing.Optional[str]):
        await interaction.response.defer()
        talkbacks = await self.talkback_driver.list_all_talkbacks(interaction.guild_id, keyword)

        if not talkbacks:
            await interaction.followup.send("No talkbacks are currently present on this server matching your query.")
            return

        embeds, chunks = _generate_talkback_embeds(interaction.guild, talkbacks, title_suffix=f"(Search: {keyword})" if keyword else "")
        view = Navigation(len(embeds), embeds, chunks, self.talkback_driver, remove_mode=False) 

        view.message = await interaction.followup.send(embed=embeds[0], view=view)
        await view.wait()

class Navigation(discord.ui.View):
    def __init__(self, pages: int, embeds: list, chunks: list, driver: 'TalkbackDriver', remove_mode: bool = False):
        super().__init__(timeout=60)
        self.pages = pages
        self.embeds = embeds
        self.chunks = chunks # The actual data corresponding to each page [[{id:1...}, {id:2...}], [...]]
        self.driver = driver
        self.remove_mode = remove_mode
        self.current_page = 1 
        self.message = None

        # Setup Buttons
        if self.pages <= 1:
            self.remove_item(self._back)
            self.remove_item(self._next)

        # Setup Dropdown
        if self.remove_mode:
            self._update_dropdown_options()
        else:
            self.remove_item(self._talkback_rm_input)

    def _update_dropdown_options(self):
        """Generates dropdown options based on the IDs in the current page's chunk."""
        if not self.chunks: return
        
        current_chunk = self.chunks[self.current_page - 1]
        options = []
        
        for i, tb in enumerate(current_chunk, start=1):
            first_trigger = tb['triggers'][0] if tb['triggers'] else "???"
            label = f"{i}. {first_trigger}"
            if len(label) > 100: label = label[:97] + "..."
            
            # The VALUE is the database ID, enabling safe O(1) deletion
            options.append(discord.SelectOption(
                label=label,
                description=f"ID: {tb['id']}",
                value=str(tb['id']) 
            ))
            
        self._talkback_rm_input.options = options

    async def _update_view(self, interaction: discord.Interaction):
        if self.remove_mode:
            self._update_dropdown_options()
        await interaction.response.edit_message(embed=self.embeds[self.current_page - 1], view=self)

    async def on_timeout(self) -> None:
        try:
            if self.message: await self.message.delete()
        except: pass
        self.stop()

    @discord.ui.button(label='Back', style=discord.ButtonStyle.primary)
    async def _back(self, interaction : discord.Interaction, button : discord.ui.Button):
        if self.current_page > 1:
            self.current_page -= 1
            await self._update_view(interaction)
        else:
            await interaction.response.defer() # No op

    @discord.ui.button(label='Next', style=discord.ButtonStyle.primary)
    async def _next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.pages:
            self.current_page += 1
            await self._update_view(interaction)
        else:
            await interaction.response.defer()

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.danger)
    async def _cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.message: await self.message.delete()
        self.stop()

    @discord.ui.select(min_values=1, options=[], placeholder="Select a Talkback to Remove")
    async def _talkback_rm_input(self, interaction : discord.Interaction, selection : discord.ui.Select):
        # Value is the Talkback ID (str)
        talkback_id = int(selection.values[0])
        
        success, msg = await self.driver.delete_talkback(interaction.guild_id, talkback_id)
        
        await interaction.response.send_message(content=msg, ephemeral=True)
        if self.message: await self.message.delete()
        self.stop()

class TalkbackResView(discord.ui.View):
    def __init__(self, guild_id : int , triggeree_id : int):
        super().__init__(timeout=None) # Persistent-ish view usually needs no timeout or long timeout
        self.guild_id = guild_id
        self.triggeree_id = triggeree_id 
    
    @discord.ui.button(label='Delete', style=discord.ButtonStyle.red)
    async def _delete(self, interaction : discord.Interaction, button : discord.ui.Button):
        original_message : discord.Message = interaction.message
        channel = original_message.channel
        member = interaction.guild.get_member(interaction.user.id)

        # Check permissions: Either the person who triggered it, or a Manage Messages admin
        if interaction.user.id == self.triggeree_id or (member and channel.permissions_for(member).manage_messages):
            try:
                await interaction.message.delete()
            except discord.Forbidden:
                await interaction.response.send_message("Missing permissions.", ephemeral=True)   
        else:
            await interaction.response.send_message("You cannot delete this.", ephemeral=True)
    
    @discord.ui.button(label='Keep', style=discord.ButtonStyle.green)
    async def _keep(self, interaction: discord.Interaction, button: discord.ui.Button):
        original_message = interaction.message
        channel = original_message.channel
        member = interaction.guild.get_member(interaction.user.id)

        if not (member and (channel.permissions_for(member).manage_messages or interaction.user.id == self.triggeree_id)):
            await interaction.response.send_message("Permission denied.", ephemeral=True)
            return
        
        files = [await attachment.to_file() for attachment in original_message.attachments]
        
        # Resend content to strip the "Delete after" timer and View
        try:
            new_msg = await channel.send(content=original_message.content, files=files)
            # Try to restore reactions
            for reaction in original_message.reactions:
                try: await new_msg.add_reaction(reaction.emoji)
                except: pass
            
            await original_message.delete()
        except Exception as e:
            await interaction.response.send_message(f"Failed to keep message: {e}", ephemeral=True)


class TalkbackDriver:
    """
    Driver class for managing talkbacks in RotiDB.
    """
    def __init__(self, db: RotiDatabase, logger: Optional[logging.Logger] = None):
        self.db = db
        self.logger = logger or logging.getLogger(__name__)
    
    async def add_talkback(self, server_id: int, trigger_phrases: str, response_phrases: str) -> str:
        # implementation...
        try:
            trigger_list = [t.replace('"', '') for t in shlex.split(trigger_phrases)]
            response_list = [r.replace('"', '') for r in shlex.split(response_phrases)]
            if len(trigger_list) > 10 or len(response_list) > 10: return "Too many items (max 10)."
            if not trigger_list or not response_list: return "No triggers/responses provided."
            
            result = await self.db.supabase.rpc('create_talkback_with_merge', {
                'p_server_id': server_id, 'p_new_triggers': trigger_list, 'p_new_responses': response_list
            }).execute()
            
            return result.data[0]['message'] if result.data else "Failed."
        except Exception as e:
            self.logger.warning(f"Add Error: {e}")
            return "Failed to create talkback."

    async def get_response(self, server_id: int, message: str) -> Optional[str]:
        try:
            result = await self.db.supabase.rpc('get_random_talkback_response', {
                'p_server_id': server_id, 'p_message': message
            }).execute()
            return result.data if result.data else None
        except Exception as e:
            self.logger.error(f"Get Response Error: {e}")
            return None

    async def list_all_talkbacks(self, server_id: int, search_keyword: Optional[str] = None) -> List[Dict[str, Any]]:
        try:
            query = self.db.supabase.from_('talkbacks').select('id, responses, created_at, talkback_triggers(trigger)').eq('server_id', server_id).order('id')
            result = await query.execute()
            if not result.data: return []
            
            talkbacks = []
            for item in result.data:
                triggers = [t['trigger'] for t in item['talkback_triggers']]
                if search_keyword and not any(search_keyword.lower() in t.lower() for t in triggers): continue
                talkbacks.append({'id': item['id'], 'triggers': triggers, 'responses': item['responses']})
            return talkbacks
        except Exception: return []

    async def delete_talkback(self, server_id: int, talkback_id: int) -> Tuple[bool, str]:
        try:
            # Basic validation query
            check = await self.db.supabase.from_('talkbacks').select('id').eq('id', talkback_id).eq('server_id', server_id).execute()
            if not check.data: return False, "Talkback not found."
            
            await self.db.delete(TalkbacksTable, id=talkback_id)
            return True, "Deleted."
        except Exception: return False, "Failed."

async def setup(bot: commands.Bot):
    await bot.add_cog(Talkback(bot))