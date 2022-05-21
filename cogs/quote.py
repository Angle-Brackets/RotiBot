import typing
import discord
import random
import data
import re

from discord import app_commands
from discord.ext import commands
from data import db

#This is a reference for the quote structure that is stored in the array.
QUOTE_STRUCTURE = {
    "quote": str, #Quote
    "default": str, #This is the default quote associated with a replaceable quote.
    "name": str, #Name of who said the quote
    "replaceable": bool, #If the quote has replaceable portions
    "has_original": bool #Only toggleable for replaceable quotes, flag to state whether the quote has an ORIGINAL copy. (used for /quote random)
}

def build_quote(quote_obj : dict):
    if quote_obj["name"] == "None":
        return quote_obj["default"]
    else:
        return quote_obj["default"] + "\n-{0}".format(quote_obj["name"])

class Quote(commands.GroupCog, group_name="quote"):
    def __init__(self, bot : commands.Bot):
        super().__init__()
        self.bot = bot

    add_group = app_commands.Group(name="add", description="Creates a new quote")

    @app_commands.describe(quote="The new quote to be added.", name="An optional argument that will add the name of who said the quote.")
    @add_group.command(name="nonreplaceable", description="Creates a new quote that has NO replaceable portions.")
    async def _quote_add_nonrep(self, interaction : discord.Interaction, quote : str, name : typing.Optional[str]):
        await interaction.response.defer()
        new_quote = QUOTE_STRUCTURE.copy()
        new_quote["quote"] = quote
        new_quote["default"] = quote
        new_quote["name"] = name if name is not None else "None"
        new_quote["replaceable"] = False
        new_quote["has_original"] = True #Always true for non-replaceable quotes.

        db[interaction.guild_id]["quotes"].append(new_quote)
        data.push_data(interaction.guild_id, "quotes")
        await interaction.followup.send("Successfully added new quote.")

    @add_group.command(name="replaceable", description="Creates a new quote that has replaceable portions.")
    async def _quote_add_rep(self, interaction : discord.Interaction):
        await interaction.response.send_modal(Quote_Modal())

    @app_commands.command(name="random", description="Displays a random quote.")
    async def _quote_random(self, interaction : discord.Interaction):
        await interaction.response.defer()
        if len(db[interaction.guild_id]["quotes"]) > 0:
            await interaction.followup.send(build_quote(random.choice(list(filter(lambda x : x["has_original"], db[interaction.guild_id]["quotes"])))))
        else:
            await interaction.followup.send("No quotes found! Add a quote using /quote add!")

    @app_commands.describe(show_defaultless="Toggle to change whether quotes without defaults are displayed, by default they are NOT displayed.")
    @app_commands.command(name="list", description="Displays all of the quotes present in the server.")
    async def _quote_get_all(self, interaction : discord.Interaction, show_defaultless : typing.Optional[bool]):
        await interaction.response.defer()
        all_embeds = list()
        show_defaultless = show_defaultless if show_defaultless is not None else False
        quotes = list(filter(lambda x: x["has_original"], db[interaction.guild_id]["quotes"])) if not show_defaultless else db[interaction.guild_id]["quotes"]
        embed_base = discord.Embed(title=f"List of all Quotes in {interaction.guild.name}", description="Use the buttons below to navigate between pages.", color=0xecc98e)

        split_list = [quotes[x:x + 25] for x in range(0, len(quotes), 25)] #Splits into sections of length 25, as 25 fields are allowed per embed

        #Generates all of the embeds tha will display the quotes
        count = 1
        current_page = 1
        for arr in split_list:
            new_embed = embed_base.copy()
            for quote_obj in arr:
                #If show_defaultless is true, then this always runs basically.
                if quote_obj["has_original"] or show_defaultless:
                    quote_to_display = str
                    if quote_obj["has_original"]:
                        quote_to_display = quote_obj["default"] #Will display the default original quote
                    elif show_defaultless:
                        quote_to_display = quote_obj["quote"] #Otherwise will just grab the quote with the replaceable portions if show_defaultless is true

                    new_embed.add_field(name="[{0}]. A Quote by {1}".format(count, quote_obj["name"] if quote_obj["name"] != "None" else "???"), value=quote_to_display[0:150] + "..." if len(quote_to_display) > 150 else quote_to_display, inline=False)
                    new_embed.set_footer(text=f"Page {current_page}/{len(split_list)}")
                    count += 1
            all_embeds.append(new_embed)
            current_page += 1

        view = Navigation(len(all_embeds), all_embeds)
        view.message = await interaction.followup.send(embed=all_embeds[0], view=view)
        view.message = await interaction.original_message()

        await view.wait()

    @app_commands.command(name="remove", )

class Quote_Modal(discord.ui.Modal, title = "Make a new Replaceable Quote!"):
    def __init__(self):
        super().__init__()
        self.timeout = 60

    quote = discord.ui.TextInput(
        label = "New Quote, add replaceable portions w/ {INT}.",
        placeholder = "Enter your quote here...",
        max_length=1950,
        required = True
    )

    default = discord.ui.TextInput(
        label = "Same quote, but w/ no replaceable portions.",
        placeholder = "Optionally enter default quote here...",
        max_length=1950,
        required = False
    )

    name = discord.ui.TextInput(
        label = "Who said this quote?",
        placeholder = "Optionally include who said this quote...",
        max_length=50,
        required = False
    )

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.response.send_message('Oops! Something went wrong.', ephemeral=True)

    async def on_submit(self, interaction: discord.Interaction):
        replace_tokens = re.findall("{[0-9]{1}}", self.quote.value)
        if len(replace_tokens) <= 0:
            await interaction.response.send_message("Failed to add new quote: your quote lacks any replaceable portions! Add a replaceable portion in your quote by inserting {#} anywhere in your quote, where the # is a digit from 0-9. If you do not want any replaceable portions, use /quote add nonreplaceable!")
            return
        else:
            new_quote = QUOTE_STRUCTURE.copy()
            new_quote["quote"] = self.quote.value
            new_quote["name"] = self.name.value if len(self.name.value) > 0  else "None"
            new_quote["replaceable"] = True
            new_quote["has_original"] = True if len(self.default.value) > 0 else False
            new_quote["default"] = self.default.value if new_quote["has_original"] else "None"

            db[interaction.guild_id]["quotes"].append(new_quote)
            data.push_data(interaction.guild_id, "quotes")
            await interaction.response.send_message("Successfully added new quote.")

class Navigation(discord.ui.View):
    def __init__(self, pages, embeds):
        super().__init__()
        self.timeout = 60
        self.pages = pages
        self.current_page = 1  # Subtract 1 for indexing.
        self.embeds = embeds

        if self.pages == 1:
            self.remove_item(self._back)
            self.remove_item(self._next)

    async def on_timeout(self) -> None:
        await self.message.delete()
        self.stop()

    @discord.ui.button(label='Back', style=discord.ButtonStyle.primary)
    async def _back(self, interaction : discord.Interaction, button : discord.ui.Button):
        if self.current_page > 1:
            self.current_page -= 1
            await interaction.response.edit_message(embed=self.embeds[self.current_page - 1], view=self)

    @discord.ui.button(label='Next', style=discord.ButtonStyle.primary)
    async def _next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page is not self.pages:
            self.current_page += 1
            await interaction.response.edit_message(embed=self.embeds[self.current_page - 1], view=self)

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.danger)
    async def _cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.message.delete()
        self.stop()



async def setup(bot: commands.Bot):
    await bot.add_cog(Quote(bot))
