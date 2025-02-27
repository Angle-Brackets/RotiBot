import typing
import discord
import random
import database.data as data
import re

from discord import app_commands
from discord.ext import commands
from database.data import RotiDatabase
from utils.command_utils import cog_command

#This is a reference for the quote structure that is stored in the array.
QUOTE_STRUCTURE = {
    "quote": str, #Quote
    "default": str, #This is the default quote associated with a replaceable quote. "None" if undefined.
    "tag": str, #This is the tag/shorthand used for /quote say, this is UNIQUE to every quote.
    "name": str, #Name of who said the quote
    "replaceable": bool, #If the quote has replaceable portions
    "has_original": bool #Only toggleable for replaceable quotes, flag to state whether the quote has an ORIGINAL copy. (used for /quote random)
}

def build_quote(quote_obj : dict):
    if quote_obj["name"] == "None":
        return quote_obj["default"]
    else:
        return quote_obj["default"] + f"\n-{quote_obj["name"]}"

@cog_command
class Quote(commands.GroupCog, group_name="quote"):
    def __init__(self, bot : commands.Bot):
        super().__init__()
        self.bot = bot
        self.db = RotiDatabase()

    add_group = app_commands.Group(name="add", description="Creates a new quote")

    @app_commands.describe(quote="The new quote to be added.", tag="A unique identifier that can be used to find this quote again.", name="An optional argument that will add the name of who said the quote.")
    @add_group.command(name="nonreplaceable", description="Creates a new quote that has NO replaceable portions.")
    async def _quote_add_nonrep(self, interaction : discord.Interaction, quote : str, tag : str, name : typing.Optional[str]):
        await interaction.response.defer()

        if len(tag) > 128:
            await interaction.followup.send("Provided tag exceeds max length of 128 characters, shorten it and try again!")
            return

        quotes = self.db[interaction.guild_id, "quotes"].unwrap()
        for quote_obj in quotes:
            if quote_obj["tag"] == tag:
                await interaction.followup.send(f"Failed to add new quote, duplicate tag detected with quote: {quote_obj["default"] if quote_obj["has_original"] else quote_obj["quote"]}!")
                return

        new_quote = QUOTE_STRUCTURE.copy()
        new_quote["quote"] = quote
        new_quote["default"] = quote
        new_quote["tag"] = tag
        new_quote["name"] = name if name is not None else "None"
        new_quote["replaceable"] = False
        new_quote["has_original"] = True #Always true for non-replaceable quotes.

        quotes.append(new_quote)
        self.db[interaction.guild_id, "quotes"] = quotes
        await interaction.followup.send("Successfully added new quote.")

    @add_group.command(name="replaceable", description="Creates a new quote that has replaceable portions.")
    async def _quote_add_rep(self, interaction : discord.Interaction):
        await interaction.response.send_modal(Quote_Modal(self.db))

    @app_commands.command(name="random", description="Displays a random quote.")
    async def _quote_random(self, interaction : discord.Interaction):
        await interaction.response.defer()

        quotes = self.db[interaction.guild_id, "quotes"].unwrap()
        if quotes:
            await interaction.followup.send(build_quote(random.choice(list(filter(lambda x : x["has_original"], quotes)))))
        else:
            await interaction.followup.send("No quotes found! Add a quote using /quote add!")

    @app_commands.describe(query="A search query that can be a tag, name, or substring of the quote.", show_defaultless="Toggle to change whether quotes without defaults are displayed, by default they are NOT displayed.")
    @app_commands.command(name="list", description="Displays all of the quotes present in the server.")
    async def _quote_list(self, interaction : discord.Interaction, query: typing.Optional[str], show_defaultless : typing.Optional[bool]):
        await interaction.response.defer()

        quotes = self.db[interaction.guild_id, "quotes"].unwrap()
        if not quotes:
            await interaction.followup.send("No quotes found! Add a quote using /quote add!")
            return

        all_embeds = list()
        show_defaultless = show_defaultless if show_defaultless is not None else False
        quotes = list(filter(lambda x: x["has_original"], quotes)) if not show_defaultless else quotes
        quotes = quotes if query is None else list(filter(lambda x: query.casefold() in x["quote"].casefold() or query.casefold() in x["default"] if x["default"] != "None" else False or query.casefold() in x["tag"].casefold() or query.casefold() in x["name"].casefold(), quotes))

        embed_base = discord.Embed(title=f"List of all Quotes in {interaction.guild.name}", description="Use the buttons below to navigate between pages.", color=0xecc98e)
        split_list = [quotes[x:x + 25] for x in range(0, len(quotes), 25)] #Splits into sections of length 25, as 25 fields are allowed per embed

        if not quotes:
            await interaction.followup.send("No quotes found! Try a different query or parameter!", ephemeral=True)
            return

        #Generates all of the embeds that will display the quotes
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

                    quote_sayer = f"[{count}]. A Quote by {quote_obj["name"] if quote_obj[ "name"] != "None" else "???"}"
                    new_embed.add_field(name=(quote_sayer if len(quote_sayer) < 128 else quote_sayer[0:125] + "...") + f"\nTag: {quote_obj["tag"] if len(quote_obj["tag"]) < 128 else quote_obj["tag"][0:125] + "..."} {"🔓" if quote_obj["replaceable"] else "🔒"}",value=quote_to_display[0:147] + "..." if len(quote_to_display) > 150 else quote_to_display,inline=False)
                    new_embed.set_footer(text=f"Page {current_page}/{len(split_list)}\nSyntax: 🔒 - Nonreplaceable, 🔓 - Replaceable")
                    count += 1
            all_embeds.append(new_embed)
            current_page += 1

        view = Navigation(self.db, len(all_embeds), all_embeds, False)
        view.message = await interaction.followup.send(embed=all_embeds[0], view=view)
        view.message = await interaction.original_response()

        await view.wait()

    @app_commands.describe(query="A keyword to help search for a particular quote, matches against the name, tag, and actual quote itself.")
    @app_commands.command(name="remove", description="Remove a specific quote")
    async def _quote_remove(self, interaction : discord.Interaction, query : typing.Optional[str]):
        await interaction.response.defer()

        quotes = self.db[interaction.guild_id, "quotes"].unwrap()
        if not quotes:
            await interaction.followup.send("No quotes found! Add a quote using /quote add!")
            return

        all_embeds = list()
        query = query.casefold() if query is not None else ""
        quotes = list(filter(lambda x : query in x["default"].casefold() or query in x["name"].casefold() or query in x["tag"].casefold() if x["has_original"] else x["quote"].casefold() or query in x["name"].casefold() or query in x["tag"].casefold(), quotes)) #Gets every quote
        embed_base = discord.Embed(title=f"List of all quotes found in {interaction.guild.name}" if query == "" else f"List of all quotes found with keyword {query} in {interaction.guild.name}", description="Use the buttons below to navigate between pages.", color=0xecc98e)
        split_list = [quotes[x:x + 25] for x in range(0, len(quotes), 25)] #Splits into sections of length 25, as 25 fields are allowed per embed

        #Nothing matched the query
        if not quotes:
            await interaction.followup.send(f"No matches found with query: {query}.")
            return

        # Generates all of the embeds tha will display the quotes
        count = 1
        current_page = 1
        for arr in split_list:
            new_embed = embed_base.copy()
            for quote_obj in arr:
                quote_to_display = quote_obj["default"] if quote_obj["has_original"] else quote_obj["quote"]
                # If show_defaultless is true, then this always runs basically.
                quote_sayer = f"[{count}]. A Quote by {quote_obj["name"] if quote_obj["name"] != "None" else "???"}"
                new_embed.add_field(name=(quote_sayer if len(quote_sayer) < 128 else quote_sayer[0:125] + "...") + f"\nTag: {quote_obj["tag"] if len(quote_obj["tag"]) < 128 else quote_obj["tag"][0:125] + "..."}", value=quote_to_display[0:147] + "..." if len(quote_to_display) > 150 else quote_to_display, inline=False)
                new_embed.set_footer(text=f"Page {current_page}/{len(split_list)}")
                count += 1
            all_embeds.append(new_embed)
            current_page += 1

        view = Navigation(self.db, len(all_embeds), all_embeds, True)
        view.message = await interaction.followup.send(embed=all_embeds[0], view=view)
        view.message = await interaction.original_response()

        await view.wait()

    @app_commands.describe(tag="The tag of the quote you would like to say.", type="The type of quote that you would like to say. If nonreplaceable is chosen for a replaceable quote, it will attempt to display the default quote.")
    @app_commands.command(name="say", description="Say a specific quote")
    async def _say(self, interaction : discord.Interaction, tag: str, type : typing.Literal["Replaceable", "Nonreplaceable"]):
        quote = None
        quotes = self.db[interaction.guild_id, "quotes"].unwrap()
        for q in quotes:
            if q["tag"].casefold() == tag:
                quote = q
                break

        #We first check if the quote is nonreplaceable, if it is, Roti will just say it.
        if type == "Nonreplaceable":
            #Need to verify that the quote has a default
            if quote["default"] == "None":
                await interaction.response.send_message("No default quote exists for this tag, try again with a different quote!", ephemeral=True)
                return
            await interaction.response.send_message(quote["default"])
            return

        #If the quote is replaceable, Roti will auto generate a custom modal with the necessary fields to edit.
        if type == "Replaceable":
            if not quote["replaceable"]:
                if quote["has_original"]:
                    await interaction.response.send_message(quote["default"])
                else:
                    await interaction.response.send_message("This quote isn't replaceable, try again with a different quote!", ephemeral=True)
                    return
            # We need to figure out how many fields there are.
            unique_tokens = set(re.findall("{[0-3]{1}}", quote["quote"]))
            await interaction.response.send_modal(Say_Replacement_Modal(quote, unique_tokens))


    @_say.autocomplete("tag")
    async def _tag_autocomplete(self, interaction: discord.Interaction, current: str):
        # Only includes first 25 to avoid a crash
        # TODO: Might add an autocomplete for the type field, using interaction.namespace.tag to get the current typed tag.
        return [app_commands.Choice(name=quote["tag"], value=quote["tag"]) for quote in
                self.db[interaction.guild_id, "quotes"].unwrap() if current.casefold() in quote["tag"].casefold()][0:25]

