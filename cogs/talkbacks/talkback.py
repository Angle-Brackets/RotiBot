import enum
import typing

import discord
import re
import shlex
import random
import time
import asyncio
import logging

from utils.RotiUtilities import cog_command
from database.data import RotiDatabase
from discord.ext import commands
from discord import app_commands
from cogs.generate.RotiBrain import RotiBrain
from returns.result import Result, Success, Failure
from returns.maybe import Maybe, Some, Nothing
from typing import Optional

# Thin wrapper around Exception for Result matching.
class TalkbackError(Exception):
    def __init__(self, reason : typing.Optional[str]):
        super().__init__(reason)
        self.reason = reason

#Adds new talkbacks, also automerges talkbacks if a duplicate trigger is given.
def _add_talkback_phrase(serverID : int, db : RotiDatabase, trigger_phrases : str, response_phrases : str, logger : Optional[logging.Logger]):
        try:
            res = ""
            t_data = db[serverID, "trigger_phrases"].unwrap() #loads the current trigger data
            r_data = db[serverID, "trigger_phrases"].unwrap() #loads the current response data
            trigger_list = shlex.split(trigger_phrases) #separates entries by spaces, quotes are used to group items
            response_list = shlex.split(response_phrases) #see above

            if len(trigger_list) > 10 or len(response_list) > 10:
                return "Failed to create new talkback action (greater than 10 triggers or responses given)."

            #deletes quotes
            for i in range(len(trigger_list)):
                trigger_list[i] = trigger_list[i].replace("\"", "")
            for i in range(len(response_list)):
                response_list[i] = response_list[i].replace("\"", "")

            #lowercases everything
            t_data = [ [ item.lower() for item in sublist ] for sublist in t_data]

            #If a duplicate trigger is given, this loop attempts to merge the two response lists together since they share the same trigger.
            trigger_list_copy = trigger_list[:]
            for i in range(len(t_data)):
                trigger_set = t_data[i] #particular set of triggers (max 10)

                for j in range(len(trigger_list)):
                    if trigger_list[j].casefold() in trigger_set:
                        if len(response_list) + len(r_data[i]) > 10:
                            res += f"Failed to merge duplicate trigger {trigger_list[j]} due to response cap being exceeded.\n"
                            trigger_list_copy.remove(trigger_list[j])

                        else:
                            res += f"Successfully merged trigger {trigger_list[j]} with pre-existing talkback combo.\n"
                            trigger_list_copy.remove(trigger_list[j])
                            db[serverID, "response_phrases"].unwrap()[i] += response_list

            # TODO: Need to rewrite this.
            trigger_list = trigger_list_copy
            if trigger_list:
                db[(serverID, "trigger_phrases")] = db[(serverID, "trigger_phrases")].value_or([]) + [trigger_list]
                db[(serverID, "response_phrases")] = db[(serverID, "response_phrases")].value_or([]) + [response_list]
            else:
                db[(serverID, "trigger_phrases")] = db[(serverID, "trigger_phrases")].unwrap()
                db[(serverID, "response_phrases")] = db[(serverID, "response_phrases")].unwrap()

            return "Successfully created new talkback." if not res else (res + "Successfully added new talkback.")
        except Exception as e:
            if logger:
                logger.warning("Failed to create new talkback action with given traceback:\n%s", e)
            return "Failed to create new talkback action"

#This function is quite complex, in essence this function finds the triggers that most similarly match the given keyword and returns them, while also formatting the embed that stores them all.
#The return value has 2 indexes: index 0 is all the embeds in an array, and index 1 is an array of all of the matched triggers found.

