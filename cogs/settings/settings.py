import typing

import discord
from discord.ext import commands
from discord import app_commands
from cogs.generate.RotiBrain import RotiBrain
from database.data import RotiDatabase, TalkbackSettings, MusicSettings, GenerateSettings
from utils.RotiUtilities import cog_command

@cog_command
class Settings(commands.GroupCog, group_name="settings"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.db = RotiDatabase()
        self.brain = RotiBrain()

    talkback_group = app_commands.Group(name="talkback", description="Change the settings regarding the /talkback command.")

    @talkback_group.command(name="enable", description="Toggles AI responses and if Roti will respond to talkback triggers with a response at all.")
    async def _talkback_enable(self, interaction : discord.Interaction, state : typing.Optional[bool]):
        await interaction.response.defer()
        current = await self.db.select(TalkbackSettings, server_id=interaction.guild_id)

        if state is None:
            await interaction.followup.send(f"Currently, I am toggled to {"respond to talkback triggers." if current.enabled else "not respond to talkback triggers."}")
        else:
            self.db.update(TalkbackSettings, server_id=interaction.guild_id, enabled=state)
            await interaction.followup.send(f"Successfully {"enabled talkback responses" if state else "disabled talkback responses."}")

    @talkback_group.command(name="strict", description="Toggles if Roti will be \"strict\" in matching triggers to talkbacks / only look for exact matches.")
    async def _talkback_strict(self, interaction : discord.Interaction, state : typing.Optional[bool]):
        # TODO(02/04/26): This isn't currently implemented, everything is a non-strict match right now.
        await interaction.response.defer()
        current = await self.db.select(TalkbackSettings, server_id=interaction.guild.id)

        if state is None:
            await interaction.followup.send(f"Currently, I am toggled to {"be strict with talkback triggers." if current.strict else "not be strict with talkback triggers."}")
        else:
            self.db.update(TalkbackSettings, server_id=interaction.guild_id, strict=state)
            await interaction.followup.send(f"Successfully {"enabled strict talkback trigger matching." if state else "disabled strict talkback trigger matching."}")

    @talkback_group.command(name="duration", description="Time in seconds before a talkback response is deleted (0 makes messages permanent).")
    async def _talkback_duration(self, interaction : discord.Interaction, length : typing.Optional[app_commands.Range[int, 0]]):
        await interaction.response.defer()
        current = await self.db.select(TalkbackSettings, server_id=interaction.guild.id)
        if length is None:
            await interaction.followup.send(f"Currently, my responses are {"not set to delete themselves automatically" if not current.duration else "set to delete themselves after " + str(current.duration) + " seconds."}")
        else:
            self.db.update(TalkbackSettings, server_id=interaction.guild_id, duration=length)
            await interaction.followup.send(f"Successfully {"set talkback responses to be delete after " + str(length) + " seconds." if length > 0 else "set talkback responses to remain permanently in chat."}")

    @talkback_group.command(name="probability", description="Probability that Roti will respond to a talkback trigger, percentage from 0 - 100%.")
    async def _talkback_prob(self, interaction : discord.Interaction, probability : typing.Optional[app_commands.Range[int, 0, 100]]):
        await interaction.response.defer()
        current = await self.db.select(TalkbackSettings, server_id=interaction.guild.id)
        if probability is None:
            await interaction.followup.send(f"Currently, I have a {current.res_probability}% chance to respond to talkback triggers.")
        else:
            self.db.update(TalkbackSettings, server_id=interaction.guild_id, res_probability=probability)
            await interaction.followup.send(f"Successfully set probability to respond to talkbacks to {probability}%")

    @talkback_group.command(name="ai_probability", description="Probability an AI response will occur, percentage from 0 - 100%.")
    async def _talkback_ai_probability(self, interaction : discord.Interaction, probability : typing.Optional[app_commands.Range[int, 0, 100]]):
        await interaction.response.defer()
        current = await self.db.select(TalkbackSettings, server_id=interaction.guild.id)
        if probability is None:
            await interaction.followup.send(f"Currently, I have a {current.ai_probability}% chance to randomly respond with an AI message.")
        else:
            self.db.update(TalkbackSettings, server_id=interaction.guild_id, ai_probability=probability)
            await interaction.followup.send(f"Successfully set probability to randomly respond with an AI message to {probability}%")

    generate_group = app_commands.Group(name="generate", description="Change the settings regarding the /generate command.")

    @generate_group.command(name="default_model", description="Sets the default AI text model for this server.")
    async def _generate_default_model(self, interaction: discord.Interaction, model_name: typing.Optional[str]):
        """
        Sets the default text generation model for the server.
        Uses ephemeral responses to keep chat clean.
        """
        # Defer ephemerally
        await interaction.response.defer(ephemeral=True)
        
        current = await self.db.select(GenerateSettings, server_id=interaction.guild_id)
        
        if model_name is None:
            await interaction.followup.send(f"Current default model is: **{current.default_model}**")
            return

        # Validation
        from cogs.generate.RotiBrain import RotiBrain
        brain = RotiBrain()
        
        if model_name not in brain.text_models:
            # Create a nice list of available models for the error message
            available = ", ".join([f"`{name}`" for name in list(brain.text_models.keys())[:5]])
            await interaction.followup.send(
                f"❌ Invalid model name: `{model_name}`\n"
                f"Available models include: {available}, and more.\n"
                "Use the autocomplete suggestions to pick a valid model."
            )
            return

        # Update setting
        self.db.upsert(GenerateSettings, server_id=interaction.guild_id, default_model=model_name)
        await interaction.followup.send(f"Successfully set default AI model to: **{model_name}**")

    @_generate_default_model.autocomplete("model_name")
    async def _generate_default_model_autocomplete(self, interaction: discord.Interaction, current: str) -> typing.List[app_commands.Choice[str]]:
        models = list(self.brain.text_models.keys())
        return [
            app_commands.Choice(name=model, value=model)
            for model in models if current.lower() in model.lower()
        ][:25]

async def setup(bot: commands.Bot):
    await bot.add_cog(Settings(bot))