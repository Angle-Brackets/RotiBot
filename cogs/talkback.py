import discord
import re
from replit import db
from discord.ext import commands
from discord_slash import cog_ext, SlashContext

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

def _remove_talkback(serverID, msg):
	data = db[str(serverID)]
	msg = msg[0:msg.index(" ") if " " in msg else len(msg)] #elimates any spaces
	contents = "" #List of possible triggers found

	partition_words = [] #If somehow it exceeds the 6000 character limit, this stores the words that the list gets split at for multiple pages.

	trigger_number = 1

	for i in range(len(data["trigger_phrases"])):
		for j in range(len(data["trigger_phrases"][i])):
			if msg.casefold() in data["trigger_phrases"][i][j].casefold().strip():
				contents += "[{0}] ".format(trigger_number) + ", ".join(data["trigger_phrases"][i]) + " / " + ", ".join(data["response_phrases"][i]) + "\n" 
				trigger_number += 1
				break
	return contents + "\n" + "length: " + str(len(contents)) + " characters." if len(contents) > 0 else "No potential trigger/response pairs found"

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
           "description": "The words/phrases that activate the bot.",
           "required": True,
           "type": 3,
       },
    #    {
    #        #may add this later to remove function..
    #        "name": "responses",
    #        "description": "The words/phrases that the bot responds with.",
    #        "required": False,
    #        "type": 3,
    #    },
   ]

    @cog_ext.cog_subcommand(base="talkback", name="add", description="Add a new talkback trigger/response pair", options=talkback_add_options)
    async def _talkback_add(self, ctx: SlashContext, triggers = str, responses = str):
        await ctx.defer()
        notif = _add_talkback_phrase(ctx.guild.id, str(triggers),str(responses))
        await ctx.send(notif)
    
    @cog_ext.cog_subcommand(base="talkback", name="remove", description="Remove a current talkback trigger/response pair", options=talkback_remove_options)
    async def _talkback_remove(self, ctx: SlashContext, trigger = str):
        await ctx.defer()
        embed = discord.Embed(title="Possible Trigger/Response Pairs", description=_remove_talkback(ctx.guild.id, trigger), color=discord.Color.from_rgb(236, 201, 142))
		
        await ctx.send(content="still not done xD", embeds=[embed])


def setup(bot):
    bot.add_cog(Talkback(bot))
