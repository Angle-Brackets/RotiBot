#make sure to install wikipedia api and beautifulsoup4 idiot
import discord
import requests
import json

import wikipediaapi as wiki

from discord import app_commands
from discord.ext import commands
from bs4 import BeautifulSoup

#generates a random page.
def _generate_random_page():
    url = str()
    url = requests.get("https://en.wikipedia.org/wiki/Special:Random")
    soup = BeautifulSoup(url.content, "html.parser")
    title = soup.find(class_="firstHeading").text

    image = json.loads(requests.get(f"https://en.wikipedia.org/w/api.php?action=query&format=json&formatversion=2&prop=pageimages|pageterms&piprop=thumbnail&pithumbsize=600&pilicense=any&titles={title}").content)
    try:
        image = image["query"]["pages"][0]["thumbnail"]["source"] # Trust me this works.
    except:
        image = "https://upload.wikimedia.org/wikipedia/en/thumb/8/80/Wikipedia-logo-v2.svg/600px-Wikipedia-logo-v2.svg.png"
    return title, image

#generates a page's embed with the given wikipedia page argument!
def _generate_page(page):
    text = page.text if len(page.text) < 4000 else page.text[0:4000] + "..."
    text = _find_sections(page.sections, text)

    image = json.loads(requests.get(
        f"https://en.wikipedia.org/w/api.php?action=query&format=json&formatversion=2&prop=pageimages|pageterms&piprop=thumbnail&pithumbsize=600&pilicense=any&titles={page.title.replace(" ", "_")}").content)
    try:
        image = image["query"]["pages"][0]["thumbnail"]["source"]  # Trust me this works.
    except:
        image = "https://upload.wikimedia.org/wikipedia/en/thumb/8/80/Wikipedia-logo-v2.svg/600px-Wikipedia-logo-v2.svg.png"

    embed = discord.Embed(title=page.title, description=text, color=0xecc98e, url=f"https://en.wikipedia.org/wiki/{page.title.replace(" ", "_")}")
    embed.set_thumbnail(url=image)
    embed.add_field(name="Want to read more?", value=f"[Article](https://en.wikipedia.org/wiki/{page.title.replace(" ", "_")})")
    return embed

#Used to correctly highlight sections of the article, main headings are bolded and subheadings are italicized.
def _find_sections(sections, text, level = 0):
    for s in sections:
        prev = text
        text = text.replace(s.title, f"**{s.title}**" if level == 0 else f"*{s.title}*")
        # This implies that we have reached a section that is not displayed, so we stop
        if prev is text:
            break
        level += 1
        _find_sections(s.sections, text, level)
    return text

class Wikipedia(commands.GroupCog, group_name="wikipedia"):
    def __init__(self, bot : commands.Bot):
        super().__init__()
        self.user_agent = "RotiBot/1.0"
        self.bot = bot
        self.wiki_search = wiki.Wikipedia(user_agent=self.user_agent, language="en", extract_format=wiki.ExtractFormat.WIKI)

    @app_commands.command(name="random", description="Grabs a random wikipedia article.")
    async def _wiki_random(self, interaction : discord.Interaction):
        await interaction.response.defer()
        page, image = None, None

        # Will keep trying until it generates a wikipedia page that exists.
        while page is None or image is None or not page.exists():
            page, image = _generate_random_page()
            try:
                page = self.wiki_search.page(page)
            except:
                await interaction.followup.send("Unable to retrieve wikipedia pages, try again later.")
                return

        text = page.text if len(page.text) < 4000 else page.text[0:4000] + "..."
        text = _find_sections(page.sections, text)

        embed = discord.Embed(title=page.title, description=text, color=0xecc98e,url=f"https://en.wikipedia.org/wiki/{page.title.replace(" ", "_")}")
        embed.set_thumbnail(url=image)
        embed.add_field(name="Want to read more?", value=f"[Article](https://en.wikipedia.org/wiki/{page.title.replace(" ", "_")})")

        view = DisambNav()
        view.message = await interaction.followup.send(embed=embed, view=view)
        view.message = await interaction.original_response()

        await view.wait()

    #"All article disambiguation pages"
    @app_commands.command(name="search", description="Find a particular wikipedia article")
    async def _search(self, interaction : discord.Interaction, query : str):
        await interaction.response.defer()
        try:
            page = self.wiki_search.page(query)
        except:
            await interaction.followup.send("Unable to retrieve wikipedia pages, try again later.")
            return

        #This means that the page is a disambiguation page, not a proper page.
        if "Category:All article disambiguation pages" in list(page.categories.keys()):
            page_embed = discord.Embed(title="Did you mean...", color=0xecc98e)
            page_links = page.links
            view = DisambNav(page_links)

            #Max of 25 elements allowed.
            count = 0
            if count < 25:
                for new_page, page_data in page_links.items():
                    page_embed.add_field(name=new_page, value=page_data.summary[0:100] + "...", inline=False)
                    count += 1
            view.message = await interaction.followup.send(embed=page_embed, view=view)
            view.message = await interaction.original_response()

            await view.wait()
        else:
            view = DisambNav()
            view.message = await interaction.followup.send(embed=_generate_page(page), view=view)
            view.message = await interaction.original_response()

            await view.wait()

def _generate_options(choices):
    select_list = list()
    choice_list = list(choices.keys())[0:24]
    for choice in choice_list:
        select_list.append(discord.SelectOption(label=choice))
    return select_list

class DisambNav(discord.ui.View):
    def __init__(self, choices = None):
        super().__init__()
        self.timeout = 60
        if choices is not None:
            self.choices = choices
            self._article_select.options = _generate_options(self.choices)
        else:
            self.remove_item(self._article_select)

    @discord.ui.select(min_values=1, options=[], placeholder="Select an Article")
    async def _article_select(self, interaction : discord.Interaction, selection : discord.ui.Select):
        choice = selection.values[0]
        page = self.choices[choice]

        await interaction.response.edit_message(embed=_generate_page(page))

    @discord.ui.button(label='Cancel', style=discord.ButtonStyle.danger)
    async def _cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.message.delete()
        self.stop()

    async def on_timeout(self) -> None:
        await self.message.delete()
        self.stop()

async def setup(bot: commands.Bot):
    await bot.add_cog(Wikipedia(bot))

