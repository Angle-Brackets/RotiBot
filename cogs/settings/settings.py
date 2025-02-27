import typing

import discord
from discord.ext import commands
from discord import app_commands
from database.data import RotiDatabase
from utils.command_utils import cog_command

@cog_command
class Settings(commands.GroupCog, group_name="settings"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.db = RotiDatabase()

    talkback_group = app_commands.Group(name="talkback", description="Change the settings regarding the /talkback command.")

    @talkback_group.command(name="enable", description="Toggles AI responses and if Roti will respond to talkback triggers with a response at all.")
    async def _talkback_enable(self, interaction : discord.Interaction, state : typing.Optional[bool]):
        await interaction.response.defer()
        current_state = self.db[interaction.guild_id, "settings", "talkback", "enabled"].unwrap()

        if state is None:
            await interaction.followup.send(f"Currently, I am toggled to {"respond to talkback triggers." if current_state else "not respond to talkback triggers."}")
        else:
            self.db[interaction.guild_id, "settings", "talkback", "enabled"] = state
            await interaction.followup.send(f"Successfully {"enabled talkback responses" if state else "disabled talkback responses."}")

    @talkback_group.command(name="strict", description="Toggles if Roti will be \"strict\" in matching triggers to talkbacks / only look for exact matches.")
    async def _talkback_strict(self, interaction : discord.Interaction, state : typing.Optional[bool]):
        await interaction.response.defer()
        current_state = self.db[interaction.guild_id, "settings", "talkback", "strict"].unwrap()

        if state is None:
            await interaction.followup.send(f"Currently, I am toggled to {"be strict with talkback triggers." if current_state else "not be strict with talkback triggers."}")
        else:
            self.db[interaction.guild_id, "settings", "talkback", "strict"] = state
            await interaction.followup.send(f"Successfully {"enabled strict talkback trigger matching." if state else "disabled strict talkback trigger matching."}")

    @talkback_group.command(name="duration", description="Time in seconds before a talkback response is deleted (0 makes messages permanent).")
    async def _talkback_duration(self, interaction : discord.Interaction, length : typing.Optional[app_commands.Range[int, 0]]):
        await interaction.response.defer()
        current_length = self.db[interaction.guild_id, "settings", "talkback", "duration"].unwrap()
        if length is None:
            await interaction.followup.send(f"Currently, my responses are {"not set to delete themselves automatically" if not current_length else "set to delete themselves after " + str(current_length) + " seconds."}")
        else:
            self.db[interaction.guild_id, "settings", "talkback", "duration"] = length
            await interaction.followup.send(f"Successfully {"set talkback responses to be delete after " + str(length) + " seconds." if length > 0 else "set talkback responses to remain permanently in chat."}")

    @talkback_group.command(name="probability", description="Probability that Roti will respond to a talkback trigger, percentage from 0 - 100%.")
    async def _talkback_prob(self, interaction : discord.Interaction, probability : typing.Optional[app_commands.Range[int, 0, 100]]):
        await interaction.response.defer()
        current_prob = self.db[interaction.guild_id, "settings", "talkback", "res_probability"].unwrap()
        if probability is None:
            await interaction.followup.send(f"Currently, I have a {current_prob}% chance to respond to talkback triggers.")
        else:
            self.db[interaction.guild_id, "settings", "talkback", "res_probability"] = probability
            await interaction.followup.send(f"Successfully set probability to respond to talkbacks to {probability}%")

    @talkback_group.command(name="ai_probability", description="Probability an AI response will occur, percentage from 0 - 100%.")
    async def _talkback_ai_probability(self, interaction : discord.Interaction, probability : typing.Optional[app_commands.Range[int, 0, 100]]):
        await interaction.response.defer()
        current_prob = self.db[interaction.guild_id, "settings", "talkback", "ai_probability"].unwrap()
        if probability is None:
            await interaction.followup.send(f"Currently, I have a {current_prob}% chance to randomly respond with an AI message.")
        else:
            self.db[interaction.guild_id, "settings", "talkback", "ai_probability"] = probability
            await interaction.followup.send(f"Successfully set probability to randomly respond with an AI message to {probability}%")

async def setup(bot: commands.Bot):
    await bot.add_cog(Settings(bot))