import discord
import wikipedia
import asyncio
import logging
from typing import List
from discord import app_commands
from discord.ext import commands
from utils.RotiUtilities import cog_command

# Politeness matters for API rate limits
wikipedia.set_user_agent("RotiBot/b1.0")

@cog_command
class Wikipedia(commands.GroupCog, group_name="wikipedia"):
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.logger = logging.getLogger(__name__)

    async def fetch_page(self, query: str, auto_suggest: bool = True):
        """Helper to run the blocking wikipedia calls in a thread."""
        return await asyncio.to_thread(wikipedia.page, query, auto_suggest=auto_suggest)

    def create_wiki_embed(self, page: wikipedia.WikipediaPage) -> discord.Embed:
        """Standardized Google-style Wikipedia Embed."""
        # Use the first 800 chars for the snippet to keep it punchy
        summary = page.summary
        if len(summary) > 1000:
            summary = summary[:997] + "..."

        embed = discord.Embed(
            title=page.title,
            description=summary,
            color=0xecc98e,
            url=page.url
        )

        # Better Image Logic
        if page.images:
            # Skip common junk/icons
            ignored_extensions = ('.svg', '.gif', '.png') 
            valid_imgs = [i for i in page.images if not i.lower().endswith(ignored_extensions)]
            if valid_imgs:
                embed.set_image(url=valid_imgs[0])
            elif page.images:
                embed.set_thumbnail(url=page.images[0])

        embed.set_footer(text="Verified Wikipedia Article", icon_url="https://upload.wikimedia.org/wikipedia/en/thumb/8/80/Wikipedia-logo-v2.svg/1200px-Wikipedia-logo-v2.svg.png")
        embed.add_field(name="Source", value=f"[Read Full Article]({page.url})", inline=True)
        return embed

    @app_commands.command(name="search", description="Search Wikipedia with smart disambiguation.")
    async def _search(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        
        try:
            page = await self.fetch_page(query)
            embed = self.create_wiki_embed(page)
            await interaction.followup.send(embed=embed)

        except wikipedia.exceptions.DisambiguationError as e:
            view = WikiDisambigView(self, e.options[:25]) # Select menus have a 25 item limit
            embed = discord.Embed(
                title="🔍 Multiple Results Found",
                description=f"Your search for **{query}** is ambiguous. Please select the intended topic from the dropdown below.",
                color=discord.Color.blue()
            )
            await interaction.followup.send(embed=embed, view=view)

        except wikipedia.exceptions.PageError:
            await interaction.followup.send(f"❌ No Wikipedia page found for `{query}`.", ephemeral=True)
        except Exception as e:
            self.logger.error(f"Wiki Error: {e}")
            await interaction.followup.send("⚠️ Wikipedia is currently unresponsive.", ephemeral=True)

    @app_commands.command(name="random", description="Explore a random corner of human knowledge.")
    async def _random(self, interaction: discord.Interaction):
        await interaction.response.defer()
        try:
            title = await asyncio.to_thread(wikipedia.random, pages=1)
            page = await self.fetch_page(title, auto_suggest=False)
            embed = self.create_wiki_embed(page)
            await interaction.followup.send(embed=embed)
        except:
            await interaction.followup.send("Failed to roll the dice. Try again!")

# --- UI COMPONENTS ---

class WikiDisambigView(discord.ui.View):
    """A view that lets users pick from a list of ambiguous topics."""
    def __init__(self, cog: Wikipedia, options: List[str]):
        super().__init__(timeout=60)
        self.cog = cog
        
        # Add the select menu
        self.add_item(WikiSelect(options))

    async def on_timeout(self):
        # Clean up so we don't leave dead buttons
        if hasattr(self, 'message'):
            try: await self.message.edit(view=None)
            except: pass

class WikiSelect(discord.ui.Select):
    """The actual dropdown menu."""
    def __init__(self, options: List[str]):
        # Filter out very long strings that break Discord's label limit (100)
        formatted_options = [
            discord.SelectOption(label=opt[:100], value=opt[:100]) 
            for opt in options 
            if opt.strip()
        ]
        
        super().__init__(
            placeholder="Choose the correct topic...",
            min_values=1,
            max_values=1,
            options=formatted_options
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        selection = self.values[0]
        
        try:
            # Fetch the specific page the user selected
            page = await self.view.cog.fetch_page(selection, auto_suggest=False)
            embed = self.view.cog.create_wiki_embed(page)
            
            # Replace the disambiguation message with the actual article
            await interaction.edit_original_response(content=None, embed=embed, view=None)
            self.view.stop()
        except Exception:
            await interaction.followup.send("Could not load that specific page.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Wikipedia(bot))