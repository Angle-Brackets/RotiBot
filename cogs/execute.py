import discord
import logging
import io

from typing import List, Optional
from utils.ExecutionEngine import RotiExecutionEngine
from discord.ext import commands
from discord import app_commands
from enum import Enum
from pyston.models import Output


class Execute(commands.GroupCog, group_name="execute"):
    def __init__(self, bot : commands.bot):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.bot = bot
        self.engine : RotiExecutionEngine = RotiExecutionEngine()
        self.languages : List[str] = None
    
    """
    This function is used to initialize anything that requires an async operation
    """
    async def _initialize_async_items(self):
        self.languages = list(await self.engine.get_languages())
        self.languages.sort()

    def _language_options(self, current):
        choices = [
            app_commands.Choice(name=language, value=language)
            for language in self.languages
            if current.lower() in language.lower()
        ]
        
        return choices if len(choices) <= 25 else choices[:25]

    @app_commands.describe(language="The programming language you want to use! There are more than 25 available, so let autocomplete show you them all.", file="The file you wish to upload and run code with. UTF-8 Only.", arguments="Space separated list of command line arguments you want to pass.")
    @app_commands.command(name="file", description="Run code in a provided file.")
    async def _execute_file(self, interaction : discord.Interaction, language : str, file : discord.Attachment, arguments : Optional[str]):
        await interaction.response.defer()
        code : io.TextIOWrapper = io.TextIOWrapper(io.BytesIO(await file.read()), encoding="utf-8")

        output : Output = await self.engine.execute(
            language=language,
            file=code,
            args=arguments.split(" ") if arguments else []
        )

        if output.compile_stage and not output.compile_stage.code and output.compile_stage.signal:
            await interaction.followup.send(f"An error has occured compiling with signal {output.compile_stage.signal}:\n{output.compile_stage.output}", ephemeral=True)
            return
        if not output.run_stage.code and output.run_stage.signal:
            await interaction.followup.send(f"An error has occured running with signal {output.compile_stage.signal} (You may have exceeded the size of stdout!):\n{output.compile_stage.output}", ephemeral=True)
            return

        msg = output.run_stage.output if len(output.run_stage.output) < 2000 else output.run_stage.output[:2000]
        await interaction.followup.send(output.run_stage.output)
    
    @_execute_file.autocomplete(name="language")
    async def _execute_file_autocomplete(self, interaction : discord.Interaction, current : str):
        return self._language_options(current)
        

async def setup(bot : commands.Bot):
    cog = Execute(bot)
    await cog._initialize_async_items()
    await bot.add_cog(cog)