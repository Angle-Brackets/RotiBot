import discord
import json
import os
import logging

from dataclasses import dataclass
from typing import Optional, List, Dict
from database.bot_state import RotiState
from discord.ext import commands
from discord import app_commands
from utils.RotiUtilities import cog_command

# Help Information JSON Format
@dataclass(frozen=True)
class CommandArgument:
    name: str
    description: str

@dataclass(frozen=True)
class Command:
    name: str
    description: str
    usage: str
    arguments: Dict[str, CommandArgument]  # Maps argument name to its description

@dataclass(frozen=True)
class Category:
    name: str
    title: str
    description: str
    command_base: str
    emoji: str
    commands: Dict[str, Command]  # Maps command names to Command objects

@dataclass
class HelpInformation:
    categories: Dict[str, Category]  # Maps category name (e.g., "Talkbacks") to Category objects

@cog_command
class Help(commands.Cog):
    def __init__(self, bot : commands.bot):
        super().__init__()
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.help_information : HelpInformation = None
        self.changelog = None
        self._current_dir = os.path.dirname(os.path.abspath(__file__))
        
        # Load help information and changelog data.
        with open(file=os.path.join(self._current_dir, "help_information.json"), mode="r") as file:
            self.help_information = self._create_help_information(json.loads(file.read()))

        with open(os.path.join(self._current_dir, "changelog.json"), mode="r") as file:
            self.changelog = json.loads(file.read())

        self.old_changelog = []
        try:
            with open(os.path.join(self._current_dir, "old_changelog.json"), mode="r") as file:
                self.old_changelog = json.loads(file.read())
        except FileNotFoundError:
            self.logger.warning("old_changelog.json not found.")

    """
    This command is a global command for listing all of the help information.
    """
    @app_commands.command(name="help", description="Displays the help listing for all commands.")
    async def _help(self, interaction: discord.Interaction, category: Optional[str]):
        await interaction.response.defer()
        command_page = self.help_information.categories[category] if category else None
        view = HelpNav(self.help_information, command_page)

        embed = None
        if not category:
            embed = Help._generate_help_embed(self.help_information)
        else:
            embed = Help._generate_help_embed(self.help_information, view.page.name)["landing"]

        view.message = await interaction.followup.send(embed=embed, view=view)
        view.message = await interaction.original_response()

        await view.wait()

    @app_commands.command(name="changelog", description="Displays the latest changes to Roti!")
    async def _changelog(self, interaction : discord.Interaction):
        # Combine current and old changelogs for the view
        all_changelogs = [self.changelog] + self.old_changelog
        view = ChangelogNav(all_changelogs)
        await interaction.response.send_message(embed=self._generate_changelog_embed(self.changelog), view=view, ephemeral=True, delete_after=60)
        view.message = await interaction.original_response()
    
    @_help.autocomplete("category")
    async def _help_autocomplete(self, interaction : discord.Interaction, current : str) -> List[app_commands.Choice]:
        commands = []
        try:
            commands = [
                app_commands.Choice(name=command, value=command)
                for command in self.help_information.categories
                if current.lower() in command.lower()
            ]
        except:
            pass # Ignore exceptions, they're a result of discord requiring 3 second responses, even though it doesn't matter here.

        return commands[:25] # Only 25 options at max!
    
    @staticmethod
    def _generate_help_embed(help_information: HelpInformation, command: Optional[str] = None):
        all_embeds = {}  # Dictionary of embeds keyed by Command with their information

        def _generate_pages(command_page: Optional[Category] = None):
            if not command_page:
                total_categories = len(help_information.categories)
                total_commands = sum(len(category.commands) for category in help_information.categories.values())

                embed = discord.Embed(
                    title="Roti's Commands",
                    description="Choose a category from the dropdown below",
                    color=0xecc98e
                )

                embed.add_field(
                    name="General Information",
                    value=f"Uptime: ``{RotiState.calculate_uptime()}``\nRoti currently has ``{total_categories}`` categories available, "
                        f"with a total of ``{total_commands}`` commands available!",
                    inline=False
                )

                embed.add_field(
                    name="Categories",
                    value="\n".join(
                        f"``/help {category_name}`` | {category_name} {category.emoji}"
                        for category_name, category in help_information.categories.items()
                    ),
                    inline=False
                )

                embed.add_field(
                    name="Additional Information",
                    value="By @soupa. | [Github](https://github.com/Angle-Brackets/RotiBot)"
                )

                return embed

            # Generate the main page with sub-commands
            landing_embed = discord.Embed(
                title=command_page.title,
                description=command_page.description,
                color=0xecc98e
            )

            landing_embed.add_field(
                name=":bookmark: Commands",
                value="```" + "\t".join(command_page.commands.keys()) + "```"
            )

            all_embeds["landing"] = landing_embed

            # Generate all command-specific embeds
            for command_name, command_info in command_page.commands.items():
                embed = discord.Embed(
                    title=f"Help for /{command_page.command_base} {command_name}"
                    if command_page.command_base != "None"
                    else f"Help for /{command_name}",
                    description=command_info.description,
                    color=0xecc98e
                )

                embed.add_field(
                    name=":question: Usage",
                    value=f"``{command_info.usage}``",
                    inline=False
                )

                if command_info.arguments:
                    embed.add_field(
                        name="\n:pencil2: Arguments",
                        value="\n\n".join(
                            f"**{arg.capitalize()}**: {arg_desc.description}"
                            for arg, arg_desc in command_info.arguments.items()
                        ),
                        inline=False
                    )
                else:
                    embed.add_field(
                        name="\n:pencil2: Arguments",
                        value="None",
                        inline=False
                    )

                embed.set_footer(text="Syntax: [Required], <Optional>, (Extra Information)")
                all_embeds[command_name] = embed

            return all_embeds

        if command:
            return _generate_pages(help_information.categories[command])
        return _generate_pages()


    @staticmethod
    def _generate_changelog_embed(entry):
        embed = discord.Embed(title="Changelog for Roti " + entry["version"], description=entry["summary"], color=0xecc98e)

        count = 1
        for change_title, change in entry["changes"].items():
            embed.add_field(name=f"{count}. " + change_title, value=change, inline=False)
            count += 1

        return embed

    def _create_help_information(self, source_data):
        return HelpInformation(categories=Help._parse_categories(source_data))

    # Helper functions to convert to a HelpInformation container object
    # Use create_help_information to actually construct an instance of HelpInformation directly.
    @staticmethod
    def _parse_arguments(arguments_dict):
        return {arg: CommandArgument(name=arg, description=desc) for arg, desc in arguments_dict.items()}

    @staticmethod
    def _parse_commands(commands_dict):
        return {cmd: Command(name=cmd,
                            description=cmd_info["description"],
                            usage=cmd_info["usage"],
                            arguments=Help._parse_arguments(cmd_info.get("arguments", {})))
                for cmd, cmd_info in commands_dict.items()}

    @staticmethod
    def _parse_categories(categories_dict):
        return {cat: Category(name=cat, 
                            title=cat_info["title"],
                            description=cat_info["description"],
                            command_base=cat_info["command_base"],
                            emoji=cat_info["emoji"],
                            commands=Help._parse_commands(cat_info["commands"]))
                for cat, cat_info in categories_dict.items()}

