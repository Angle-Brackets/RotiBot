import typing

import discord
import data
from discord.ext import commands
from discord import app_commands
from data import db

class Settings(commands.GroupCog, group_name="settings"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    talkback_group = app_commands.Group(name="talkback", description="Change the settings regarding the /talkback command.")

    @talkback_group.command(name="enabled", description="Toggles if Roti will respond to talkback triggers with a response at all.")
    async def _talkback_enable(self, interaction : discord.Interaction, state : typing.Optional[bool]):
        await interaction.response.defer()
        currentState = db[interaction.guild_id]["settings"]["talkback"]["enabled"]

        if state is None:
            await interaction.followup.send("Currently, I am toggled to {0}".format(
                "respond to talkback triggers." if currentState else "not respond to talkback triggers."))
        else:
            db[interaction.guild_id]["settings"]["talkback"]["enabled"] = state
            data.push_data(interaction.guild_id, "settings")
            await interaction.followup.send("Successfully {0}".format("enabled talkback responses" if state else "disabled talkback responses."))

    @talkback_group.command(name="strict", description="Toggles if Roti will be \"strict\" in matching triggers to talkbacks / only look for exact matches.")
    async def _talkback_strict(self, interaction : discord.Interaction, state : typing.Optional[bool]):
        await interaction.response.defer()
        currentState = db[interaction.guild_id]["settings"]["talkback"]["strict"]

        if state is None:
            await interaction.followup.send("Currently, I am toggled to {0}".format(
                "be strict with talkback triggers." if currentState else "not be strict with talkback triggers."))
        else:
            db[interaction.guild_id]["settings"]["talkback"]["strict"] = state
            data.push_data(interaction.guild_id, "settings")
            await interaction.followup.send("Successfully {0}".format(
                "enabled strict talkback trigger matching." if state else "disabled strict talkback trigger matching."))

    @talkback_group.command(name="duration", description="Time in seconds before a talkback response is deleted (0 makes messages permanent).")
    async def _talkback_duration(self, interaction : discord.Interaction, length : typing.Optional[app_commands.Range[int, 0]]):
        await interaction.response.defer()
        currentLength = db[interaction.guild_id]["settings"]["talkback"]["duration"]
        if length is None:
            await interaction.followup.send("Currently, my responses are {0}".format("not set to delete themselves automatically" if currentLength == 0 else "set to delete themselves after " + str(currentLength) + " seconds."))
        else:
            db[interaction.guild_id]["settings"]["talkback"]["duration"] = length
            data.push_data(interaction.guild_id, "settings")
            await interaction.followup.send("Successfully {0}".format("set talkback responses to be delete after " + str(length) + " seconds." if length > 0 else "set talkback responses to remain permanently in chat."))

    @talkback_group.command(name="probability", description="Probability that Roti will respond to a talkback trigger, percentage from 0 - 100%.")
    async def _talkback_prob(self, interaction : discord.Interaction, probability : typing.Optional[app_commands.Range[int, 0, 100]]):
        await interaction.response.defer()
        currentProb = db[interaction.guild_id]["settings"]["talkback"]["res_probability"]
        if probability is None:
            await interaction.followup.send("Currently, I have a {0}% chance to respond to talkback triggers.".format(currentProb))
        else:
            db[interaction.guild_id]["settings"]["talkback"]["res_probability"] = probability
            data.push_data(interaction.guild_id, "settings")
            await interaction.followup.send("Successfully set probability to respond to talkbacks to {0}%".format(probability))

async def setup(bot: commands.Bot):
    await bot.add_cog(Settings(bot))