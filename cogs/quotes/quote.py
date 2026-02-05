import typing
import discord
import itertools
import re
import logging

from returns.result import Success, Failure
from discord import app_commands
from discord.ext import commands
from database.data import RotiDatabase, QuotesTable
from utils.RotiUtilities import cog_command
from cogs.statistics.statistics_helpers import ttl_cache

def build_quote(quote : QuotesTable):
    if quote.name == "None":
        return quote.default
    return f"{quote.default}\n-{quote.name}"

@cog_command
class Quote(commands.GroupCog, group_name="quote"):
    def __init__(self, bot : commands.Bot):
        super().__init__()
        self.bot = bot
        self.db = RotiDatabase()
        self.logger = logging.getLogger(__name__)

    add_group = app_commands.Group(name="add", description="Creates a new quote")

    @app_commands.describe(quote="The new quote to be added.", tag="A unique identifier that can be used to find this quote again.", name="An optional argument that will add the name of who said the quote.")
    @add_group.command(name="nonreplaceable", description="Creates a new quote that has NO replaceable portions.")
    async def _quote_add_nonrep(self, interaction : discord.Interaction, quote : str, tag : str, name : typing.Optional[str]):
        await interaction.response.defer(ephemeral=True)

        if len(tag) > 128:
            await interaction.followup.send("Provided tag exceeds max length of 128 characters, shorten it and try again!")
            return

        row = await self.db.select_one(QuotesTable, server_id=interaction.guild_id, tag=tag)
        if row:
            await interaction.followup.send(f"Failed to add new quote, duplicate tag detected with quote: {row.default if row.has_original else row.quote}!")
            return                

        new_quote = QuotesTable(
            server_id=interaction.guild_id,
            tag=tag,
            quote=quote,
            default=quote,
            name=name if name is not None else "None",
            replaceable=False,
            has_original=True #Always true for non-replaceable quotes.
        )

        self.db.insert(new_quote)
        await interaction.followup.send("Successfully added new quote.")

    @add_group.command(name="replaceable", description="Creates a new quote that has replaceable portions.")
    async def _quote_add_rep(self, interaction : discord.Interaction):
        await interaction.response.send_modal(QuoteModal(self.db))

    @app_commands.command(name="random", description="Displays a random quote.")
    async def _quote_random(self, interaction : discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        await interaction.followup.send("Retrieving...")
        query = f"""
        SELECT * FROM "Quotes"
        WHERE "server_id" != {interaction.guild_id} AND "has_original"
        ORDER BY RANDOM()
        LIMIT 1
        """

        match await self.db.raw_query(query):
            case Success(random_quote) if random_quote and random_quote[0]:
                random_quote = self.db._dict_to_dataclass(QuotesTable, random_quote[0])
                await interaction.followup.send(build_quote(random_quote), ephemeral=False)
            case Success(random_quote) if random_quote and not random_quote[0]:
                return await interaction.followup.send("No quotes found! Add a quote using /quote add!", ephemeral=True)
            case Failure(error):
                self.logger.error("Failed to retrieve quote for server: %i\nError: %s", interaction.guild_id, error)
                return await interaction.followup.send("No quotes found! Add a quote using /quote add!", ephemeral=True)

    @app_commands.describe(query="A search query that can be a tag, name, or substring of the quote.", show_defaultless="Toggle to change whether quotes without defaults are displayed, by default they are NOT displayed.")
    @app_commands.command(name="list", description="Displays all of the quotes present in the server.")
    async def _quote_list(self, interaction : discord.Interaction, query: typing.Optional[str], show_defaultless : typing.Optional[bool]):
        await interaction.response.defer(ephemeral=True)

        count = await self.db.count(QuotesTable, server_id=interaction.guild_id)
        show_defaultless = show_defaultless if show_defaultless is not None else False
        
        if count == 0:
            await interaction.followup.send("No quotes found! Add a quote using /quote add!", ephemeral=True)
            return

        # This might want to be improved to be a bit more optimized...idk. Also should be an OR condition.
        quotes = await self.db.select_all(QuotesTable, server_id=interaction.guild_id, has_original=not show_defaultless)
        # In memory filter, don't support fuzzy matching yet with the DB engine.
        if query:
            q = query.casefold()
            quotes = [
                x for x in quotes
                if q in x.quote.casefold()
                or q in x.tag.casefold()
                or (x.name != "None" and q in x.name.casefold())
                or (x.default != "None" and q in x.default.casefold())
            ]
        
        if not quotes:
            await interaction.followup.send("No quotes found! Try a different query or parameter!", ephemeral=True)
            return

        embed_base = discord.Embed(
            title=f"List of all Quotes in {interaction.guild.name}", 
            description="Use the buttons below to navigate between pages.", 
            color=0xecc98e
        )

        # 1. Split into pages of 25 quotes at a time.
        PAGE_SIZE = 25
        split_list = list(itertools.batched(quotes, PAGE_SIZE))
        total_pages = len(split_list)
        all_embeds = []
        count = 1

        # 2. Generate the embeds
        for current_page, batch in enumerate(split_list, start=1):
            new_embed = embed_base.copy()
            
            for quote in batch:
                if quote.has_original:
                    quote_to_display = quote.default
                else:
                    quote_to_display = quote.quote

                # Format Sayer Name
                display_name = quote.name if quote.name != "None" else "???"
                quote_sayer = f"[{count}]. A Quote by {display_name}"
                if len(quote_sayer) > 128:
                    quote_sayer = f"{quote_sayer[:125]}..."

                # Format Tag and Lock status
                tag_text = quote.tag if len(quote.tag) < 100 else f"{quote.tag[:97]}..."
                status_emoji = "🔓" if quote.replaceable else "🔒"
                
                field_name = f"{quote_sayer}\nTag: {tag_text} {status_emoji}"
                
                # Format the Quote value
                field_value = quote_to_display if len(quote_to_display) <= 150 else f"{quote_to_display[:147]}..."

                new_embed.add_field(name=field_name, value=field_value, inline=False)
                count += 1

            # Set footer with current progress
            new_embed.set_footer(
                text=f"Page {current_page}/{total_pages}\nSyntax: 🔒 - Nonreplaceable, 🔓 - Replaceable"
            )
            all_embeds.append(new_embed)

        # 3. Handle empty results
        if not all_embeds:
            await interaction.followup.send("No quotes found.", ephemeral=True)
            return

        # 4. View and Navigation
        view = QuoteNavigation(len(all_embeds), all_embeds, False)
        message = await interaction.followup.send(embed=all_embeds[0], view=view, ephemeral=True)
        view.message = message

        await view.wait()

    @app_commands.describe(query="A keyword to help search for a particular quote, matches against the name, tag, and actual quote itself.")
    @app_commands.command(name="remove", description="Remove a specific quote")
    async def _quote_remove(self, interaction : discord.Interaction, query : typing.Optional[str]):
        await interaction.response.defer(ephemeral=True)

        count = await self.db.count(QuotesTable, server_id=interaction.guild_id)
        if count == 0:
            await interaction.followup.send("No quotes found! Add a quote using /quote add!", ephemeral=True)
            return
        
        # In memory filter, don't support fuzzy matching yet with the DB engine.
        quotes = await self.db.select_all(QuotesTable, server_id=interaction.guild_id)
        if query:
            q = query.casefold()
            quotes = [
                x for x in quotes
                if q in x.quote.casefold()
                or q in x.tag.casefold()
                or (x.name != "None" and q in x.name.casefold())
                or (x.default != "None" and q in x.default.casefold())
            ]
        
        if not quotes:
            await interaction.followup.send(f"No matches found with query: {query}.")
            return


        # 3. Setup Embeds
        desc_text = f"List of quotes matching `{query}`" if query else "List of all quotes"
        embed_base = discord.Embed(
            title=f"Remove Quote - {interaction.guild.name}", 
            description=f"{desc_text}\nUse the buttons to navigate.", 
            color=0xecc98e
        )

        all_embeds = []
        PAGE_SIZE = 25
        split_list = list(itertools.batched(quotes, PAGE_SIZE))
        total_pages = len(split_list)
        count = 1

        for current_page, batch in enumerate(split_list, start=1):
            new_embed = embed_base.copy()
            
            for quote_obj in batch:
                # Show default if original exists, otherwise show raw quote
                quote_to_display = quote_obj.default if quote_obj.has_original else quote_obj.quote
                
                # Format Sayer
                sayer_name = quote_obj.name if quote_obj.name != "None" else "???"
                quote_sayer = f"[{count}]. {sayer_name}"
                
                # Format Tag
                tag_display = quote_obj.tag if len(quote_obj.tag) < 50 else f"{quote_obj.tag[:47]}..."
                
                # Header: Name | Tag
                field_name = f"{quote_sayer} | Tag: {tag_display}"
                
                # Truncate Body
                field_value = quote_to_display if len(quote_to_display) <= 150 else f"{quote_to_display[:147]}..."
                
                new_embed.add_field(name=field_name, value=field_value, inline=False)
                count += 1
                
            new_embed.set_footer(text=f"Page {current_page}/{total_pages} • Note the ID to delete specific quotes")
            all_embeds.append(new_embed)

        # 4. View Handling
        view = DeleteView(self.db, split_list, all_embeds)
        
        message = await interaction.followup.send(embed=all_embeds[0], view=view)
        view.message = message
        await view.wait()

    @app_commands.describe(
        tag="The tag of the quote you would like to say.", 
        type="Replaceable: fill in the blanks. Nonreplaceable: say the default version."
    )
    @app_commands.command(name="say", description="Say a specific quote")
    async def _say(self, interaction: discord.Interaction, tag: str, type: typing.Literal["Replaceable", "Nonreplaceable"]):        
        quote = await self.db.select_one(QuotesTable, server_id=interaction.guild_id, tag=tag)

        if not quote:
            await interaction.response.send_message("No quote exists for this tag!", ephemeral=True)
            return

        # 2. Handle Nonreplaceable Request
        if type == "Nonreplaceable":
            if not quote.has_original:
                await interaction.response.send_message("No default version exists for this quote.", ephemeral=True)
                return
            
            # Simple send
            await interaction.response.send_message(quote.default)
            return

        # 3. Handle Replaceable Request
        # Check if it actually IS a replaceable quote
        if not quote.replaceable:
            if quote.has_original:
                await interaction.response.send_message(f"Quote `{tag}` is not replaceable. Sending default instead.", ephemeral=True)
                await interaction.followup.send(quote.default)
            else:
                await interaction.response.send_message("This quote is not replaceable.", ephemeral=True)
            return
        
        # 4. Analyze Tokens and Send Modal
        # Find all occurrences of {0}, {1}, etc.
        unique_tokens = set(re.findall(r"\{[0-3]\}", quote.quote))
        
        if not unique_tokens:
            # Fallback if flag says replaceable but regex finds nothing
            await interaction.response.send_message(quote.quote)
        else:
            await interaction.response.send_modal(SayReplacementModal(quote, unique_tokens))


    @ttl_cache(ttl=30)
    @_say.autocomplete("tag")
    async def _tag_autocomplete(self, interaction: discord.Interaction, current: str):
        quotes = await self.db.select_all(QuotesTable, server_id=interaction.guild_id)
        
        choices = []
        search_query = current.casefold()
        
        for q in quotes:
            if search_query in q.tag.casefold():
                type_str = "Replaceable" if q.replaceable else "Non-Replaceable"
                name = f"{q.tag} ({type_str})"[:100]
                
                choices.append(app_commands.Choice(name=name, value=q.tag))
                
                if len(choices) >= 25: # Discord's maximum allowed choices
                    break
                    
        return choices

class QuoteModal(discord.ui.Modal, title = "Make a new Replaceable Quote!"):
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
        
        if len(replace_tokens) <= 0:
            await interaction.response.send_message("Failed to add new quote: your quote lacks any replaceable portions! Add a replaceable portion in your quote by inserting {#} anywhere in your quote, where the # is a digit from 0-9. If you do not want any replaceable portions, use /quote add nonreplaceable!", ephemeral=True)
            return
        if self.default.value.casefold() == "none":
            await interaction.response.send_message("Failed to add new quote: the default field cannot be set to be \"None\", please choose a different default value.", ephemeral=True)
            return
        
        row = await self.db.select_one(QuotesTable, server_id=interaction.guild_id, tag=self.tag.value)
        if row:
            await interaction.response.send_message(f"Failed to add new quote, duplicate tag detected with quote: {row.default if row.has_original else row.quote}!", ephemeral=True)
            return
        else:
            new_quote = QuotesTable(
                server_id=interaction.guild_id,
                quote=self.quote.value,
                tag=self.tag.value,
                name=self.name.value if len(self.name.value) > 0 else "None",
                replaceable=True,
                has_original=len(self.default.value) > 0,
                default=self.default.value if len(self.default.value) > 0 else "None"
            )

            self.db.insert(new_quote)
            await interaction.response.send_message("Successfully added new quote.",ephemeral=True)

class QuoteNavigation(discord.ui.View):
    def __init__(self, pages: int, embeds: list, split_list: list = None):
        super().__init__(timeout=60)
        self.pages = pages
        self.current_page = 1 
        self.embeds = embeds
        self.split_list = split_list  # List of batches of Quote objects
        self.message = None

        # Adjust UI based on mode/page count
        if self.pages <= 1:
            self.remove_item(self._back)
            self.remove_item(self._next)
            self.remove_item(self._jump)
        
        self._update_dropdown()

    def _update_dropdown(self):
        """Refreshes the dropdown options based on the current page's quotes."""
        if not self.split_list:
            return
            
        current_batch = self.split_list[self.current_page - 1]
        options = []
        for i, quote in enumerate(current_batch, start=1):
            label = quote.default if quote.has_original else quote.quote
            options.append(discord.SelectOption(
                label=f"{i}. {label[:90]}...",
                value=str(quote.id), # The hidden ID!
                description=f"By: {quote.name}"
            ))
        self._quote_rm_input.options = options

    async def update_view(self, interaction: discord.Interaction):
        """Centralized refresh for the message."""        
        await interaction.response.edit_message(
            embed=self.embeds[self.current_page - 1], 
            view=self
        )

    @discord.ui.button(label='Back', style=discord.ButtonStyle.primary)
    async def _back(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 1:
            self.current_page -= 1
            await self.update_view(interaction)
        else:
            await interaction.response.defer()

    @discord.ui.button(label='Jump', style=discord.ButtonStyle.secondary)
    async def _jump(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(JumpModal(self))

    @discord.ui.button(label='Next', style=discord.ButtonStyle.primary)
    async def _next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.pages:
            self.current_page += 1
            await self.update_view(interaction)
        else:
            await interaction.response.defer()

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.danger)
    async def _cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.message.delete()
        self.stop()

    async def on_timeout(self) -> None:
        try:
            await self.message.delete()
        except:
            pass
        self.stop()

class JumpModal(discord.ui.Modal, title="Jump to Page"):
    page_num = discord.ui.TextInput(
        label="Enter Page Number",
        placeholder="Type a number...",
        min_length=1,
        max_length=3
    )

    def __init__(self, view):
        super().__init__()
        self.view = view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            target = int(self.page_num.value)
            if 1 <= target <= self.view.pages:
                self.view.current_page = target
                await self.view.update_view(interaction)
            else:
                await interaction.response.send_message(f"Please enter a page between 1 and {self.view.pages}.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message("Please enter a valid number.", ephemeral=True)

class DeleteView(discord.ui.View):
    def __init__(self, db, split_list, embeds):
        super().__init__(timeout=180)
        self.db = db
        self.split_list = split_list
        self.embeds = embeds
        self.current_page = 0
        self.message = None

        # Add the initial dropdown for page 0
        self.add_item(DeleteQuoteSelect(self.split_list[0]))
        self.update_buttons()

    def update_buttons(self):
        self.prev_button.disabled = (self.current_page == 0)
        self.next_button.disabled = (self.current_page == len(self.embeds) - 1)

    async def update_view(self, interaction: discord.Interaction):
        self.update_buttons()
        
        # CLEAR previous dropdown and add the new one for this page
        self.clear_items()
        
        # Re-add navigation buttons (since clear_items wiped them)
        self.add_item(self.prev_button)
        self.add_item(self.next_button)
        
        # Add the new Dropdown for the current batch of quotes
        current_batch = self.split_list[self.current_page]
        self.add_item(DeleteQuoteSelect(current_batch))

        await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(label="Prev", style=discord.ButtonStyle.gray, row=1)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        await self.update_view(interaction)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.gray, row=1)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        await self.update_view(interaction)

class DeleteQuoteSelect(discord.ui.Select):
    def __init__(self, quotes: list[QuotesTable]):
        # Create options from the quotes list
        options = []
        for i, quote in enumerate(quotes, start=1):
            # Truncate text for the label (max 100 chars allowed by Discord)
            label_text = quote.default if quote.has_original else quote.quote
            if len(label_text) > 95:
                label_text = label_text[:92] + "..."
            
            # The value must be a string, so we pass the invisible ID here
            options.append(discord.SelectOption(
                label=f"{i}. {label_text}", 
                description=f"By: {quote.name}", 
                value=str(quote.id),
                emoji="🗑️"
            ))

        super().__init__(
            placeholder="Select a quote to delete...",
            min_values=1,
            max_values=1,
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        if not self.values:
            return
        
        # 1. Get the hidden ID from the selection (after selection this is the current value)
        quote_id = int(self.values[0])
        
        try:
            await self.view.db.delete(QuotesTable, id=quote_id)
            await interaction.response.send_message(f"✅ Quote successfully deleted!", ephemeral=True)
            
            # 3. Disable the view so they can't delete ghost items
            self.view.stop()
            await self.view.message.edit(view=None, content="*Session closed after deletion.*")
            
        except Exception as e:
            await interaction.response.send_message(f"Failed to delete quote: {e}", ephemeral=True)

class SayReplacementModal(discord.ui.Modal):
    def __init__(self, quote: QuotesTable, replace_tokens: set):
        # Dynamically set the title based on the quote tag
        super().__init__(title=f"Replace: {quote.tag[:40]}")
        self.quote = quote
        
        # Parse tokens: "{0}" -> 0
        self.matched_tokens = {int(token[1]) for token in replace_tokens}

        # 1. Setup Reference Field (ReadOnly-ish)
        # We display the raw quote so the user knows what goes where.
        self.reference_quote.default = self.quote.quote
        
        # 2. Logic to keep only necessary inputs
        # We put them in a list to iterate easily
        all_inputs = [self.replacement_0, self.replacement_1, self.replacement_2, self.replacement_3]
        
        for i, text_input in enumerate(all_inputs):
            if i not in self.matched_tokens:
                self.remove_item(text_input)

    # UI Elements
    reference_quote = discord.ui.TextInput(
        label="Reference (Do not edit)",
        style=discord.TextStyle.long,
        required=False
    )

    replacement_0 = discord.ui.TextInput(
        label="Replacement for {0}",
        placeholder="Type text here...",
        required=True
    )

    replacement_1 = discord.ui.TextInput(
        label="Replacement for {1}",
        placeholder="Type text here...",
        required=True
    )

    replacement_2 = discord.ui.TextInput(
        label="Replacement for {2}",
        placeholder="Type text here...",
        required=True
    )

    replacement_3 = discord.ui.TextInput(
        label="Replacement for {3}",
        placeholder="Type text here...",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        # Safe string replacement
        final_text = self.quote.quote

        # Map indices to the actual input objects
        inputs = {
            0: self.replacement_0,
            1: self.replacement_1,
            2: self.replacement_2,
            3: self.replacement_3
        }

        for index in self.matched_tokens:
            if index in inputs:
                # Replace "{0}" with the value from replacement_0 and so on.
                final_text = final_text.replace(f"{{{index}}}", inputs[index].value)
        await interaction.response.send_message(final_text)

async def setup(bot: commands.Bot):
    await bot.add_cog(Quote(bot))
