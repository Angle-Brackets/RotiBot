import discord
import wizwiki
import asyncio
import logging
import io
import re
import cloudscraper
from discord import app_commands
from discord.ext import commands
from utils.RotiUtilities import cog_command
from curl_cffi import requests as cffi_requests

@cog_command
class Wiz(commands.GroupCog, group_name="wiz"):
    """Advanced Wizard101 Wiki commands using the WizWiki Layout architecture."""
    
    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot
        self.logger = logging.getLogger(__name__)

        self.SCHOOL_COLORS = {
            "Fire": 0xe74c3c,
            "Ice": 0x3498db,
            "Storm": 0xf1c40f,
            "Death": 0x8e44ad,
            "Life": 0x2ecc71,
            "Myth": 0xf39c12,
            "Balance": 0xd4af37,
            "Shadow": 0x2c3e50,
            "Sun": 0xf39c12,
            "Moon": 0x9b59b6,
            "Star": 0x3498db,
        }

        self.SCHOOL_ICONS = {
            "Fire": "🔥",
            "Ice": "❄️",
            "Storm": "⚡",
            "Death": "💀",
            "Life": "🌿",
            "Myth": "🐉",
            "Balance": "⚖️",
            "Shadow": "🌑",
            "Sun": "☀️",
            "Moon": "🌙",
            "Star": "⭐",
        }

        # not added yet
        # Format: "School": emoji_id (as integer)
        # Leave as None to use default Unicode emoji
        self.CUSTOM_EMOJI_IDS = {
            "Fire": None,
            "Ice": None,
            "Storm": None,
            "Death": None,
            "Life": None,
            "Myth": None,
            "Balance": None,
            "Shadow": None,
            "Sun": None,
            "Moon": None,
            "Star": None,
        }

        # WizWiki branding
        self.WIZWIKI_REPO = "https://github.com/Angle-Brackets/WizWiki"
        self.FOOTER_TEXT = "Powered by WizWiki"

    def _sync_download(self, url: str) -> io.BytesIO | None:
        """Synchronous download using curl_cffi to spoof TLS fingerprints."""
        try:
            # Impersonate a modern browser exactly
            resp = cffi_requests.get(url, impersonate="chrome110", timeout=10)
            
            if resp.status_code == 200:
                return io.BytesIO(resp.content)
            self.logger.warning(f"Download status {resp.status_code} for {url}")
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
    
    def _parse_schools(self, school_str: str | None) -> list[str]:
        if not school_str:
            return []
        return school_str.split()

    def _school_color(self, school_str: str | None):
        schools = self._parse_schools(school_str)
        if not schools:
            return 0x95a5a6

        primary = schools[0]
        return self.SCHOOL_COLORS.get(primary, 0x95a5a6)
    
    def _school_icons(self, school_str: str | None):
        schools = self._parse_schools(school_str)
        return " ".join(self._get_school_emoji(s) for s in schools)

    def _get_school_emoji(self, school: str) -> str:
        """Get school emoji with custom emoji fallback.
        
        Tries to use custom emoji from external server first.
        Falls back to default Unicode emoji if custom doesn't exist or isn't configured.
        """
        if not school:
            return "✨"
        
        # Try custom emoji if configured
        custom_id = self.CUSTOM_EMOJI_IDS.get(school)
        if custom_id:
            try:
                emoji = self.bot.get_emoji(custom_id)
                if emoji:
                    return str(emoji)
            except Exception as e:
                self.logger.warning(f"Failed to fetch custom emoji for {school}: {e}")
        
        # Fall back to default Unicode emoji
        return self.SCHOOL_ICONS.get(school, "✨")

    def _parse_cheats(self, cheats_list: list) -> list[str]:
        """Parse and split cheats - handles both quoted format and plain text.
        
        Tries to parse "Cheat Name" - Description format first.
        Falls back to splitting on sentence boundaries if needed.
        Returns list of individual cheat entries.
        """
        if not cheats_list:
            return []
        
        parsed = []
        for cheat_block in cheats_list:
            # Try to find quoted format first: "Name" - Description
            pattern = r'"([^"]+)"\s*-\s*([^"]*?)(?="(?=[A-Z])|$)'
            matches = list(re.finditer(pattern, cheat_block))
            
            if matches:
                # Successfully parsed quoted format
                for match in matches:
                    cheat_name = match.group(1).strip()
                    description = match.group(2).strip()
                    if cheat_name:
                        cheat_entry = f'"{cheat_name}"'
                        if description:
                            cheat_entry += f' - {description}'
                        parsed.append(cheat_entry)
            else:
                # No quoted format found - treat as plain text
                # Split on periods followed by capital letters (sentence boundaries)
                sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', cheat_block)
                
                # Reconstruct into logical chunks
                current_chunk = ""
                for sentence in sentences:
                    sentence = sentence.strip()
                    if not sentence:
                        continue
                    
                    # Try to keep chunks under 500 chars for readability
                    if len(current_chunk) + len(sentence) + 1 < 500:
                        current_chunk += (" " if current_chunk else "") + sentence
                    else:
                        if current_chunk:
                            parsed.append(current_chunk)
                        current_chunk = sentence
                
                if current_chunk:
                    parsed.append(current_chunk)
        
        return parsed

    @app_commands.command(name="creature", description="Full details for a Wizard101 creature.")
    async def _creature(self, interaction: discord.Interaction, name: str):
        await self._creature_logic(interaction, name, ephemeral=True)

    async def _creature_logic(self, interaction: discord.Interaction, name_or_obj, ephemeral: bool = True):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=ephemeral)
        try:
            if isinstance(name_or_obj, str):
                c = await wizwiki.creature(name_or_obj)
            else:
                c = name_or_obj
            file = None
            img_url = None
            if c.image_url:
                file, img_url = await self._fetch_as_file(c.image_url, "creature.png")
            # Determine accent color based on primary school
            accent_color = self._school_color(c.school)

            class CreatureLayout(discord.ui.LayoutView):
                def __init__(self, creature, img_url, outer, accent_color, is_public=False):
                    super().__init__()
                    self.c = creature
                    self.img_url = img_url
                    self.outer = outer
                    self.accent_color = accent_color
                    self.is_public = is_public
                    self.current_page = 0
                    # Calculate total pages: always overview, + cheats if available, + drops if available
                    self.pages = ["overview"]
                    if self.c.cheats:
                        self.pages.append("cheats")
                    if self.c.drops:
                        self.pages.append("drops")
                    self._render_page()

                def _render_page(self):
                    """Render the current page."""
                    self.clear_items()
                    self.container = discord.ui.Container(accent_color=self.accent_color)
                    page_type = self.pages[self.current_page]
                    if page_type == "overview":
                        self._render_overview()
                    elif page_type == "cheats":
                        self._render_cheats()
                    elif page_type == "drops":
                        self._render_drops()
                    self.add_item(self.container)
                    self._add_footer()

                def _render_overview(self):
                    """Render the overview page."""
                    classification = f" ({self.c.classification})" if self.c.classification else ""
                    health = f"{self.c.health:,} HP" if self.c.health else "Unknown HP"
                    schools = self.outer._parse_schools(self.c.school)
                    icons = self.outer._school_icons(self.c.school)
                    school_text = " ".join(schools) if schools else "Unknown"
                    header = (
                        f"## {icons} {self.c.name}\n"
                        f"🏷️ **Rank:** {self.c.rank or 'Unknown'} | {school_text}{classification}\n"
                        f"❤️ **Health:** {health}"
                    )
                    if self.img_url:
                        self.container.add_item(
                            discord.ui.Section(
                                header,
                                accessory=discord.ui.Thumbnail(self.img_url)
                            )
                        )
                    else:
                        self.container.add_item(discord.ui.TextDisplay(header))
                    self.container.add_item(discord.ui.Separator())
                    if self.c.battle_stats:
                        bs = self.c.battle_stats
                        traits = []
                        if bs.stunnable is False:
                            traits.append("🚫 Stun Immune")
                        if bs.beguilable is False:
                            traits.append("🚫 Beguile Immune")
                        stats = (
                            f"### ⚔️ Combat Stats\n"
                            f"🔮 **Starting Pips:** {bs.starting_pips or '—'}\n"
                            f"📈 **Boost:** {bs.incoming_boost or 'None'}\n"
                            f"🛡️ **Resist:** {bs.incoming_resist or 'None'}"
                        )
                        if traits:
                            stats += "\n" + " • ".join(traits)
                        self.container.add_item(discord.ui.TextDisplay(stats))
                    world_block = ""
                    if self.c.location:
                        world_block += f"📍 **Location:** **[{self.c.location.name}]({self.c.location.url})**\n"
                    if self.c.allies:
                        world_block += f"👥 **Allies:** {self.outer._format_view_list(self.c.allies, limit=6)}"
                    if world_block:
                        self.container.add_item(
                            discord.ui.TextDisplay("### 🌍 World Presence\n" + world_block)
                        )

                def _render_cheats(self):
                    """Render the cheats page."""
                    self.container.add_item(
                        discord.ui.TextDisplay(f"## 🧠 Boss Cheats")
                    )
                    self.container.add_item(discord.ui.Separator())
                    if self.c.cheats:
                        # Parse cheats to handle both quoted and plain text formats
                        all_cheats = self.outer._parse_cheats(self.c.cheats)
                        displayed_cheats = all_cheats[:4]
                        
                        # Truncate individual cheats to 400 chars if they're very long
                        truncated_cheats = []
                        for cheat in displayed_cheats:
                            if len(cheat) > 400:
                                truncated_cheats.append(cheat[:400] + "...")
                            else:
                                truncated_cheats.append(cheat)
                        
                        cheats_text = "\n\n".join(f"• {cheat}" for cheat in truncated_cheats)
                        if len(all_cheats) > 4:
                            cheats_text += f"\n\n*...and {len(all_cheats) - 4} more cheats*"
                        
                        # Final truncation to stay under Discord's 4000 char limit
                        if len(cheats_text) > 3900:
                            cheats_text = cheats_text[:3850] + "\n*...(truncated)*"
                        
                        self.container.add_item(discord.ui.TextDisplay(cheats_text))
                    else:
                        self.container.add_item(
                            discord.ui.TextDisplay("*No cheats documented.*")
                        )

                def _render_drops(self):
                    """Render the drops page."""
                    self.container.add_item(
                        discord.ui.TextDisplay(f"## 💰 Drops")
                    )
                    self.container.add_item(discord.ui.Separator())
                    if self.c.drops:
                        drop_lines = []
                        displayed_cats = list(self.c.drops.items())[:5]
                        for cat, items in displayed_cats:
                            item_list = self.outer._format_view_list(items, limit=3)
                            drop_lines.append(f"**{cat}**\n{item_list}")
                        drops_text = "\n\n".join(drop_lines)
                        if len(self.c.drops) > 5:
                            drops_text += f"\n\n*...and {len(self.c.drops) - 5} more categories*"
                        
                        # Truncate if necessary to stay under Discord's 4000 char limit
                        if len(drops_text) > 3900:
                            drops_text = drops_text[:3850] + "\n*...(truncated)*"
                        
                        self.container.add_item(discord.ui.TextDisplay(drops_text))
                    else:
                        self.container.add_item(
                            discord.ui.TextDisplay("*No drops documented.*")
                        )

                def _add_footer(self):
                    """Add pagination buttons and WizWiki branding footer."""
                    # Add footer separator and branding to container
                    self.container.add_item(discord.ui.Separator())
                    footer_text = f"🔗 [{self.outer.FOOTER_TEXT}]({self.outer.WIZWIKI_REPO})"
                    self.container.add_item(discord.ui.TextDisplay(footer_text))
                    
                    # Add pagination and navigation buttons
                    buttons = []
                    prev_btn = discord.ui.Button(
                        label="◀ Prev",
                        style=discord.ButtonStyle.secondary,
                        disabled=(self.current_page == 0)
                    )
                    prev_btn.callback = self._on_previous
                    buttons.append(prev_btn)
                    page_label = f"{self.pages[self.current_page].title()} ({self.current_page + 1}/{len(self.pages)})"
                    page_btn = discord.ui.Button(
                        label=page_label,
                        style=discord.ButtonStyle.primary,
                        disabled=True
                    )
                    buttons.append(page_btn)
                    next_btn = discord.ui.Button(
                        label="Next ▶",
                        style=discord.ButtonStyle.secondary,
                        disabled=(self.current_page == len(self.pages) - 1)
                    )
                    next_btn.callback = self._on_next
                    buttons.append(next_btn)
                    wiki_btn = discord.ui.Button(
                        label="Wiki",
                        url=self.c.url,
                        emoji="🔗"
                    )
                    buttons.append(wiki_btn)
                    if not self.is_public:
                        pub_btn = discord.ui.Button(
                            label="Publicize",
                            style=discord.ButtonStyle.success,
                            emoji="📢"
                        )
                        pub_btn.callback = self._on_publicize
                        buttons.append(pub_btn)
                    self.add_item(discord.ui.ActionRow(*buttons))

                async def _on_previous(self, interaction: discord.Interaction):
                    if self.current_page > 0:
                        self.current_page -= 1
                        self._render_page()
                        await interaction.response.edit_message(view=self)

                async def _on_next(self, interaction: discord.Interaction):
                    if self.current_page < len(self.pages) - 1:
                        self.current_page += 1
                        self._render_page()
                        await interaction.response.edit_message(view=self)

                async def _on_publicize(self, interaction: discord.Interaction):
                    if self.is_public:
                        return
                    self.is_public = True
                    self._render_page()
                    # Edit immediately to remove/disable the button and prevent spam
                    await interaction.response.edit_message(view=self)
                    # Then perform the heavy lifting of sending the public message
                    await self.outer._creature_logic(interaction, self.c, ephemeral=False)

            msg = {"view": CreatureLayout(c, img_url, self, accent_color, is_public=not ephemeral)}
            if file:
                msg["file"] = file
            if ephemeral:
                await interaction.followup.send(**msg)
            else:
                await interaction.channel.send(**msg)
        except Exception as e:
            self.logger.exception(f"Creature error: {e}")
            await interaction.followup.send("❌ Error fetching creature.", ephemeral=True)

    @app_commands.command(name="spell", description="Detailed info for a Wizard101 spell.")
    async def _spell(self, interaction: discord.Interaction, name: str):
        await self._spell_logic(interaction, name, ephemeral=True)

    async def _spell_logic(self, interaction: discord.Interaction, name_or_obj, ephemeral: bool = True):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=ephemeral)
        try:
            if isinstance(name_or_obj, str):
                s = await wizwiki.spell(name_or_obj)
            else:
                s = name_or_obj
            files = []
            c_file, c_url = await self._fetch_as_file(s.card_image_url, "card.png")
            a_file, a_url = await self._fetch_as_file(s.animation_gif_url, "anim.gif")
            if c_file: files.append(c_file)
            if a_file: files.append(a_file)
            # Determine accent color based on school
            accent_color = self._school_color(s.school)
            school_icon = self.SCHOOL_ICONS.get(s.school, "✨")

            class SpellLayout(discord.ui.LayoutView):
                def __init__(self, s, c_url, a_url, outer, accent_color, icon, is_public=False):
                    super().__init__()
                    self.s = s
                    self.c_url = c_url
                    self.a_url = a_url
                    self.outer = outer
                    self.accent_color = accent_color
                    self.icon = icon
                    self.is_public = is_public
                    self._render()

                def _render(self):
                    self.clear_items()
                    self.container = discord.ui.Container(accent_color=self.accent_color)
                    header = f"## {self.icon} {self.s.name}"
                    desc = self.s.description or "*No description available.*"
                    if self.c_url:
                        self.container.add_item(
                            discord.ui.Section(
                                f"{header}\n{desc}",
                                accessory=discord.ui.Thumbnail(self.c_url)
                            )
                        )
                    else:
                        self.container.add_item(discord.ui.TextDisplay(f"{header}\n{desc}"))
                    pvp_icon = "⚔️ PvP" if self.s.is_pvp else "🕊️ PvE Only"
                    school = self.s.school or "Unknown"
                    stats = (
                        f"### 📊 Spell Stats\n"
                        f"{self.icon} **School:** {school}\n"
                        f"⚡ **Pip Cost:** {self.s.pip_cost or '—'}\n"
                        f"✨ **School Pips:** {self.s.school_pip_cost or '—'}\n"
                        f"🎯 **Accuracy:** {self.s.accuracy or '—'}\n"
                        f"⚖️ **Mode:** {pvp_icon}"
                    )
                    self.container.add_item(discord.ui.TextDisplay(stats))
                    if self.s.type_icons:
                        types = " • ".join(self.s.type_icons)
                        self.container.add_item(
                            discord.ui.TextDisplay(f"🧩 **Spell Type:** {types}")
                        )
                    self.container.add_item(discord.ui.Separator())
                    if self.a_url:
                        self.container.add_item(
                            discord.ui.MediaGallery(
                                discord.MediaGalleryItem(
                                    self.a_url,
                                    description="Spell Cast Animation"
                                )
                            )
                        )
                    if self.s.can_be_trained or self.s.trainers:
                        train_text = "### 🎓 Training"
                        if self.s.training_points_cost:
                            train_text += f"\n💠 **Cost:** {self.s.training_points_cost} Training Points"
                        if self.s.trainers:
                            trainers = "\n".join(
                                f"• **[{t.name}]({t.url})**"
                                for t in self.s.trainers[:5]
                            )
                            train_text += f"\n👤 **Trainers:**\n{trainers}"
                        if self.s.training_requirements:
                            train_text += f"\n📜 **Requirements:** {self.s.training_requirements}"
                        self.container.add_item(discord.ui.TextDisplay(train_text))
                    if self.s.prerequisites:
                        prereqs = "\n".join(
                            f"• **[{p.name}]({p.url})**"
                            for p in self.s.prerequisites[:6]
                        )
                        self.container.add_item(
                            discord.ui.TextDisplay(
                                f"### 🔗 Prerequisite Spells\n{prereqs}"
                            )
                        )
                    if self.s.acquisition_sources:
                        quests = "\n".join(
                            f"• **[{q.name}]({q.url})**"
                            for q in self.s.acquisition_sources[:8]
                        )
                        self.container.add_item(
                            discord.ui.TextDisplay(
                                f"### 📜 Quest Rewards\n{quests}"
                            )
                        )
                    if self.s.spellement_acquirable:
                        self.container.add_item(
                            discord.ui.TextDisplay(
                                "🧬 **Spellement Upgrade Available**"
                            )
                        )
                    self.add_item(self.container)
                    self.add_item(
                        discord.ui.ActionRow(
                            discord.ui.Button(
                                label="Powered by WizWiki",
                                url="https://github.com/Angle-Brackets/WizWiki",
                                emoji="🔗"
                            ),
                            discord.ui.Button(
                                label="View on Wiki",
                                url=self.s.url
                            )
                        )
                    )
                    if not self.is_public:
                        pub_btn = discord.ui.Button(
                            label="Publicize",
                            style=discord.ButtonStyle.success,
                            emoji="📢"
                        )
                        pub_btn.callback = self._on_publicize
                        self.add_item(discord.ui.ActionRow(pub_btn))

                async def _on_publicize(self, interaction: discord.Interaction):
                    if self.is_public:
                        return
                    self.is_public = True
                    self._render()
                    await interaction.response.edit_message(view=self)
                    await self.outer._spell_logic(interaction, self.s, ephemeral=False)

            msg = {"view": SpellLayout(s, c_url, a_url, self, accent_color, school_icon, is_public=not ephemeral)}
            if files: msg["files"] = files
            if ephemeral:
                await interaction.followup.send(**msg)
            else:
                await interaction.channel.send(**msg)
        except Exception as e:
            self.logger.exception(f"Spell error: {e}")
            await interaction.followup.send("❌ Spell not found.", ephemeral=True)

    @app_commands.command(name="item", description="Full stats and source info for an item.")
    async def _item(self, interaction: discord.Interaction, name: str):
        await self._item_logic(interaction, name, ephemeral=True)

    async def _item_logic(self, interaction: discord.Interaction, name_or_obj, ephemeral: bool = True):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=ephemeral)
        try:
            if isinstance(name_or_obj, str):
                i = await wizwiki.item(name_or_obj)
            else:
                i = name_or_obj
            file, thumb_url = await self._fetch_as_file(i.image_male_url or i.image_female_url, "item.png")

            class ItemLayout(discord.ui.LayoutView):
                def __init__(self, i, t_url, outer, is_public=False):
                    super().__init__()
                    self.i = i
                    self.t_url = t_url
                    self.outer = outer
                    self.is_public = is_public
                    self._render()

                def _render(self):
                    self.clear_items()
                    self.container = discord.ui.Container(accent_color=0xe74c3c)
                    header = f"## ⚔️ {self.i.name}\n**Type:** {self.i.item_type} | **Lvl:** {self.i.level_requirement or 0}+"
                    if self.t_url:
                        self.container.add_item(discord.ui.Section(header, accessory=discord.ui.Thumbnail(self.t_url)))
                    else:
                        self.container.add_item(discord.ui.TextDisplay(header))
                    if self.i.stats:
                        self.container.add_item(discord.ui.TextDisplay("### 📈 Combat Stats\n" + self.outer._clean_stats(self.i.stats)))
                    if self.i.item_cards:
                        self.container.add_item(discord.ui.TextDisplay("### 🎴 Item Cards\n" + " • ".join(self.i.item_cards)))
                    econ = f"**Sell Price:** {self.i.vendor_sell_price or 0} Gold\n" \
                           f"**Auctionable:** {'✅' if self.i.is_auctionable else '❌'} | **Tradeable:** {'✅' if self.i.is_tradeable else '❌'}"
                    self.container.add_item(discord.ui.TextDisplay("### 💰 Economy\n" + econ))
                    if self.i.dropped_by:
                        self.container.add_item(discord.ui.TextDisplay("### 🎯 Dropped By\n" + self.outer._format_view_list(self.i.dropped_by)))
                    self.add_item(self.container)
                    self.add_item(discord.ui.ActionRow(
                        discord.ui.Button(label="Powered by WizWiki", url="https://github.com/Angle-Brackets/WizWiki", emoji="🔗"),
                        discord.ui.Button(label="Wiki Page", url=self.i.url)
                    ))
                    if not self.is_public:
                        pub_btn = discord.ui.Button(
                            label="Publicize",
                            style=discord.ButtonStyle.success,
                            emoji="📢"
                        )
                        pub_btn.callback = self._on_publicize
                        self.add_item(discord.ui.ActionRow(pub_btn))

                async def _on_publicize(self, interaction: discord.Interaction):
                    if self.is_public:
                        return
                    self.is_public = True
                    self._render()
                    await interaction.response.edit_message(view=self)
                    await self.outer._item_logic(interaction, self.i, ephemeral=False)

            msg = {"view": ItemLayout(i, thumb_url, self, is_public=not ephemeral)}
            if file: msg["file"] = file
            if ephemeral:
                await interaction.followup.send(**msg)
            else:
                await interaction.channel.send(**msg)
        except Exception:
            await interaction.followup.send("❌ Item not found.", ephemeral=True)

    @app_commands.command(name="recipe", description="Crafting requirements and vendors.")
    async def _recipe(self, interaction: discord.Interaction, name: str):
        await self._recipe_logic(interaction, name, ephemeral=True)

    async def _recipe_logic(self, interaction: discord.Interaction, name_or_obj, ephemeral: bool = True):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=ephemeral)
        try:
            if isinstance(name_or_obj, str):
                r = await wizwiki.recipe(name_or_obj)
            else:
                r = name_or_obj
            class RecipeLayout(discord.ui.LayoutView):
                def __init__(self, r, outer, is_public=False):
                    super().__init__()
                    self.r = r
                    self.outer = outer
                    self.is_public = is_public
                    self._render()

                def _render(self):
                    self.clear_items()
                    self.container = discord.ui.Container(accent_color=0x9b59b6)
                    self.container.add_item(discord.ui.TextDisplay(f"## 🛠️ Recipe: {self.r.name}\n**Station:** {self.r.crafting_station}"))
                    if self.r.vendors:
                        vendors = "\n".join([f"• **[{v.name}]({v.url})**" for v in self.r.vendors])
                        self.container.add_item(discord.ui.TextDisplay("### 👤 Vendors\n" + vendors))
                    if self.r.cost:
                        self.container.add_item(discord.ui.TextDisplay(f"### 💰 Cost\n**{self.r.cost} Gold**"))
                    if self.r.ingredients:
                        ing = "\n".join([f"• x{count} **{name}**" for name, count in self.r.ingredients.items()])
                        self.container.add_item(discord.ui.TextDisplay("### 📦 Ingredients\n" + ing))
                    self.add_item(self.container)
                    self.add_item(discord.ui.ActionRow(
                        discord.ui.Button(label="Powered by WizWiki", url="https://github.com/Angle-Brackets/WizWiki", emoji="🔗"),
                        discord.ui.Button(label="Wiki Page", url=self.r.url)
                    ))
                    if not self.is_public:
                        pub_btn = discord.ui.Button(
                            label="Publicize",
                            style=discord.ButtonStyle.success,
                            emoji="📢"
                        )
                        pub_btn.callback = self._on_publicize
                        self.add_item(discord.ui.ActionRow(pub_btn))

                async def _on_publicize(self, interaction: discord.Interaction):
                    if self.is_public:
                        return
                    self.is_public = True
                    self._render()
                    await interaction.response.edit_message(view=self)
                    await self.outer._recipe_logic(interaction, self.r, ephemeral=False)

            msg = {"view": RecipeLayout(r, self, is_public=not ephemeral)}
            if ephemeral:
                await interaction.followup.send(**msg)
            else:
                await interaction.channel.send(**msg)
        except Exception as e:
            self.logger.exception(f"Recipe error: {e}")
            await interaction.followup.send("❌ Recipe not found.", ephemeral=True)

    @app_commands.command(name="location", description="Details about a world or area.")
    async def _location(self, interaction: discord.Interaction, name: str):
        await self._location_logic(interaction, name, ephemeral=True)

    async def _location_logic(self, interaction: discord.Interaction, name_or_obj, ephemeral: bool = True):
        if not interaction.response.is_done():
            await interaction.response.defer(ephemeral=ephemeral)
        try:
            if isinstance(name_or_obj, str):
                loc = await wizwiki.location(name_or_obj)
            else:
                loc = name_or_obj
            map_file = None
            map_url = None
            if loc.map_url:
                map_file, map_url = await self._fetch_as_file(loc.map_url, "map.png")

            class LocationLayout(discord.ui.LayoutView):
                def __init__(self, l: wizwiki.Location, map_url, outer, is_public=False):
                    super().__init__()
                    self.l = l
                    self.map_url = map_url
                    self.outer = outer
                    self.is_public = is_public
                    self._render()

                def _render(self):
                    self.clear_items()
                    self.container = discord.ui.Container(accent_color=0xe67e22)
                    header = f"## 📍 {self.l.name}"
                    desc = self.l.description or "*No description available.*"
                    if self.map_url:
                        self.container.add_item(
                            discord.ui.Section(
                                f"{header}\n{desc}",
                                accessory=discord.ui.Thumbnail(self.map_url)
                            )
                        )
                    else:
                        self.container.add_item(
                            discord.ui.TextDisplay(f"{header}\n{desc}")
                        )
                    self.container.add_item(discord.ui.Separator())
                    if self.l.parents:
                        parents = "\n".join(
                            f"• **[{p.name}]({p.url})**"
                            for p in self.l.parents[:5]
                        )
                        self.container.add_item(
                            discord.ui.TextDisplay(
                                f"### 🌍 Parent Locations\n{parents}"
                            )
                        )
                    if self.l.sublocations:
                        subs = "\n".join(
                            f"• **[{s.name}]({s.url})**"
                            for s in self.l.sublocations[:10]
                        )
                        self.container.add_item(
                            discord.ui.TextDisplay(
                                f"### 🏘️ Sub-Areas\n{subs}"
                            )
                        )
                    if self.l.connections:
                        conns = "\n".join(
                            f"• **[{c.name}]({c.url})**"
                            for c in self.l.connections[:10]
                        )
                        self.container.add_item(
                            discord.ui.TextDisplay(
                                f"### 🧭 Connected Locations\n{conns}"
                            )
                        )
                    if self.map_url:
                        self.container.add_item(discord.ui.Separator())
                        self.container.add_item(
                            discord.ui.MediaGallery(
                                discord.MediaGalleryItem(
                                    self.map_url,
                                    description="Area Map"
                                )
                            )
                        )
                    self.add_item(self.container)
                    self.add_item(
                        discord.ui.ActionRow(
                            discord.ui.Button(
                                label="Powered by WizWiki",
                                url="https://github.com/Angle-Brackets/WizWiki",
                                emoji="🔗"
                            ),
                            discord.ui.Button(
                                label="View on WizWiki",
                                url=self.l.url
                            )
                        )
                    )
                    if not self.is_public:
                        pub_btn = discord.ui.Button(
                            label="Publicize",
                            style=discord.ButtonStyle.success,
                            emoji="📢"
                        )
                        pub_btn.callback = self._on_publicize
                        self.add_item(discord.ui.ActionRow(pub_btn))

                async def _on_publicize(self, interaction: discord.Interaction):
                    if self.is_public:
                        return
                    self.is_public = True
                    self._render()
                    await interaction.response.edit_message(view=self)
                    await self.outer._location_logic(interaction, self.l, ephemeral=False)

            msg = {"view": LocationLayout(loc, map_url, self, is_public=not ephemeral)}
            if map_file:
                msg["file"] = map_file
            if ephemeral:
                await interaction.followup.send(**msg)
            else:
                await interaction.channel.send(**msg)
        except Exception as e:
            self.logger.exception(f"Location error: {e}")
            await interaction.followup.send("❌ Location not found.", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Wiz(bot))