#serverID is the serverID
#msg is the keyword given to the function to be used in the matching search.
#list_enabled is for /talkback list, and prevents the matched triggers from being generated or returned to increase speed.
def _generate_embed_and_triggers(guild : discord.Guild, db : RotiDatabase, msg = "", list_enabled = False):
    msg = msg.strip()
    trigger_phrases = db[guild.id, "trigger_phrases"].unwrap()
    response_phrases = db[guild.id, "response_phrases"].unwrap()
    all_embeds = list() #If somehow it exceeds the 6000 character limit, this stores all the embeds that the list gets split at for multiple pages. Also handles if there are greater than 25 fields in an embed...which is more common.

    matched_triggers = list()
    trigger_number = 1 #number of triggers in matched triggers
    empty_embed = None

    if list_enabled:
        if not msg:
            empty_embed = discord.Embed(title="List of all talkbacks in " + guild.name, description="Navigate with the Buttons Below.", color=0xecc98e)
        else:
            empty_embed = discord.Embed(title="List of all talkbacks in " + guild.name + " found with keyword: " + "\"" + msg + "\"", description="React with ❌ to cancel the command, or ▶️ and ◀️ to scroll through each page.", color=0xecc98e)
    else:
        empty_embed = discord.Embed(title="Possible Related Trigger/Response Pairs", description="Enter the number corresponding to the trigger/response pair you would like to remove. React with ❌ to cancel the command or ▶️ and ◀️ to scroll through each page.", color=0xecc98e)

    embed = empty_embed.copy()

    def _update_embed(embed, trigger_number, index):
        #This must be capped at 256 characters for field name (triggers) and 1024 for field values (responses) to avoid a crash
        potential_trigger = f"[{trigger_number}] "
        trigger_display = ", ".join(trigger_phrases[index])

        #This will truncate triggers to 256 chars total.
        if len(potential_trigger) + len(trigger_display) > 256:
            trigger_display = trigger_display[:253] + "..."
        potential_trigger = potential_trigger + trigger_display

        #Similar idea for responses, must cap at 1024
        potential_res = ", ".join(response_phrases[index])

        if len(potential_res) > 1024:
            potential_res = potential_res[:1021] + "..."

        embed.add_field(name=potential_trigger, value=potential_res, inline=False)
        trigger_number += 1

        if not list_enabled:
            matched_triggers.append(trigger_phrases[index])

    #Will add support for searching response phrases later.
    #Not the max of 6000 just so I can add page numbers safely.
    for i in range(len(trigger_phrases)):
        for j in range(len(trigger_phrases[i])):
            if msg.casefold() in trigger_phrases[i][j].casefold().strip():
                if (len(embed.fields) % 25 != 0 if len(embed.fields) > 0 else True) and len(embed) + len(''.join(trigger_phrases[i])) < 5000:
                    _update_embed(embed, trigger_number, i)
                    trigger_number += 1
                else:
                    all_embeds.append(embed)

                    embed = empty_embed.copy()

                    _update_embed(embed, trigger_number, i)

                    trigger_number += 1
                break

    if embed.fields == empty_embed.fields:
        embed.add_field(name="No potential trigger/response pairs found.", value="\uFEFF", inline=False)

    all_embeds.append(embed)

    #Adds page numbers to the footer of each embed
    for i in range(len(all_embeds)):
        all_embeds[i].set_footer(text=f"Page {i+1}/{len(all_embeds)}")

    return [all_embeds, matched_triggers] if not list_enabled else all_embeds