class HelpNav(discord.ui.View):
    def __init__(self, help_information: HelpInformation, command_page: Optional[Category] = None):
        super().__init__()
        self.timeout = 60
        self.page = command_page
        self.help_information = help_information

        if self.page is not None:
            self._main_select_panel.options = self._generate_options(self.help_information, self.page)
        else:
            self._main_select_panel.options = self._generate_options(self.help_information)

    @discord.ui.select(min_values=1, options=[], placeholder="Select a Category")
    async def _main_select_panel(self, interaction: discord.Interaction, selection: discord.ui.Select):
        # This generates the general landing page that lists all categories
        if self.page is None:
            selected_category = selection.values[0]
            embeds = Help._generate_help_embed(self.help_information, selected_category)
            self.page = self.help_information.categories[selected_category]
            self._main_select_panel.options = self._generate_options(self.help_information, self.page)
            self._main_select_panel.placeholder = "Select a Command"
            await interaction.response.edit_message(embed=embeds["landing"], view=self)
        else:
            selected_command = selection.values[0].split(" ", 1)[-1] if " " in selection.values[0] else selection.values[0]
            embeds = Help._generate_help_embed(self.help_information, self.page.name)
            await interaction.response.edit_message(embed=embeds[selected_command], view=self)

    def _generate_options(self, help_information: HelpInformation, page: Optional[Category] = None):
        """
        Generates the options for the view object.
        If the page is None, generates the general page that lists all categories, 
        otherwise will generate category-specific choices.
        """
        select_list = []

        if not page:
            for category_name, category in help_information.categories.items():
                description = category.description.split("\n", 1)[0] if "\n" in category.description else category.description
                select_list.append(discord.SelectOption(label=category_name, description=description))
        else:
            for command_name, command_info in page.commands.items():
                label = f"/{page.command_base} {command_name}" if page.command_base != "None" else command_name
                description = command_info.description[:97] + "..." if len(command_info.description) > 100 else command_info.description
                select_list.append(discord.SelectOption(label=label, description=description))

        return select_list

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.danger)
    async def _cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.message.delete()
        self.stop()


    async def on_timeout(self) -> None:
        await self.message.delete()
        self.stop()

class ChangelogNav(discord.ui.View):
    def __init__(self, changelogs: List[Dict]):
        super().__init__(timeout=60)
        self.changelogs = changelogs
        self.current_index = 0
        self.message: Optional[discord.Message] = None

        # Update button states initially
        self._update_buttons()

    def _update_buttons(self):
        # Disable "Newer" if we are at the newest (index 0)
        # Note: If there's only 1 page, both are disabled
        self._newer.disabled = (self.current_index == 0)
        # Disable "Older" if we are at the oldest (index len-1)
        self._older.disabled = (self.current_index == len(self.changelogs) - 1)

    async def _update_message(self, interaction: discord.Interaction):
        self._update_buttons()
        embed = Help._generate_changelog_embed(self.changelogs[self.current_index])
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label='Newer', style=discord.ButtonStyle.primary)
    async def _newer(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_index > 0:
            self.current_index -= 1
            await self._update_message(interaction)
        else:
            await interaction.response.defer()

    @discord.ui.button(label='Older', style=discord.ButtonStyle.primary)
    async def _older(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_index < len(self.changelogs) - 1:
            self.current_index += 1
            await self._update_message(interaction)
        else:
            await interaction.response.defer()
            
    async def on_timeout(self) -> None:
        try:
            if self.message: await self.message.delete()
        except: pass
        self.stop()

async def setup(bot : commands.Bot):
    await bot.add_cog(Help(bot))