#ROTI BOT V1.9.4 ALPHA (2025 - 01 - 17)
#BY @soupa., CURRENTLY WRITTEN IN PYTHON USING MONGO DATABASE FOR DATA.

import discord
import aiohttp
import os
import wavelink
import argparse
import logging

from dotenv import load_dotenv
from discord.ext import commands
from discord.utils import find
from data import update_database, delete_guild_entry

#load credentials
load_dotenv(".env")
class Roti(commands.Bot):
    def __init__(self):
        logging.basicConfig(level="INFO")
        self.logger = logging.getLogger(__name__)

        # Flags to disable features during testing
        self.parser = argparse.ArgumentParser()
        self.parser.add_argument("--nomusic", action=argparse.BooleanOptionalAction, help="Disable Music Functionality")
        self.parser.add_argument("--test", action=argparse.BooleanOptionalAction, help="Enable testing mode")
        self.args = self.parser.parse_args()

        self.test_build = bool(self.args.test)

        super().__init__(
            command_prefix = "$",
            intents = discord.Intents.all(),
            application_id = os.getenv('APPLICATION_ID') if not self.test_build else os.getenv('TEST_APPLICATION_ID')
        )

    async def on_ready(self):
        self.logger.info("Roti Bot Online, logged in as %s", self.user)

    async def setup_hook(self):
        self.session = aiohttp.ClientSession()
        for cog_file in os.listdir("./cogs"):
            if cog_file.endswith(".py"):
                await self.load_extension(f"cogs.{cog_file[:-3]}")

        # Music bot setup
        if not self.args.nomusic:
            nodes = [wavelink.Node(uri=fr"http://{os.getenv("MUSIC_IP")}:2333", password=os.getenv("MUSIC_PASS"))]
            await wavelink.Pool.connect(nodes=nodes, client=self, cache_capacity=100)
        else:
            self.logger.warning("Music Functionality is Disabled!")

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
        self.logger.critical("Deleted guild %s's data.", guild.name)

roti = Roti()
roti.run(os.getenv('TOKEN') if not roti.test_build else os.getenv('TEST_TOKEN'))