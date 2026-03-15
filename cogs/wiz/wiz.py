import discord
import wizwiki
import asyncio
import logging
import io
import cloudscraper
from discord import app_commands
from discord.ext import commands
from utils.RotiUtilities import cog_command

@cog_command
class Wiz(commands.GroupCog, group_name="wiz"):
    """Advanced Wizard101 Wiki commands using the WizWiki Layout architecture."""
    
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        # Initialize the scraper to bypass Cloudflare
        self.scraper = cloudscraper.create_scraper(browser={
            'browser': 'chrome',
            'platform': 'windows',
            'desktop': True
        })

    def _sync_download(self, url: str) -> io.BytesIO | None:
        """Synchronous download for Cloudscraper bypass."""
        try:
            resp = self.scraper.get(url, timeout=10)
            if resp.status_code == 200:
                return io.BytesIO(resp.content)
            self.logger.warning(f"Cloudscraper status {resp.status_code} for {url}")
        except Exception as e:
            self.logger.error(f"Image Download Exception: {e}")
        return None

    async def _fetch_as_file(self, url: str, filename: str):
        """Asynchronous wrapper for the bypass downloader."""
        if not url or "None" in url:
            return None, None
        data = await asyncio.to_thread(self._sync_download, url)
        if data:
            return discord.File(data, filename=filename), f"attachment://{filename}"
        return None, None

    def _format_view_list(self, views, limit=10) -> str:
        """Converts a list of View objects into clickable markdown links."""
        if not views: return "None"
        formatted = [f"[{v.name}]({v.url})" for v in views[:limit]]
        if len(views) > limit:
            formatted.append(f"*...and {len(views) - limit} more*")
        return ", ".join(formatted)

    def _clean_stats(self, stats: dict) -> str:
        """Formats the stats dictionary into a clean list."""
        if not stats: return "No stats available."
        lines = []
        for k, v in stats.items():
            name = k.replace("stat_", "").replace("_", " ").title()
            lines.append(f"**{name}:** {v}")
        return "\n".join(lines)

    @app_commands.command(name="creature", description="Full details for a Wizard101 creature.")
    async def _creature(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer()
        try:
            c = await wizwiki.creature(name)
            file, thumb_url = await self._fetch_as_file("https://wiki.wizard101central.com/wiki/images/4/4b/Icon_Creature.png", "icon.png")

            class CreatureLayout(discord.ui.LayoutView):
                def __init__(self, c, t_url, outer):
                    super().__init__()
                    self.container = discord.ui.Container(accent_color=0x2ecc71)
                    
                    # Header Section
                    header = f"## 👾 {c.name}\n**Rank:** {c.rank} {c.school}\n**Health:** {c.health:,} HP"
                    if t_url:
                        self.container.add_item(discord.ui.Section(header, accessory=discord.ui.Thumbnail(t_url)))
                    else:
                        self.container.add_item(discord.ui.TextDisplay(header))

                    # Battle Stats
                    if c.battle_stats:
                        bs = c.battle_stats
                        traits = []
                        if bs.stunnable is False: traits.append("🚫 Stun Immune")
                        if bs.beguilable is False: traits.append("🚫 Beguile Immune")
                        
                        stat_block = f"**Starting Pips:** {bs.starting_pips}\n" \
                                     f"**Boost:** {bs.incoming_boost or 'None'}\n" \
                                     f"**Resist:** {bs.incoming_resist or 'None'}\n" \
                                     + " • ".join(traits)
                        self.container.add_item(discord.ui.TextDisplay("### ⚔️ Combat Intelligence\n" + stat_block))

                    # Relationships (Allies/Location)
                    rel_text = f"**Location:** [{c.location.name}]({c.location.url})\n" if c.location else ""
                    if c.allies:
                        rel_text += f"**Common Allies:** {outer._format_view_list(c.allies)}"
                    if rel_text:
                        self.container.add_item(discord.ui.TextDisplay("### 👥 World Presence\n" + rel_text))

                    # Drops Summary
                    if c.drops:
                        top_drops = []
                        for cat, items in list(c.drops.items())[:3]: # Show first 3 categories
                            top_drops.append(f"**{cat}:** {outer._format_view_list(items, limit=3)}")
                        self.container.add_item(discord.ui.TextDisplay("### 📦 Key Drops\n" + "\n".join(top_drops)))

                    self.add_item(self.container)
                    self.add_item(discord.ui.ActionRow(discord.ui.Button(label="Open Wiki", url=c.url)))

            msg = {"view": CreatureLayout(c, thumb_url, self)}
            if file: msg["file"] = file
            await interaction.followup.send(**msg)
        except Exception as e:
            self.logger.exception(f"Creature juice error: {e}")
            await interaction.followup.send("❌ Error fetching creature.", ephemeral=True)

    @app_commands.command(name="spell", description="Juiced details for a Wizard101 spell.")
    async def _spell(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer()
        try:
            s = await wizwiki.spell(name)
            files = []
            c_file, c_url = await self._fetch_as_file(s.card_image_url, "card.png")
            a_file, a_url = await self._fetch_as_file(s.animation_gif_url, "anim.gif")
            if c_file: files.append(c_file)
            if a_file: files.append(a_file)

            class SpellLayout(discord.ui.LayoutView):
                def __init__(self, s, c_url, a_url, outer):
                    super().__init__()
                    self.container = discord.ui.Container(accent_color=0x3498db)
                    header = f"## 🪄 {s.name}\n{s.description or 'No description available.'}"
                    
                    if c_url:
                        self.container.add_item(discord.ui.Section(header, accessory=discord.ui.Thumbnail(c_url)))
                    else:
                        self.container.add_item(discord.ui.TextDisplay(header))

                    specs = f"**School:** {s.school} | **Pips:** {s.pip_cost} | **Acc:** {s.accuracy}%"
                    self.container.add_item(discord.ui.TextDisplay(specs))
                    self.container.add_item(discord.ui.Separator())

                    if a_url:
                        self.container.add_item(discord.ui.MediaGallery(discord.MediaGalleryItem(a_url, description="Spell Cast Animation")))

                    if s.trained_from:
                        self.container.add_item(discord.ui.TextDisplay(f"**Trained From:** {outer._format_view_list(s.trained_from)}"))

                    self.add_item(self.container)
                    self.add_item(discord.ui.ActionRow(discord.ui.Button(label="View on Wiki", url=s.url)))

            msg = {"view": SpellLayout(s, c_url, a_url, self)}
            if files: msg["files"] = files
            await interaction.followup.send(**msg)
        except Exception:
            await interaction.followup.send("❌ Spell not found.", ephemeral=True)

    @app_commands.command(name="item", description="Full stats and source info for an item.")
    async def _item(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer()
        try:
            i = await wizwiki.item(name)
            file, thumb_url = await self._fetch_as_file(i.image_male_url or i.image_female_url, "item.png")

            class ItemLayout(discord.ui.LayoutView):
                def __init__(self, i, t_url, outer):
                    super().__init__()
                    self.container = discord.ui.Container(accent_color=0xe74c3c)
                    header = f"## ⚔️ {i.name}\n**Type:** {i.item_type} | **Lvl:** {i.level_requirement or 0}+"
                    
                    if t_url:
                        self.container.add_item(discord.ui.Section(header, accessory=discord.ui.Thumbnail(t_url)))
                    else:
                        self.container.add_item(discord.ui.TextDisplay(header))

                    # Stat Block
                    if i.stats:
                        self.container.add_item(discord.ui.TextDisplay("### 📈 Combat Stats\n" + outer._clean_stats(i.stats)))

                    # Cards provided by item
                    if i.item_cards:
                        self.container.add_item(discord.ui.TextDisplay("### 🎴 Item Cards\n" + " • ".join(i.item_cards)))

                    # Economy/Source
                    econ = f"**Sell Price:** {i.vendor_sell_price or 0} Gold\n" \
                           f"**Auctionable:** {'✅' if i.is_auctionable else '❌'} | **Tradeable:** {'✅' if i.is_tradeable else '❌'}"
                    self.container.add_item(discord.ui.TextDisplay("### 💰 Economy\n" + econ))

                    if i.dropped_by:
                        self.container.add_item(discord.ui.TextDisplay("### 🎯 Dropped By\n" + outer._format_view_list(i.dropped_by)))

                    self.add_item(self.container)
                    self.add_item(discord.ui.ActionRow(discord.ui.Button(label="Wiki Page", url=i.url)))

            msg = {"view": ItemLayout(i, thumb_url, self)}
            if file: msg["file"] = file
            await interaction.followup.send(**msg)
        except Exception:
            await interaction.followup.send("❌ Item not found.", ephemeral=True)

    @app_commands.command(name="recipe", description="Crafting requirements and vendors.")
    async def _recipe(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer()
        try:
            r = await wizwiki.recipe(name)
            
            class RecipeLayout(discord.ui.LayoutView):
                def __init__(self, r, outer):
                    super().__init__()
                    self.container = discord.ui.Container(accent_color=0x9b59b6)
                    self.container.add_item(discord.ui.TextDisplay(f"## 🧪 Recipe: {r.name}\n**Category:** {r.recipe_type}"))
                    
                    if r.ingredients:
                        ing = "\n".join([f"• x{count} **{name}**" for name, count in r.ingredients.items()])
                        self.container.add_item(discord.ui.TextDisplay("### 📦 Ingredients\n" + ing))
                    
                    if r.crafts:
                        self.container.add_item(discord.ui.TextDisplay(f"### 🛠️ Crafts\n{outer._format_view_list(r.crafts)}"))
                    
                    if r.vendors:
                        self.container.add_item(discord.ui.TextDisplay(f"### 🏪 Vendors\n{outer._format_view_list(r.vendors)}"))

                    self.add_item(self.container)
                    self.add_item(discord.ui.ActionRow(discord.ui.Button(label="Wiki Page", url=r.url)))

            await interaction.followup.send(view=RecipeLayout(r, self))
        except Exception:
            await interaction.followup.send("❌ Recipe not found.", ephemeral=True)

    @app_commands.command(name="location", description="Details about a world or area.")
    async def _location(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer()
        try:
            loc = await wizwiki.location(name)
            
            class LocationLayout(discord.ui.LayoutView):
                def __init__(self, l, outer):
                    super().__init__()
                    self.container = discord.ui.Container(accent_color=0xe67e22)
                    self.container.add_item(discord.ui.TextDisplay(f"## 📍 {l.name}\n**World:** {l.world or 'Spiral'}"))
                    
                    if l.areas:
                        self.container.add_item(discord.ui.TextDisplay("### 🏘️ Sub-areas\n" + outer._format_view_list(l.areas)))

                    self.add_item(self.container)
                    self.add_item(discord.ui.ActionRow(discord.ui.Button(label="Visit Wiki", url=l.url)))

            await interaction.followup.send(view=LocationLayout(loc, self))
        except Exception:
            await interaction.followup.send("❌ Location not found.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Wiz(bot))