@cog_command
class Talkback(commands.GroupCog, group_name="talkback"):
    def __init__(self, bot : commands.Bot):
        super().__init__()
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.brain = RotiBrain()
        self.cooldown = 5 # 5 second cooldown for AI responses to not be rate limited.
        self.last_response = 0
        self.db = RotiDatabase()
    
    # This function is used to match words inside of a message to check if a talkback trigger is present.
    def _match_talkback(self, trigger : str, msg : str, strict : bool) -> str:
        if strict:
            #This is the strict match algorithm, only will return true if there is at least 1 exact match for a trigger in a message.
            #Ex: trigger = "HERE" and msg = "THERE", strict match would return False whereas the normal matching algorithm would return True, since "here" is a substring of "there".
            return len(re.findall('\\b' + trigger + '\\b', msg.casefold(), flags=re.IGNORECASE)) > 0
        return trigger in msg
    
    def _generate_talkback(self, message : discord.Message) -> Maybe[str]:
        if self.bot.user in message.mentions:
            return Nothing # If the message mentions the bot directly, all talkbacks are bypassed and it goes straight to the AI.
        
        msg = message.content.casefold()
        serverID = message.guild.id
        
        if serverID not in self.db:
            return Nothing

        strict = self.db[serverID, "settings", "talkback", "strict"].unwrap()
        probability = self.db[serverID, "settings", "talkback", "res_probability"].unwrap() / 100
        trigger_phrases = self.db[serverID, "trigger_phrases"].unwrap()
        responses = self.db[serverID, "response_phrases"].unwrap()
        rand = random.random()

        if probability < rand:
            return Nothing

        # Index here is used for responses since they're parallel arrays to each other.
        for i, triggers in enumerate(trigger_phrases):
            for trigger in triggers:
                if self._match_talkback(trigger.casefold(), msg, strict):
                    return Some(random.choice(responses[i]))
        return Nothing # No talkback was found

    async def _generate_ai_talkback(self, message : discord.Message) -> Result[str, TalkbackError]:
        serverID = message.guild.id 
        probability = self.db[serverID, "settings", "talkback", "ai_probability"].unwrap() / 100
        channel : discord.TextChannel = message.channel
        time_since_last = time.time() - self.last_response

        # Enforce a sleep to not overload the API
        if time_since_last < self.cooldown:
            self.logger.info(f"AI Response requested too quickly for {message.guild.name}. Sleeping for {self.cooldown - time_since_last:.2f} seconds...")
            time.sleep(self.cooldown - time_since_last)

        # If the bot isn't mentioned and the probability isn't reached, no response.
        if probability <= 0 or (self.bot.user not in message.mentions and random.random() >= probability):
            return Failure(TalkbackError)

        self.last_response = time.time()
        chat_history = "No chat history"

        history : typing.List[discord.Message] = [msg async for msg in channel.history(limit=10)]
        formatted_messages = []
        # Format for the messages, this is important for the prompt!
        msg_format = "THE CONTEXT FOLLOWS THE FORMAT [MSG START] USERNAME: MESSAGE_CONTENTS [MSG END] WITH EACH MESSAGE BLOCK RELATING TO ONE USER'S MESSAGE. THE MOST RECENT MESSAGE IS AT THE BOTTOM."

        for msg in reversed(history):
            username = msg.author.display_name
            content = msg.content or "[NO CONTENT]" # Should always have content.
            formatted_messages.append(
                f"[MSG START] {username}: {content} [MSG END]"
            )
        
        chat_history = "\n".join(formatted_messages)
        response = await asyncio.to_thread(
            self.brain.generate_ai_response, 
            f"{message.author.display_name} said {message.content} to you! You should respond with the current chat context provided with a similar tone to what this person said to you!", 
            chat_history, 
            msg_format, 
            "llama"
        )

        if not response:
            return Failure(TalkbackError()) # If any error occurs with the response.

        return Success(response)

    @commands.Cog.listener()
    async def on_message(self, message : discord.Message):
        if not message or message.author == self.bot.user or not self.db[message.guild.id, "settings", "talkback", "enabled"].unwrap():
            return
        
        serverID = message.guild.id
        delete_duration = self.db[serverID, "settings", "talkback", "duration"].unwrap()
        view = TalkbackResView(serverID, message.author)

        match self._generate_talkback(message):
            case Some(response) if delete_duration:
                await message.channel.send(response, view=view, delete_after=delete_duration)
                return
            case Some(response):
                await message.channel.send(response, view=view)
                return
            case Maybe.empty:
                pass # No talkback was fired.
        
        # Try an AI message, the probability of this happening is related to the talkback probability as well.
        match await self._generate_ai_talkback(message):
            case Success(response) if delete_duration:
                await message.channel.typing()
                await message.channel.send(response, view=view, delete_after=delete_duration)
            case Success(response):
                await message.channel.typing()
                await message.channel.send(response, view=view)
            case Failure(TalkbackError() as error) if error.reason:
                await message.channel.send(error, view=view, delete_after=5)
            case Failure(_):
                pass

    @app_commands.command(name="add", description="Add a new talkback pair. Spaces separate elements, use quotes to group phrases.")
    async def _talkback_add(self, interaction : discord.Interaction, triggers : str, responses : str):
        await interaction.response.defer()
        notif = _add_talkback_phrase(interaction.guild_id, self.db, str(triggers), str(responses), self.logger)
        await interaction.followup.send(notif)

    @app_commands.command(name="remove", description="Remove a current talkback trigger/response pair")
    async def _talkback_remove(self, interaction : discord.Interaction, trigger : typing.Optional[str]):
        await interaction.response.defer()

        res = _generate_embed_and_triggers(interaction.guild, self.db, str(trigger) if trigger is not None else "")
        page, pages = 1, len(res[0])
        view = Navigation(pages, res, True, self.db)

        view.message = await interaction.followup.send(embed=res[0][page-1], view=view)
        view.message = await interaction.original_response()

        await view.wait()

    @app_commands.command(name="list", description="Lists all talkback pairs present in server.")
    async def _talkback_list(self, interaction : discord.Interaction, keyword : typing.Optional[str]):
        await interaction.response.defer()
        if not self.db[interaction.guild_id, "trigger_phrases"].unwrap():
            await interaction.response.send_message("No talkbacks are currently present on this server.")
            return

        embeds = _generate_embed_and_triggers(interaction.guild, self.db, str(keyword) if keyword is not None else "", list_enabled=True)

        page, pages = 1, len(embeds) #Subtract 1 for index
        view = Navigation(pages, embeds, False, self.db) #Only if pages > 1 will the navigation buttons appear.

        view.message = await interaction.followup.send(embed=embeds[page-1], view=view)
        view.message = await interaction.original_response() #If I needed it in the button class

        await view.wait()

