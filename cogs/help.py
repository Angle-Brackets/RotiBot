import discord
import json
import typing

from discord.ext import commands
from discord import app_commands
from data import calculate_uptime
from enum import Enum

"""
Contains all of the help information for every command, loaded on start-up.
"""
help_information = None
changelog = None

#Loads all the help and changelog data.
with open("help_information.json") as file:
    data = file.read()
    help_information = json.loads(data)
    file.close()

with open("changelog") as file:
    data = file.read()
    changelog = json.loads(data)
    file.close()

# Generates all of the embeds for the help function...yeah sorry for the clutter, I wanted to have somewhat compressed code because most of it is string stuff.
def _generate_help_embed(command = None):
    all_embeds = dict() #This will be a dictionary of the embeds to return, keyed by Command and the Value being all of its information in an embed.

    def _generate_pages(command_page = None):

        #This will generate the main page embed, listing all the categories of commands.
        if command_page is None:
            embed = discord.Embed(title="Roti's Commands", description="Choose a category from the dropdown below", color=0xecc98e)
            embed.add_field(name="General Information", value="Uptime: ``{0}``\nRoti currently has ``{1}`` categories available, with a total of ``{2}`` commands available!".format(calculate_uptime(), len(help_information), sum(len(value["commands"]) for key, value in help_information.items())), inline=False)
            embed.add_field(name="Categories", value="\n".join("``/help " + category + "`` | " + category + " " + str(help_information[category]["emoji"]) for category in help_information.keys()), inline=False)
            embed.add_field(name="Additional Information", value="By Soupa#0524 | [Github](https://github.com/Angle-Brackets/RotiBot)")
            return embed

        # This generates the main page that houses all of the sub-commands.
        landing_embed = discord.Embed(title=command_page["title"], description=command_page["description"], color=0xecc98e)
        landing_embed.add_field(name=":bookmark: Commands", value="```" + "\t".join(command_page["commands"].keys()) + "```")
        all_embeds["landing"] = landing_embed

        # Now to generate all the command embeds.
        for command, info in command_page["commands"].items():
            embed = discord.Embed(title="Help for " + ("/" + command_page["command_base"] + " " + command if command_page["command_base"] != "None" else "/" + command), description=info["description"], color=0xecc98e)
            embed.add_field(name=":question: Usage", value="``" + info["usage"] + "``", inline=False)

            if info["arguments"] != "None":
                embed.add_field(name="\n:pencil2: Arguments", value="\n\n".join("**" + arg.capitalize() + "**" + ": " + arg_desc for arg, arg_desc in info["arguments"].items()), inline=False)
            embed.set_footer(text="Syntax: [Required], <Optional>, (Extra Information)")
            all_embeds[command] = embed

        return all_embeds

    # If a page is selected that is valid, it will display all the help information for that page.
    if command is not None:
        return _generate_pages(help_information[command])
    else:
        return _generate_pages()

def _generate_changelog_embed():
    embed = discord.Embed(title="Changelog for Roti " + changelog["version"], description=changelog["summary"], color=0xecc98e)

    count = 1
    for change_title, change in changelog["changes"].items():
        embed.add_field(name=f"{count}. " + change_title, value=change, inline=False)
        count += 1

    return embed

class Help(commands.Cog):
    def __init__(self, bot : commands.bot):
        super().__init__()
        self.bot = bot

    """
    This command is a global command for listing all of the help information.
    """
    @app_commands.command(name="help", description="Displays the help listing for all commands.")
    async def _help(self, interaction : discord.Interaction, command : typing.Optional[Enum("Command", list(help_information.keys()))]):
        await interaction.response.defer()
        view = HelpNav(command.name.replace("Command.", "").strip() if command is not None else None)

        embed = None
        if command is None:
            embed = _generate_help_embed()
        else:
            embed = _generate_help_embed(view.page)["landing"]

        view.message = await interaction.followup.send(embed=embed, view=view)
        view.message = await interaction.original_message() # Needed to delete the message when it times out

        await view.wait()

    @app_commands.command(name="changelog", description="Displays the latest changes to Roti!")
    async def _changelog(self, interaction : discord.Interaction):
        await interaction.response.send_message(embed=_generate_changelog_embed())

#Generates the options for the view object
#If the page is None, generates the general page that lists all of the categories, otherwise will generate category-specific choices.
def _generate_options(page = None):
    select_list = list()
    if page is None:
        for key in help_information.keys():
            desc = help_information[key]["description"]
            try:
                desc = help_information[key]["description"][0:help_information[key]["description"].index("\n")]
            except:
                desc = help_information[key]["description"]
            select_list.append(discord.SelectOption(label=key, description=desc))
    else:
        for cmd, info in help_information[page]["commands"].items():
            select_list.append(discord.SelectOption(label="/" + help_information[page]["command_base"] + " " + cmd if help_information[page]["command_base"] != "None" else cmd, description=info["description"][0:97] + "..." if len(info["description"]) > 100 else info["description"]))

    return select_list

class HelpNav(discord.ui.View):
    def __init__(self, page):
        super().__init__()
        self.timeout = 60
        self.page = page
        if self.page is not None:
            self._main_select_panel.options = _generate_options(self.page)
        else:
            self._main_select_panel.options = _generate_options()

    @discord.ui.select(min_values=1, options=[], placeholder="Select a Category")
    async def _main_select_panel(self, interaction : discord.Interaction, selection : discord.ui.Select):
        #This generates the general landing page that lists all of the categories
        if self.page is None:
            embeds = _generate_help_embed(selection.values[0])
            self.page = selection.values[0]
            self._main_select_panel.options = _generate_options(self.page)
            self._main_select_panel.placeholder = "Select a Command"
            await interaction.response.edit_message(embed=embeds["landing"], view=self)
        #This generates the correct set of embeds for a particular category. A lot of the string manipulation is to remove styling so I can index a dictionary.
        else:
            cmd = selection.values[0][selection.values[0].find(" "):].strip() if selection.values[0].find(" ") != -1 else selection.values[0]
            embeds = _generate_help_embed(self.page)
            await interaction.response.edit_message(embed=embeds[cmd], view=self)


    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.danger)
    async def _cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.message.delete()
        self.stop()


    async def on_timeout(self) -> None:
        await self.message.delete()
        self.stop()

async def setup(bot : commands.Bot):
    await bot.add_cog(Help(bot))