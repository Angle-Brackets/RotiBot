import discord
import wizwiki
import asyncio
import logging
from discord import app_commands
from discord.ext import commands
from utils.RotiUtilities import cog_command

@cog_command
class Wiz(commands.GroupCog, group_name="wiz"):
    """Commands for the Wizard101 Wiki using the WizWiki package."""
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.logger = logging.getLogger(__name__)

    def _format_view(self, view) -> str:
        """Helper to format a View object into a clickable markdown link."""
        if not view: return "None"
        return f"[{view.name}]({view.url})"

    def _format_view_list(self, views, limit=5) -> str:
        """Helper to format a list of View objects."""
        if not views: return "None"
        formatted = [self._format_view(v) for v in views[:limit]]
        if len(views) > limit:
            formatted.append(f"*and {len(views) - limit} more...*")
        return ", ".join(formatted)

    def _clean_stats(self, stats: dict) -> str:
        """Helper to clean up messy stat keys and filter out debris."""
        if not stats: return "No stats available."
        cleaned = []
        for key, val in stats.items():
            # Strip known debris words
            junk = ["counter", "global", "item cards"]
            temp_key = key.lower()
            for word in junk:
                temp_key = temp_key.replace(word, "").strip()
            
            # Remove redundant segments (e.g., repeating the item category like "Hat")
            # We'll just try to normalize whitespace and see if it looks like a stat
            words = temp_key.split()
            unique_words = []
            for w in words:
                if w not in unique_words:
                    unique_words.append(w)
            
            cleaned_key = " ".join(unique_words).title()
            
            # If the key is empty after cleaning, it's likely pure junk
            if not cleaned_key:
                # If it's pure debris but has a value, maybe keep the value with a generic tag?
                # Actually, let's just keep the original key if cleaning nukes it
                cleaned_key = key
            
            cleaned.append(f"**{cleaned_key}:** {val}")
            
        return "\n".join(cleaned) if cleaned else "No valid stats found."

    @app_commands.command(name="creature", description="Search for a Wizard101 creature's stats and info.")
    async def _creature(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer()
        try:
            creature = await wizwiki.creature(name)
            
            embed = discord.Embed(
                title=f"👾 {creature.name}",
                description=f"**Category:** {creature.category}\n**Link:** [Wiki Page]({creature.url})",
                color=0x2ecc71,
                url=creature.url
            )
            
            # Exhaustive Mapping
            stats_info = []
            if creature.rank: stats_info.append(f"**Rank:** {creature.rank}")
            if creature.health: stats_info.append(f"**Health:** {creature.health:,}")
            if creature.school: stats_info.append(f"**School:** {creature.school}")
            if creature.classification: stats_info.append(f"**Classification:** {creature.classification}")
            if stats_info:
                embed.add_field(name="📊 Basic Info", value="\n".join(stats_info), inline=True)

            # Battle Stats
            if creature.battle_stats:
                bs = creature.battle_stats
                b_stats = []
                for attr in ['starting_pips', 'accuracy', 'incoming_boost', 'incoming_resist']:
                    val = getattr(bs, attr, None)
                    if val is not None:
                        b_stats.append(f"**{attr.replace('_', ' ').title()}:** {val}")
                if b_stats:
                    embed.add_field(name="⚔️ Battle Stats", value="\n".join(b_stats), inline=True)

            if creature.location:
                embed.add_field(name="📍 Location", value=self._format_view(creature.location), inline=False)
            
            if creature.allies:
                embed.add_field(name="👥 Allies", value=self._format_view_list(creature.allies), inline=False)

            # Drops Summary
            if creature.drops:
                drop_summary = []
                for cat, items in creature.drops.items():
                    drop_summary.append(f"**{cat}:** {len(items)} items")
                if drop_summary:
                    embed.add_field(name="🎁 Drop Categories", value="\n".join(drop_summary), inline=False)

            embed.set_footer(text="Powered by WizWiki API")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            self.logger.error(f"Wiz Creature Error: {e}")
            await interaction.followup.send(f"❌ Failed to find creature: **{name}**.", ephemeral=True)

    @app_commands.command(name="spell", description="Search for a Wizard101 spell's details.")
    async def _spell(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer()
        try:
            spell = await wizwiki.spell(name)
            
            embed = discord.Embed(
                title=f"🪄 {spell.name}",
                description=spell.description or "No description available.",
                color=0x3498db,
                url=spell.url
            )
            
            # Exhaustive Mapping
            specs = []
            if spell.school: specs.append(f"**School:** {spell.school}")
            if spell.pip_cost: specs.append(f"**Pip Cost:** {spell.pip_cost}")
            if spell.school_pip_cost: specs.append(f"**School Pip Cost:** {spell.school_pip_cost}")
            if spell.accuracy: specs.append(f"**Accuracy:** {spell.accuracy}")
            if specs:
                embed.add_field(name="📜 Specifications", value="\n".join(specs), inline=True)

            # Trainers & Links
            if spell.trainers:
                embed.add_field(name="👨‍🏫 Trainers", value=self._format_view_list(spell.trainers), inline=False)
            if spell.acquisition_sources:
                embed.add_field(name="🏁 Sources", value=self._format_view_list(spell.acquisition_sources), inline=False)
            if spell.prerequisites:
                embed.add_field(name="🔑 Prerequisites", value=self._format_view_list(spell.prerequisites), inline=False)

            if spell.animation_gif_url:
                # Reverting to raw URL as requested
                embed.set_thumbnail(url=spell.animation_gif_url)

            embed.set_footer(text="Powered by WizWiki API")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            self.logger.error(f"Wiz Spell Error: {e}")
            await interaction.followup.send(f"❌ Failed to find spell: **{name}**.", ephemeral=True)

    @app_commands.command(name="item", description="Search for a Wizard101 item's stats and requirements.")
    async def _item(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer()
        try:
            item = await wizwiki.item(name)
            
            embed = discord.Embed(
                title=f"⚔️ {item.name}",
                description=f"**Type:** {item.item_type or 'Item'}\n**Category:** {item.category}",
                color=0xf1c40f,
                url=item.url
            )
            
            # Exhaustive Mapping
            reqs = []
            if item.level_requirement: reqs.append(f"**Level:** {item.level_requirement}+")
            if item.school_requirement: reqs.append(f"**School:** {item.school_requirement}")
            if item.vendor_sell_price: reqs.append(f"**Sell Price:** {item.vendor_sell_price} Gold")
            if reqs:
                embed.add_field(name="🛡️ Requirements & Info", value="\n".join(reqs), inline=True)

            if item.stats:
                embed.add_field(name="📈 Stats", value=self._clean_stats(item.stats), inline=True)

            # Sources & Usage
            if item.dropped_by:
                embed.add_field(name="🎯 Dropped By", value=self._format_view_list(item.dropped_by), inline=False)
            if item.used_in_recipes:
                embed.add_field(name="🧪 Used in Recipes", value=self._format_view_list(item.used_in_recipes), inline=False)

            # Reverting to raw URL as requested
            if item.image_male_url:
                embed.set_thumbnail(url=item.image_male_url)

            embed.set_footer(text="Powered by WizWiki API")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            self.logger.error(f"Wiz Item Error: {e}")
            await interaction.followup.send(f"❌ Failed to find item: **{name}**.", ephemeral=True)

    @app_commands.command(name="recipe", description="Search for a Wizard101 crafting recipe.")
    async def _recipe(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer()
        try:
            recipe = await wizwiki.recipe(name)
            embed = discord.Embed(
                title=f"🧪 {recipe.name}",
                description=f"**Category:** {recipe.category}",
                color=0x9b59b6,
                url=recipe.url
            )
            
            if recipe.ingredients:
                ing_str = "\n".join([f"**{k}:** x{v}" for k, v in recipe.ingredients.items()])
                embed.add_field(name="📦 Ingredients", value=ing_str, inline=True)
            
            if recipe.crafting_station:
                embed.add_field(name="🏠 Station", value=recipe.crafting_station, inline=True)

            embed.set_footer(text="Powered by WizWiki API")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            self.logger.error(f"Wiz Recipe Error: {e}")
            await interaction.followup.send(f"❌ Failed to find recipe: **{name}**.", ephemeral=True)

    @app_commands.command(name="location", description="Search for a Wizard101 location.")
    async def _location(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer()
        try:
            location = await wizwiki.location(name)
            embed = discord.Embed(
                title=f"📍 {location.name}",
                description=location.description or "No description available.",
                color=0xe67e22,
                url=location.url
            )
            
            # Reverting to raw URL as requested
            if location.map_url:
                embed.set_image(url=location.map_url)
            
            if location.parents:
                embed.add_field(name="🌍 Parent Location", value=self._format_view_list(location.parents), inline=True)
            if location.sublocations:
                embed.add_field(name="🏘️ Sublocations", value=self._format_view_list(location.sublocations), inline=True)
            if location.connections:
                embed.add_field(name="🛤️ Connections", value=self._format_view_list(location.connections), inline=False)

            embed.set_footer(text="Powered by WizWiki API")
            await interaction.followup.send(embed=embed)
        except Exception as e:
            self.logger.error(f"Wiz Location Error: {e}")
            await interaction.followup.send(f"❌ Failed to find location: **{name}**.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Wiz(bot))