#States for the button.
class ButtonState(enum.Enum):
    BACK = 1
    NEXT = 2
    CANCEL = 3

#Used to generate the options for the dropdown to use, will only display the max of 25, and will update when page is changed.
def generate_options(current_page, embed_list, fields):
    temp = list()
    start = len(fields[current_page - 2].fields) if current_page > 1 else 0
    for i in range(start, start + len(fields[current_page - 1].fields)):
        temp.append(discord.SelectOption(label=f"Talkback #{i + 1}", description=", ".join(embed_list[i])))
    return temp

class Navigation(discord.ui.View):
    def __init__(self, pages : int, embed_list : list, trigger_list : False, db : RotiDatabase):
        super().__init__()
        self.value = None
        self.timeout = 60
        self.embed_list = embed_list #list of the embeds so we don't reload them unnecessarily
        self.pages = pages
        self.current_page = 1 #Subtract 1 for indexing.
        self.remove_item(self._talkback_rm_input)
        self.db = db

        if not trigger_list:
            self.remove_mode = False
            self.remove_item(self._talkback_rm_input)
        else:
            self.remove_mode = True

        if self.remove_mode:
            self.add_item(self._talkback_rm_input)
            self._talkback_rm_input.options = generate_options(self.current_page, self.embed_list[1], self.embed_list[0])

        if not pages > 1:
            self.remove_item(self._back)
            self.remove_item(self._next)
        #To figure out if we are in the /talkback remove command

    async def on_timeout(self) -> None:
        await self.message.delete()
        self.stop()

    @discord.ui.button(label='Back', style=discord.ButtonStyle.primary)
    async def _back(self, interaction : discord.Interaction, button : discord.ui.Button):
        if self.current_page > 1:
            self.value = ButtonState.BACK
            self.current_page -= 1

            # This is used in order to detect whether I should update the dropdown menu on a page swap
            if self.remove_mode:
                self._talkback_rm_input.options = generate_options(self.current_page, self.embed_list[1], self.embed_list[0])
                await interaction.response.edit_message(embed=self.embed_list[0][self.current_page - 1], view=self)
            else:
                await interaction.response.edit_message(embed=self.embed_list[self.current_page-1])

    @discord.ui.button(label='Next', style=discord.ButtonStyle.primary)
    async def _next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page is not self.pages:
            self.value = ButtonState.NEXT
            self.current_page += 1

            # This is used in order to detect whether I should update the dropdown menu on a page swap
            if self.remove_mode:
                self._talkback_rm_input.options = generate_options(self.current_page, self.embed_list[1], self.embed_list[0])
                await interaction.response.edit_message(embed=self.embed_list[0][self.current_page-1], view=self)
            else:
                await interaction.response.edit_message(embed=self.embed_list[self.current_page-1])

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.danger)
    async def _cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = ButtonState.CANCEL
        await self.message.delete()
        self.stop()

    #The options are dynamically generated when a page flip occurs.
    @discord.ui.select(min_values=1, options=[], placeholder="Select a Talkback")
    async def _talkback_rm_input(self, interaction : discord.Interaction, selection : discord.ui.Select):
        index = int(selection.values[0][selection.values[0].index("#") + 1:]) #Gets the corresponding index to remove.
        index = self.db[interaction.guild_id, "trigger_phrases"].unwrap().index(self.embed_list[1][index-1])
        triggers = self.db[interaction.guild_id, "trigger_phrases"].unwrap()
        responses = self.db[interaction.guild_id, "response_phrases"].unwrap()

        t = triggers[index]
        r = responses[index]

        #Deletes the data
        del triggers[index]
        del responses[index]
        self.db[interaction.guild_id, "trigger_phrases"] = triggers
        self.db[interaction.guild_id, "response_phrases"] = responses

        await interaction.response.send_message(content="Successfully deleted trigger/response pair: " + str(t)[1:-1] + "/" + str(r)[1:-1])
        await self.message.delete()
        self.stop()

