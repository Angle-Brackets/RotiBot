import enum
import typing

import discord
import re
import shlex
import data
import os, sys
import random

from data import db
from discord.ext import commands
from discord import app_commands
from utils.RotiBrain import RotiBrain

#Adds new talkbacks, also automerges talkbacks if a duplicate trigger is given.
def _add_talkback_phrase(serverID, trigger_phrases, response_phrases):
        try:
            res = ""
            t_data = db[serverID]["trigger_phrases"] #loads the current trigger data
            r_data = db[serverID]["response_phrases"] #loads the current response data
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
                            res += "Failed to merge duplicate trigger {0} due to response cap being exceeded.\n".format(trigger_list[j])
                            trigger_list_copy.remove(trigger_list[j])

                        else:
                            res += "Successfully merged trigger {0} with pre-existing talkback combo.\n".format(trigger_list[j])
                            trigger_list_copy.remove(trigger_list[j])
                            db[serverID]["response_phrases"][i] += response_list

            trigger_list = trigger_list_copy

            db[serverID]["trigger_phrases"].append(trigger_list)
            db[serverID]["response_phrases"].append(response_list)

            #Updates mongo database
            data.push_data(serverID, "trigger_phrases")
            data.push_data(serverID, "response_phrases")

            return "Successfully created new talkback." if not res else (res + "Successfully added new talkback.")
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print(exc_type, fname, exc_tb.tb_lineno)
            print(e)
            return "Failed to create new talkback action"

#This function is quite complex, in essence this function finds the triggers that most similarly match the given keyword and returns them, while also formatting the embed that stores them all.
#The return value has 2 indexes: index 0 is all the embeds in an array, and index 1 is an array of all of the matched triggers found.

#serverID is the serverID
#msg is the keyword given to the function to be used in the matching search.
#list_enabled is for /talkback list, and prevents the matched triggers from being generated or returned to increase speed.
def _generate_embed_and_triggers(guild, msg = "", list_enabled = False):
    data = db[guild.id]
    msg = msg.strip()

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
        potential_trigger = "[{0}] ".format(trigger_number)
        trigger_display = ", ".join(data["trigger_phrases"][index])

        #This will truncate triggers to 256 chars total.
        if len(potential_trigger) + len(trigger_display) > 256:
            trigger_display = trigger_display[:253] + "..."
        potential_trigger = potential_trigger + trigger_display

        #Similar idea for responses, must cap at 1024
        potential_res = ", ".join(data["response_phrases"][index])

        if len(potential_res) > 1024:
            potential_res = potential_res[:1021] + "..."

        embed.add_field(name=potential_trigger, value=potential_res, inline=False)
        trigger_number += 1

        if not list_enabled:
            matched_triggers.append(data["trigger_phrases"][index])

    #Will add support for searching response phrases later.
    #Not the max of 6000 just so I can add page numbers safely.
    for i in range(len(data["trigger_phrases"])):
        for j in range(len(data["trigger_phrases"][i])):
            if msg.casefold() in data["trigger_phrases"][i][j].casefold().strip():
                if (len(embed.fields) % 25 != 0 if len(embed.fields) > 0 else True) and len(embed) + len(''.join(data["trigger_phrases"][i])) < 5000:
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
        all_embeds[i].set_footer(text="Page {0}/{1}".format(i+1, len(all_embeds)))

    return [all_embeds, matched_triggers] if not list_enabled else all_embeds

#This is the strict match algorithm, only will return true if there is at least 1 exact match for a trigger in a message.
#Ex: trigger = "HERE" and msg = "THERE", strict match would return False whereas the normal matching algorithm would return True, since "here" is a substring of "there".
def _strict_match(trigger, msg):
    return len(re.findall('\\b' + trigger + '\\b', msg.casefold(), flags=re.IGNORECASE)) > 0


