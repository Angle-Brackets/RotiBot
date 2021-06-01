import discord
import re
from replit import db
from discord.ext import commands
from discord_slash import cog_ext, SlashContext
import asyncio

def _add_talkback_phrase(serverID, trigger_phrases, response_phrases):
        try:
            trigger_list = re.split(r'\s+(?=[^"]*(?:"[^"]*"[^"]*)*$)',trigger_phrases)

            response_list = re.split(r'\s+(?=[^"]*(?:"[^"]*"[^"]*)*$)',response_phrases)

            if len(trigger_list) > 10 or len(response_list) > 10:
                return "Failed to create new talkback action (greater than 10 triggers or responses given)."

            for i in range(len(trigger_list)):
                trigger_list[i] = trigger_list[i].replace("\"", "")
            for i in range(len(response_list)):
                response_list[i] = response_list[i].replace("\"", "")
            
            db[str(serverID)]["trigger_phrases"].append(trigger_list)
            db[str(serverID)]["response_phrases"].append(response_list)

            return "New talkback action successfully created."
        except:
            return "Failed to create new talkback action"

#This function is quite complex, in essence this function finds the triggers that most similarly match the given keyword and returns them, while also formatting the embed that stores them all.
#The return value has 2 indexes: index 0 is all the embeds in an array, and index 1 is an array of all of the matched triggers found.
def _remove_talkback(serverID, msg):
    data = db[str(serverID)]
    msg = msg[0:msg.index(" ") if " " in msg else len(msg)] #elimates any spaces

    all_embeds = list() #If somehow it exceeds the 6000 character limit, this stores all the embeds that the list gets split at for multiple pages.

    matched_triggers = list()
    trigger_number = 1 #number of trigger in matched triggers

    empty_embed = discord.Embed(title="Possible Related Trigger/Response Pairs", description="Enter the number corresponding to the trigger/response pair you would like to remove. React with ❌ to cancel the command.", color=0xecc98e)

    embed = empty_embed

    def _update_embed(embed, trigger_number, index):
        potential_trigger = "[{0}] ".format(trigger_number) + ", ".join(data["trigger_phrases"][index])

        potential_res = ", ".join(data["response_phrases"][index])

        embed.add_field(name=potential_trigger, value=potential_res, inline=False)
                    
        trigger_number += 1
        matched_triggers.append(data["trigger_phrases"][index])


    for i in range(len(data["trigger_phrases"])):
        for j in range(len(data["trigger_phrases"][i])):
            if msg.casefold() in data["trigger_phrases"][i][j].casefold().strip():
                if not len(embed) > 6000 or len(embed) + len(data["trigger_phrases"][i]) > 6000:
                    _update_embed(embed, trigger_number, i)
                    trigger_number += 1 
                else:
                    all_embeds.append(embed)

                    embed = empty_embed

                    _update_embed(embed, trigger_number, i)
                    
                    trigger_number += 1
                break

    if embed.fields == empty_embed.fields:
        embed.add_field(name="No potential trigger/response pairs found.", value="Epic Embed Fail.", inline=False)
    
    all_embeds.append(embed)
    return [all_embeds, matched_triggers]

class Talkback(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

   
    talkback_add_options = [
      {
         "name": "triggers",
         "description": "The words/phrases that activate the bot.",
         "required": True,
         "type": 3,
      },
      {
         "name": "responses",
         "description": "The words/phrases that the bot responds with.",
         "required": True,
         "type": 3
      }
   ]

    talkback_remove_options = [
       {
           "name": "trigger",
           "description": "A word or phrase that is identical or similar to one in a talkback action",
           "required": True,
           "type": 3,
       },
   ]

    @cog_ext.cog_subcommand(base="talkback", name="add", description="Add a new talkback trigger/response pair", options=talkback_add_options)
    async def _talkback_add(self, ctx: SlashContext, triggers = str, responses = str):
        await ctx.defer()
        notif = _add_talkback_phrase(ctx.guild.id, str(triggers),str(responses))
        await ctx.send(notif)
    
    @cog_ext.cog_subcommand(base="talkback", name="remove", description="Remove a current talkback trigger/response pair", options=talkback_remove_options)
    async def _talkback_remove(self, ctx: SlashContext, trigger = str):
        await ctx.defer()

        def check_reaction(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["◀️", "▶️", "❌"]

        
        res = _remove_talkback(ctx.guild.id, str(trigger))
        page, pages = 1, len(res[0]) #Subtract 1 for index!

        msg = await ctx.send(embed=res[0][page-1])

        if pages > 1:
            await msg.add_reaction("◀️")
            await msg.add_reaction("▶️")
        await msg.add_reaction("❌")
        
        def check_message(m):
            return m.content.isnumeric() and int(m.content) <= len(res[1]) and m.channel == ctx.channel and m.author == ctx.author

        done, pending = await asyncio.wait([
            self.bot.wait_for('message', timeout=60, check=check_message),
            self.bot.wait_for('reaction_add', timeout=60, check=check_reaction)
        ], return_when=asyncio.FIRST_COMPLETED
        )

        while True:
            try:
                response = done.pop().result()
                
                if type(response) is discord.Message:
                    index = int(response.content)
                    index = db[str(ctx.guild.id)]["trigger_phrases"].index(res[1][index-1])

                    t, r = db[str(ctx.guild.id)]["trigger_phrases"][index], db[str(ctx.guild.id)]["response_phrases"][index]

                    del db[str(ctx.guild.id)]["trigger_phrases"][index]
                    del db[str(ctx.guild.id)]["response_phrases"][index]

                    await ctx.send("Successfully deleted trigger/response pair: " + str(t.value)[1:-1] + "/" + str(r.value)[1:-1])
                    await msg.delete()
                    break
                    
                elif type(response[0]) is discord.Reaction:
                    reaction = response[0]
                    user = response[1]
                    
                    if str(reaction.emoji) == "▶️" and page is not pages:
                        pages += 1
                        await msg.edit(embed=res[0][page-1])
                        await msg.remove_reaction(reaction, user)    
                    elif str(reaction.emoji) == "◀️" and page > 1:
                        pages -= 1
                        await msg.edit(embed=res[0][page-1])
                        await msg.remove_reaction(reaction,user)
                    elif str(reaction.emoji) == "❌":
                        await msg.remove_reaction(reaction.emoji, self.bot.user)
                        await msg.delete()
                        break
                    else:
                        await msg.remove_reaction(reaction,user)
            except asyncio.TimeoutError or ...:
                await msg.delete()

                for future in done: 
                    future.exception()

                for future in pending:
                    future.cancel()
                break
        

def setup(bot):
    bot.add_cog(Talkback(bot))
