import discord
import logging

from io import TextIOWrapper, BytesIO
from typing import List, Optional, Callable, Union, Tuple
from utils.ExecutionEngine import RotiExecutionEngine
from discord.ext import commands
from discord import app_commands
from pyston.models import Output
from functools import partial


class Execute(commands.GroupCog, group_name="execute"):
    def __init__(self, bot : commands.bot):
        super().__init__()
        self.logger = logging.getLogger(__name__)
        self.bot = bot
        self.engine : RotiExecutionEngine = RotiExecutionEngine()
        self.languages : List[str] = None
        self.base_embed : discord.Embed =discord.Embed(title="Code Output", description="CODE HERE", color=0xecc98e)
        self.base_embed.set_footer(text="Powered by Piston: https://github.com/engineer-man/piston. 4096 Character Output Limit!")
        self.title_limit = 256
        self.output_limit = 4096 # 4096 character max output
        self.file_limit = 2097152 # 2MiB file limit
    
    """
    This function is used to initialize anything that requires an async operation
    """
    async def _initialize_async_items(self):
        self.languages = list(await self.engine.get_languages())
        self.languages.sort()

    def _language_options(self, current):
        choices = [
            app_commands.Choice(name=language.title(), value=language)
            for language in self.languages
            if current.lower() in language.lower()
        ]
        
        return choices if len(choices) <= 25 else choices[:25]

    """
    Validates the contents of the file
    """
    def _validate_file(self, file : discord.Attachment) -> Optional[str]:
        if file.size > self.file_limit:
            return f"Exceeded {self.file_limit // 1024**2}MiB file limit!"
        elif "text" not in file.content_type:
            return f"Not a text file!"
    
    """
    This function will execute the given code in a TextIOWrapper and return an Embed with the output in a tuple.
    If the function succeeded, the tuple will have its first argument be True, False otherwise. This is similar to 
    a Rust Result<T, E> type.
    """
    async def _execute(self, language : str, filename : str, arguments : str, code : TextIOWrapper) -> Tuple[bool, discord.Embed]:
        output : Output = await self.engine.execute(
            language=language,
            file=code,
            args=arguments.split(" ") if arguments else []
        )

        embed = self.base_embed.copy()
        embed.title = f"{filename} Output"[:self.title_limit]

        error = self.engine.validate_output(output)
        if error:
            embed.description = error[:self.output_limit]
            return (False, embed)
        
        embed.description = output.run_stage.output[:self.output_limit]
        return (True, embed)

    @app_commands.describe(language="The programming language you want to use! There are more than 25 available, so let autocomplete show you them all.", file="The file you wish to upload and run code with. UTF-8 Only.", arguments="Space separated list of command line arguments you want to pass.")
    @app_commands.command(name="file", description="Run code in a provided file.")
    async def _execute_file(self, interaction : discord.Interaction, language : str, file : discord.Attachment, arguments : Optional[str]):
        await interaction.response.defer()

        validation_result = self._validate_file(file)
        if validation_result:
            await interaction.followup.send(validation_result, ephemeral=True)
            return
        
        code : TextIOWrapper = TextIOWrapper(BytesIO(await file.read()), encoding="utf-8")
        _, embed = await self._execute(language, file.filename, arguments, code)

        await interaction.followup.send(embed=embed, ephemeral=False)
    
    @app_commands.command(name="script", description="Write a snippet of code to run.")
    async def _execute_script(self, interaction : discord.Interaction, language : str):
        # partial() is used here to autofill the first argument of the function, which is self.
        await interaction.response.send_modal(CodeEditorModal(language=language, execute_func=partial(self._execute)))
    
    @_execute_file.autocomplete(name="language")
    @_execute_script.autocomplete(name="language")
    async def _execute_file_autocomplete(self, interaction : discord.Interaction, current : str):
        return self._language_options(current)

class CodeEditorModal(discord.ui.Modal, title="Write a Script!"):
    def __init__(self, 
                 language,
                 execute_func : Callable[[Execute, str, str, str, TextIOWrapper], Tuple[bool, discord.Embed]] 
        ):
        super().__init__()
        self.language = language
        self._execute_func = execute_func
        self.logger = logging.getLogger(__name__)
        self.title = f"Write a script in {self.language}!"
    
    script_name = discord.ui.TextInput(
        label="Enter the name of the script [Optional].",
        placeholder="Script name",
        max_length=240,
        required=False
    )

    arguments = discord.ui.TextInput(
        label="Command Line Arguments [Optional].",
        placeholder="Space separated command line arguments...",
        required=False
    )

    script = discord.ui.TextInput(
        label="Write your code below!",
        placeholder="Code...",
        required=True,
        style=discord.TextStyle.paragraph
    )

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        self.logger.warning("An exception occured: %s\n", error)
        await interaction.response.send_message(f'Oops! Something went wrong!', ephemeral=True)
    
    async def on_submit(self, interaction: discord.Interaction):
        script_title = self.script_name.value if self.script_name.value else f"{interaction.user.name}'s Script"
        code = TextIOWrapper(BytesIO(self.script.value.encode("utf-8")), encoding="utf-8")
        args = self.arguments.value

        # No special validation needed here.
        result, embed = await self._execute_func(self.language, script_title, args, code)

        if not result:
            await interaction.response.send_message(embed=embed, ephemeral=True)
            self.stop()
            return
        
        await interaction.response.send_message(embed=embed)


async def setup(bot : commands.Bot):
    cog = Execute(bot)
    await cog._initialize_async_items()
    await bot.add_cog(cog)