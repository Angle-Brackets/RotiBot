import discord
import urllib3

from bs4 import BeautifulSoup
from discord import app_commands
from discord.ext import commands
from discord.app_commands import Group

class Wiz(commands.GroupCog, group_name="wiz"):
    def __init__(self, bot : commands.Bot):
        super().__init__()
        self.bot = bot
        self.http = urllib3.PoolManager()

    search_group = Group(name="search", description="Search for a specific query")

    @search_group.command(name="mob", description="List the statistics for a monster.")
    async def _search_mob(self, interaction : discord.Interaction, query : str):
        await interaction.response.defer()
        req = self.http.request('GET', f'http://www.wizard101central.com/wiki/Creature:{query}')
        soup = BeautifulSoup(req.data, "html.parser")

        battle_info = soup.find(class_="data-table").children #Gets the health, resist, etc.
        for thing in battle_info:
            if thing.text != "":
                await interaction.followup.send(thing.text)


async def setup(bot: commands.Bot):
    await bot.add_cog(Wiz(bot))