class Quote_Modal(discord.ui.Modal, title = "Make a new Replaceable Quote!"):
    def __init__(self, db : RotiDatabase):
        super().__init__()
        self.timeout = 60
        self.db = db

    quote = discord.ui.TextInput(
        label = "New Quote, add replaceable portions w/ {INT}.",
        placeholder = "Enter your quote here with replaceable portions {0-3}...",
        max_length= 1950,
        required = True
    )

    tag = discord.ui.TextInput(
        label = "Enter the tag associated with this quote",
        placeholder = "Enter your unique tag here...",
        max_length=128,
        required = True
    )

    default = discord.ui.TextInput(
        label = "Same quote, but w/ no replaceable portions.",
        placeholder = "Optionally enter default quote here...",
        max_length= 1950,
        required = False
    )

    name = discord.ui.TextInput(
        label = "Who said this quote?",
        placeholder = "Optionally include who said this quote...",
        max_length = 50,
        required = False
    )

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.response.send_message('Oops! Something went wrong.', ephemeral=True)

    async def on_submit(self, interaction: discord.Interaction):
        replace_tokens = re.findall("{[0-3]{1}}", self.quote.value)
        quotes = self.db[interaction.guild_id, "quotes"].unwrap()
        if len(replace_tokens) <= 0:
            await interaction.response.send_message("Failed to add new quote: your quote lacks any replaceable portions! Add a replaceable portion in your quote by inserting {#} anywhere in your quote, where the # is a digit from 0-9. If you do not want any replaceable portions, use /quote add nonreplaceable!")
            return
        if self.default.value.casefold() == "none":
            await interaction.response.send_message("Failed to add new quote: the default field cannot be set to be \"None\", please choose a different default value.")
            return
        
        for quote_obj in quotes:
            if quote_obj["tag"] == self.tag.value:
                await interaction.response.send(f"Failed to add new quote, duplicate tag detected with quote: {quote_obj["default"] if quote_obj["has_original"] else quote_obj["quote"]}!")
                return
        else:
            new_quote = QUOTE_STRUCTURE.copy()
            new_quote["quote"] = self.quote.value
            new_quote["name"] = self.name.value if len(self.name.value) > 0  else "None"
            new_quote["tag"] = self.tag.value
            new_quote["replaceable"] = True
            new_quote["has_original"] = True if len(self.default.value) > 0 else False
            new_quote["default"] = self.default.value if new_quote["has_original"] else "None"
            quotes.append(new_quote)
            self.db[interaction.guild_id, "quotes"] = quotes
            await interaction.response.send_message("Successfully added new quote.")

