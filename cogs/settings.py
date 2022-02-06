import discord
from discord.ext import commands, tasks
from discord_slash import cog_ext, SlashContext

import data
from data import db

class Settings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    talkback_settings_enable_options = [
        {
            "name": "state",
            "type": 5,
            "description": "Toggles if Roti will respond to talkback triggers with a response at all.",
            "required": False    
        }
    ]

    talkback_settings_duration_options = [
        {
            "name": "length",
            "type": 4,
            "description": "Time in seconds before a talkback response is deleted (0 makes messages permanent).",
            "required": False    
        }
    ]

    talkback_settings_strict_options = [
        {
            "name": "state",
            "type": 5,
            "description": "Toggles if Roti will be \"strict\" in matching triggers to talkbacks / only look for exact matches.",
            "required": False
        }
    ]

    talkback_settings_prob_options = [
          {
               "name": "probability",
               "type": 4,
               "description": "Probability that Roti will respond to a talkback trigger, percentage from 0 - 100%.",
               "required": False
          }
     ]

    @cog_ext.cog_subcommand(base="settings", subcommand_group="talkback", name="enabled", description="Change settings for commands.", sub_group_desc="Change the settings regarding the /talkback command.", options=talkback_settings_enable_options)
    async def _talkback_enable(self, ctx : SlashContext, state = None):
        await ctx.defer()
        currentState = db[ctx.guild.id]["settings"]["talkback"]["enabled"]
        
        if state is None:
            await ctx.send("Currently, I am toggled to {0}".format("respond to talkback triggers." if currentState else "not respond to talkback triggers."))
        else:
            db[ctx.guild.id]["settings"]["talkback"]["enabled"] = state
            data.push_data(ctx.guild.id, "settings")
            await ctx.send("Successfully {0}".format("enabled talkback responses" if state else "disabled talkback responses."))
        
    @cog_ext.cog_subcommand(base="settings", subcommand_group="talkback", name="strict", description="Change settings for commands.", sub_group_desc="Change the settings regarding the /talkback command.", options=talkback_settings_strict_options)
    async def _talkback_strict(self, ctx: SlashContext, state = None):
        await ctx.defer()
        currentState = db[ctx.guild.id]["settings"]["talkback"]["strict"]

        if state is None:
            await ctx.send("Currently, I am toggled to {0}".format("be strict with talkback triggers." if currentState else "not be strict with talkback triggers."))
        else:
            db[ctx.guild.id]["settings"]["talkback"]["strict"] = state
            data.push_data(ctx.guild.id, "settings")
            await ctx.send("Successfully {0}".format("enabled strict talkback trigger matching." if state else "disabled strict talkback trigger matching."))


    @cog_ext.cog_subcommand(base="settings", subcommand_group="talkback", name="duration", description="Change settings for commands.", sub_group_desc="Change the settings regarding the /talkback command.", options=talkback_settings_duration_options)
    async def _talkback_duration(self, ctx: SlashContext, length = None):
        await ctx.defer()
        currentLength = db[ctx.guild.id]["settings"]["talkback"]["duration"]
        if length is None:
            await ctx.send("Currently, my responses are {0}".format("not set to delete themselves automatically" if currentLength == 0 else "set to delete themselves after " + str(currentLength) + " seconds."))
        elif length < 0:
            await ctx.send("Invalid length specified (minimum of 0).")
        else:
            db[ctx.guild.id]["settings"]["talkback"]["duration"] = length
            data.push_data(ctx.guild.id, "settings")
            await ctx.send("Successfully {0}".format("set talkback responses to be delete after " + str(length) + " seconds." if length > 0 else "set talkback responses to remain permanently in chat."))

    @cog_ext.cog_subcommand(base="settings", subcommand_group="talkback", name="probability", description="Change settings for commands.", sub_group_desc="Change the settings regarding the /talkback command.", options=talkback_settings_prob_options)
    async def _talkback_prob(self, ctx: SlashContext, probability = None):
        await ctx.defer()
        currentProb = db[ctx.guild.id]["settings"]["talkback"]["res_probability"]
        if probability is None:
            await ctx.send("Currently, I have a {0}% chance to respond to talkback triggers.".format(currentProb))
        elif probability < 0 or probability > 100:
            await ctx.send("Invalid probability specified (Integer between 0 and 100, inclusive).")
        else:
            db[ctx.guild.id]["settings"]["talkback"]["res_probability"] = probability
            data.push_data(ctx.guild.id, "settings")
            await ctx.send("Successfully set probability to respond to talkbacks to {0}%".format(probability))             

def setup(bot):
    bot.add_cog(Settings(bot))
