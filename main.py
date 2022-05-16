#ROTI BOT V1.3 ALPHA
#BY SOUPA#0524, CURRENTLY WRITTEN IN PYTHON USING MONGO DATABASE FOR DATA.
#Currently uses discord.py 2.0, which must be manually installed from the git.
import discord
import aiohttp
import os

from dotenv import load_dotenv
from discord.ext import commands

#load credentials
load_dotenv(".env")

class Roti(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix = "prefix",
            intents = discord.Intents.all(),
            application_id = os.getenv('APPLICATION_ID')
        )

    async def on_ready(self):
        print("Roti Bot Online, logged in as {0.user}".format(self))

    async def setup_hook(self):
        self.session = aiohttp.ClientSession()
        for cog_file in os.listdir("./cogs"):
            if cog_file.endswith(".py"):
                await self.load_extension(f"cogs.{cog_file[:-3]}")

        await roti.tree.sync()

    async def close(self):
        await super().close()
        await self.session.close()

roti = Roti()
roti.run(os.getenv('TOKEN'))