def _generate_options(current_page, embeds):
    options = list()
    for i in range(len(embeds[current_page - 1].fields)):
        options.append(discord.SelectOption(label=f"Quote #{((current_page - 1) * 25) + (i + 1)}", description=embeds[current_page - 1].fields[i].value))
    return options

class Navigation(discord.ui.View):
    def __init__(self, db : RotiDatabase, pages : int, embeds : list, remove_mode : bool):
        super().__init__()
        self.timeout = 60
        self.db = db
        self.pages = pages
        self.current_page = 1  # Subtract 1 for indexing.
        self.embeds = embeds
        self.remove_mode = remove_mode
        self.remove_item(self._quote_rm_input)

        if self.pages == 1:
            self.remove_item(self._back)
            self.remove_item(self._next)

        if self.remove_mode:
            self.add_item(self._quote_rm_input)
            self._quote_rm_input.options = _generate_options(self.current_page, self.embeds)


    async def on_timeout(self) -> None:
        await self.message.delete()
        self.stop()

    @discord.ui.button(label='Back', style=discord.ButtonStyle.primary)
    async def _back(self, interaction : discord.Interaction, button : discord.ui.Button):
        if self.current_page > 1:
            self.current_page -= 1

            if self.remove_mode:
                self._quote_rm_input.options = _generate_options(self.current_page, self.embeds)
                await interaction.response.edit_message(embed=self.embeds[self.current_page - 1], view=self)
            else:
                await interaction.response.edit_message(embed=self.embeds[self.current_page - 1], view=self)

    @discord.ui.button(label='Next', style=discord.ButtonStyle.primary)
    async def _next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page is not self.pages:
            self.current_page += 1

            #Updates the options accordingly
            if self.remove_mode:
                self._quote_rm_input.options = _generate_options(self.current_page, self.embeds)
                await interaction.response.edit_message(embed=self.embeds[self.current_page - 1], view=self)
            else:
                await interaction.response.edit_message(embed=self.embeds[self.current_page - 1], view=self)

    @discord.ui.select(min_values=1, options=[], placeholder="Select a Quote.")
    async def _quote_rm_input(self, interaction : discord.Interaction, selection : discord.ui.Select):
        # This gets us the quote number, not the index, we need to search through the embed list to find the appropraite quote.
        quote_num = int(selection.values[0][selection.values[0].index("#") + 1:])
        field_quote = None
        index = -1
        regex = re.compile(fr"^\[[{quote_num}]\]\.")
        quotes = self.db[interaction.guild_id, "quotes"].unwrap()
        for quote_field in self.embeds[self.current_page - 1].fields:
            if regex.match(quote_field.name) is not None:
                field_quote = quote_field.value[0:147] if len(quote_field.value) >= 150 else quote_field.value
                break

        if field_quote is None:
            await interaction.response.send_message(content="Failed to delete quote.")
            await self.message.delete()

        #This backs out the index of the quote we would like to remove.
        for i in range(len(quotes)):
            if field_quote in quotes[i]["quote"] or field_quote in quotes[i]["default"]:
                index = i
                break

        if index == -1:
            await interaction.response.send_message(content="Failed to delete quote.")
            await self.message.delete()
        else:
            quote_to_delete = quotes[index]
            del quotes[index]
            self.db[interaction.guild_id, "quotes"] = quotes
            await interaction.response.send_message(content=f"Successfully deleted the quote: {quote_to_delete["default"] if quote_to_delete["has_original"] else quote_to_delete["quote"]}\n-{quote_to_delete["name"] if quote_to_delete["name"] != "None" else "???"}")
            await self.message.delete()
        self.stop()

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.danger)
    async def _cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.message.delete()
        self.stop()