class Talkback(commands.GroupCog, group_name="talkback"):
    def __init__(self, bot : commands.Bot):
        super().__init__()
        self.bot = bot
        self.brain = RotiBrain()
    
    async def _say_talkback(self, message : discord.Message) -> bool:
        if self.bot.user in message.mentions:
            return False # If the message mentions the bot directly, all talkbacks are bypassed and it goes straight to the AI.
        
        msg = message.content
        serverID = message.guild.id
        delete_duration = db[serverID]["settings"]["talkback"]["duration"]
        strict = db[serverID]["settings"]["talkback"]["strict"]
        probability = db[serverID]["settings"]["talkback"]["res_probability"] / 100

        if serverID in db.keys():
            for i in range(len(db[serverID]["trigger_phrases"])):
                for j in range(len(db[serverID]["trigger_phrases"][i])):
                    rand = random.random()
                    view = TalkbackResView(serverID, message.author)
                    if strict and _strict_match(db[serverID]["trigger_phrases"][i][j].casefold().strip(), msg.casefold()) and probability >= rand:
                        if delete_duration > 0:
                            #If duration > 0, it will delete after x seconds
                            await message.channel.send(random.choice(db[serverID]["response_phrases"][i]), delete_after=delete_duration, view=view)
                        else:
                            #If duration = 0 (negatives are banned), it is permanent.
                            await message.channel.send(random.choice(db[serverID]["response_phrases"][i]), view=view)
                        return True

                    elif not strict and db[serverID]["trigger_phrases"][i][j].casefold().strip() in msg.casefold() and probability >= rand:
                        if delete_duration > 0:
                            #If duration > 0, it will delete after x seconds
                            await message.channel.send(random.choice(db[serverID]["response_phrases"][i]), delete_after=delete_duration, view=view)
                        else:
                            #If duration = 0 (negatives are banned), it is permanent.
                            await message.channel.send(random.choice(db[serverID]["response_phrases"][i]), view=view)
                        return True
        return False # No talkback was found or none was triggered.

    async def _say_ai_talkback(self, message : discord.Message) -> bool:
        serverID = message.guild.id
        delete_duration = db[serverID]["settings"]["talkback"]["duration"]
        probability = db[serverID]["settings"]["talkback"]["res_probability"] / 100
        view = TalkbackResView(serverID, message.author)

        # If the bot isn't mentioned and the probability isn't reached, no response.
        if self.bot.user not in message.mentions and random.random() >= probability:
            return False # No response!

        channel : discord.TextChannel = message.channel
        history : typing.List[discord.Message] = [msg async for msg in channel.history(limit=10, oldest_first=True)]
        formatted_messages = []
        # Format for the messages, this is important for the prompt!
        msg_format = "THE CONTEXT FOLLOWS THE FORMAT [MSG START] USERNAME: MESSAGE_CONTENTS [MSG END] WITH EACH MESSAGE BLOCK RELATING TO ONE USER'S MESSAGE."

        for msg in history:
            username = msg.author.display_name
            content = msg.content or "[NO CONTENT]" # Should always have content.
            formatted_messages.append(
                f"[MSG START] {username}: {content} [MSG END]"
            )
        
        chat_history = "\n".join(formatted_messages)
        response = self.brain.generate_ai_response(
            prompt=f"{message.author.display_name} said {message.content} to you! You should respond with the current chat context provided with a similar tone to what this person said to you!",
            context=chat_history,
            context_format=msg_format,
            model="llama"
        )

        if not response:
            return False # Fail gracefully

        if delete_duration:
            await message.channel.send(response, view=view, delete_after=delete_duration)
        else:
            await message.channel.send(response, view=view)

    @commands.Cog.listener()
    async def on_message(self, message : discord.Message):
        if message.author == self.bot.user or not db[message.guild.id]["settings"]["talkback"]["enabled"]:
            return
        
        talkback_activated : bool = await self._say_talkback(message)

        if talkback_activated:
            return # Talkback happened, nothing more to do.

        # Try an AI message, the probability of this happening is related to the talkback probability as well.
        await self._say_ai_talkback(message)

    @app_commands.command(name="add", description="Add a new talkback pair. Spaces separate elements, use quotes to group phrases.")
    async def _talkback_add(self, interaction : discord.Interaction, triggers : str, responses : str):
        await interaction.response.defer()
        notif = _add_talkback_phrase(interaction.guild_id, str(triggers), str(responses))
        await interaction.followup.send(notif)

    @app_commands.command(name="remove", description="Remove a current talkback trigger/response pair")
    async def _talkback_remove(self, interaction : discord.Interaction, trigger : typing.Optional[str]):
        await interaction.response.defer()

        res = _generate_embed_and_triggers(interaction.guild, str(trigger) if trigger is not None else "")
        page, pages = 1, len(res[0])
        view = Navigation(pages, res, True)

        view.message = await interaction.followup.send(embed=res[0][page-1], view=view)
        view.message = await interaction.original_response()

        await view.wait()

    @app_commands.command(name="list", description="Lists all talkback pairs present in server.")
    async def _talkback_list(self, interaction : discord.Interaction, keyword : typing.Optional[str]):
        await interaction.response.defer()
        if len(db[interaction.guild_id]["trigger_phrases"]) == 0:
            await interaction.response.send_message("No talkbacks are currently present on this server.")
            return

        embeds = _generate_embed_and_triggers(interaction.guild, str(keyword) if keyword is not None else "", list_enabled=True)

        page, pages = 1, len(embeds) #Subtract 1 for index
        view = Navigation(pages, embeds, False) #Only if pages > 1 will the navigation buttons appear.

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
    def __init__(self, pages : int, embed_list : list, trigger_list : False):
        super().__init__()
        self.value = None
        self.timeout = 60
        self.embed_list = embed_list #list of the embeds so we don't reload them unnecessarily
        self.pages = pages
        self.current_page = 1 #Subtract 1 for indexing.
        self.remove_item(self._talkback_rm_input)

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
        index = db[interaction.guild_id]["trigger_phrases"].index(self.embed_list[1][index-1])

        t, r = db[interaction.guild_id]["trigger_phrases"][index], db[interaction.guild_id]["response_phrases"][index]

        #Deletes the data
        del db[interaction.guild_id]["trigger_phrases"][index]
        del db[interaction.guild_id]["response_phrases"][index]
        data.push_data(interaction.guild_id, "trigger_phrases")
        data.push_data(interaction.guild_id, "response_phrases")

        await interaction.response.send_message(content="Successfully deleted trigger/response pair: " + str(t)[1:-1] + "/" + str(r)[1:-1])
        await self.message.delete()
        self.stop()

class TalkbackResView(discord.ui.View):
    def __init__(self, guild_id, triggeree):
        super().__init__()
        self.guild_id = guild_id
        self.triggeree = triggeree # Who triggered the talkback
    
    @discord.ui.button(label='Delete', style=discord.ButtonStyle.red)
    async def _delete(self, interaction : discord.Interaction, button : discord.ui.Button):
        # If the user has the ability to delete messages or triggered the talkback themselves.
        if interaction.user.id == self.triggeree or interaction.permissions.manage_messages:
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

async def setup(bot: commands.Bot):
    await bot.add_cog(Talkback(bot))