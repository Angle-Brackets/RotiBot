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

class Talkback(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

   
    talkback_options = [
      {
         "name": "triggers",
         "description": "The words/phrases that activate the bot. ",
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

    @cog_ext.cog_subcommand(base="talkback", name="add", description="Add a new talkback trigger/response pair", options=talkback_options)
    async def _talkback_add(self, ctx: SlashContext, triggers = str, responses = str):
        await ctx.defer()
        notif = _add_talkback_phrase(ctx.guild.id, str(triggers),str(responses))
        await ctx.send(notif)
    

def setup(bot):
    bot.add_cog(Talkback(bot))