class TalkbackResView(discord.ui.View):
    def __init__(self, guild_id : int , triggeree : str):
        super().__init__()
        self.guild_id = guild_id
        self.triggeree = triggeree # Who triggered the talkback
    
    @discord.ui.button(label='Delete', style=discord.ButtonStyle.red)
    async def _delete(self, interaction : discord.Interaction, button : discord.ui.Button):
        # If the user has the ability to delete messages or triggered the talkback themselves.
        original_message : discord.Message = interaction.message
        channel = original_message.channel
        member = interaction.guild.get_member(interaction.user.id)

        if interaction.user.id == self.triggeree or channel.permissions_for(member).manage_messages:
            try:
                await interaction.message.delete()
            except discord.Forbidden:
                await interaction.response.send_message(
                    "You do not have permission to delete this message.",
                    ephemeral=True
                )   
        else:
            await interaction.response.send_message(
                "You do not have permission to delete this message.",
                ephemeral=True
            )
    
    @discord.ui.button(label='Keep', style=discord.ButtonStyle.green)
    async def _keep(self, interaction: discord.Interaction, button: discord.ui.Button):
        """
        Clones the message without UI elements, cancels any delete_after timer, and keeps reactions.
        I need to do a clone here because discord doesn't let me prematurely stop any "delete_after" timer that may be ticking.
        """

        original_message : discord.Message = interaction.message
        channel = original_message.channel
        member = interaction.guild.get_member(interaction.user.id)

        # Verify permisisons
        if not (channel.permissions_for(member).manage_messages or interaction.user.id == self.triggeree):
            # If not, respond with a message indicating they lack permission
            await interaction.response.send_message(
                "You do not have permission to manage messages in this channel.",
                ephemeral=True
            )
            return  # Stop further execution
        
        # Copy message content, embeds, and attachments
        files = [await attachment.to_file() for attachment in original_message.attachments]

        # Talkbacks can't have embeds, so they're omitted.
        new_message = await channel.send(
            content=original_message.content,
            files=files  # Preserve attachments
        )

        # Re-add reactions
        for reaction in original_message.reactions:
            try:
                await new_message.add_reaction(reaction.emoji)
            except discord.Forbidden:
                pass  # Bot lacks permission to add reactions

        # Delete the original message (which maybe had delete_after)
        try:
            await original_message.delete()
        except discord.NotFound:
            pass  # If it was already deleted

async def setup(bot: commands.Bot):
    await bot.add_cog(Talkback(bot))