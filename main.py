#ROTI BOT V1.70 ALPHA
#BY SOUPA#0524, CURRENTLY WRITTEN IN PYTHON USING MONGO DATABASE FOR DATA.
#Currently uses discord.py 2.0, which must be manually installed from the git.

import discord
import aiohttp
import os

from dotenv import load_dotenv
from discord.ext import commands
from discord.utils import find
from data import update_database, delete_guild_entry

#load credentials
load_dotenv(".env")
test_build = False
class Roti(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix = "prefix",
            intents = discord.Intents.all(),
            application_id = os.getenv('APPLICATION_ID') if not test_build else os.getenv('TEST_APPLICATION_ID')
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

    async def on_guild_join(self, guild : discord.Guild):
        # tries to find a general channel in the discord to send this in.
        general = find(lambda x: x.name == 'general', guild.text_channels)
        if general and general.permissions_for(guild.me).send_messages:
            await general.send(
                'Hello {0}, I\'m Roti! Thank you for adding me to this guild. You can check my commands by doing /help. Wait a moment while I prepare my database for this server...'.format(
                    guild.name))
            res = update_database(guild)
            await general.send(res)
        else:
            # if there is none, finds first text channel it can speak in.
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    await channel.send(
                        'Hello {0}, I\'m Roti! Thank you for adding me to this guild. You can check my commands by doing /help. Wait a moment while I prepare my database for this server...'.format(
                            guild.name))
                    res = update_database(guild)
                    await channel.send(res)
                    break

    async def on_guild_remove(self, guild : discord.Guild):
        delete_guild_entry(guild.id)
        print("Deleted guild " + guild.name + "'s data")

roti = Roti()
roti.run(os.getenv('TOKEN') if not test_build else os.getenv('TEST_TOKEN'))