class Say_Replacement_Modal(discord.ui.Modal, title="Say a replaceable quote!"):
    def __init__(self, quote, replace_tokens):
        super().__init__()
        self.timeout = 60
        self.quote = quote
        self.replace_tokens = replace_tokens
        self.reference_quote.default = self.quote["quote"]

        self.matched_tokens = [int(token[1]) for token in self.replace_tokens] #In the format of {#} always.
        for i in range(0, 4):
            if i not in self.matched_tokens:
                exec(f"self.remove_item(self.replacement_{i})")

    reference_quote = discord.ui.TextInput(
        label = "Quote for Reference",
        default = "This is a default value hahahahhahahhahahah"
    )

    replacement_0 = discord.ui.TextInput(
        label = "Replacement 0",
        placeholder = "All regions with {0} will be replaced with this",
        required = True,
    )

    replacement_1 = discord.ui.TextInput(
        label="Replacement 1",
        placeholder="All regions with {1} will be replaced with this",
        required=True,
    )

    replacement_2 = discord.ui.TextInput(
        label="Replacement 2",
        placeholder="All regions with {2} will be replaced with this",
        required=True,
    )

    replacement_3 = discord.ui.TextInput(
        label="Replacement 3",
        placeholder="All regions with {3} will be replaced with this",
        required=True,
    )

    async def on_error(self, interaction: discord.Interaction, error: Exception) -> None:
        await interaction.response.send_message('Oops! Something went wrong.', ephemeral=True)

    async def on_submit(self, interaction: discord.Interaction):
        replaced_quote = self.quote["quote"]

        # While not very elegant, this is better than using exec() again in an even more strange way.
        if 0 in self.matched_tokens:
            replaced_quote = replaced_quote.replace("{0}", self.replacement_0.value)
        if 1 in self.matched_tokens:
            replaced_quote = replaced_quote.replace("{1}", self.replacement_0.value)
        if 2 in self.matched_tokens:
            replaced_quote = replaced_quote.replace("{2}", self.replacement_0.value)
        if 3 in self.matched_tokens:
            replaced_quote = replaced_quote.replace("{3}", self.replacement_0.value)

        if len(replaced_quote) > 2000:
            await interaction.response.send_message("Replaced quote exceeds character limit of 2000 characters.", ephemeral=True)
            return

        await interaction.response.send_message(replaced_quote)

async def setup(bot: commands.Bot):
    await bot.add_cog(Quote(bot))
