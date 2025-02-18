#ROTI BOT V1.9.5 ALPHA (2025 - 01 - 29)
#BY @soupa., CURRENTLY WRITTEN IN PYTHON USING MONGO DATABASE FOR DATA.

import discord
import aiohttp
import os
import wavelink
import argparse
import logging
import inspect
import importlib

from dotenv import load_dotenv
from discord.ext import commands
from discord.utils import find
from database.data import RotiDatabase
from returns.maybe import Some, Nothing, Maybe

#load credentials
load_dotenv(".env")
class Roti(commands.Bot):
    def __init__(self):
        logging.basicConfig(level="INFO")
        self.logger = logging.getLogger(__name__)
        self.parser = argparse.ArgumentParser() # Flags to enable/disable features during testing
        self._setup_cli_args()

        self.test_build = bool(self.args.test)
        self.db = RotiDatabase(os.getenv("DATABASE"))
        super().__init__(
            command_prefix = "$",
            intents = discord.Intents.all(),
            application_id = os.getenv('APPLICATION_ID') if not self.test_build else os.getenv('TEST_APPLICATION_ID')
        )

    async def on_ready(self):
        await self.wait_until_ready()
        self.logger.info("Roti Bot Online, logged in as %s", self.user)

    async def setup_hook(self):
        self.session = aiohttp.ClientSession()
        await self._load_cogs()

        # Music bot setup
        if not self.args.nomusic:
            await self._setup_music_functionality()
        else:
            self.logger.warning("Music Functionality is Disabled!")

        await roti.tree.sync()
    
    async def _load_cogs(self):
        show_output : bool = self.args.show_cog_load
        for root, _, files in os.walk("./cogs"):
            for file in files:
                if file.endswith(".py"):
                    relative_path = os.path.relpath(root, "./cogs").replace(os.sep, ".")
                    module_name = f"cogs.{relative_path}.{file[:-3]}" if relative_path != "." else f"cogs.{file[:-3]}"
                    
                    try:
                        module = importlib.import_module(module_name)
                        
                        # Check if any class is a tagged cog
                        is_cog = any(
                            getattr(obj, "is_cog", False)
                            for _, obj in inspect.getmembers(module, inspect.isclass)
                        )

                        if is_cog:
                            if show_output:
                                self.logger.info(f"Loading {module_name} as cog command module.")
                            await self.load_extension(module_name)
                        else:
                            if show_output:
                                self.logger.info(f"Skipping {module_name}")
                    
                    except Exception as e:
                        self.logger.error(f"Failed to load {module_name}: {e}")
        
    async def _setup_music_functionality(self):
        nodes = [wavelink.Node(uri=fr"http://{os.getenv("MUSIC_IP")}:2333", password=os.getenv("MUSIC_PASS"))]
        await wavelink.Pool.connect(nodes=nodes, client=self, cache_capacity=100)
    
    def _setup_cli_args(self):
        self.parser.add_argument("--nomusic", action=argparse.BooleanOptionalAction, help="Disable Music Functionality")
        self.parser.add_argument("--test", action=argparse.BooleanOptionalAction, help="Enable testing mode")
        self.parser.add_argument("--show-cog-load", "-scl", action=argparse.BooleanOptionalAction, help="Show what cogs are loaded during startup.")
        self.args = self.parser.parse_args()
        
    async def close(self):
        await super().close()
        await self.session.close()

    async def on_guild_join(self, guild : discord.Guild):
        # tries to find a general channel in the discord to send this in.
        general = find(lambda x: x.name == 'general', guild.text_channels)
        if general and general.permissions_for(guild.me).send_messages:
            await general.send(
                f'Hello {guild.name}, I\'m Roti! Thank you for adding me to this guild. You can check my commands by doing /help. Wait a moment while I prepare my database for this server...')
            res = self.db.update_database(guild)
            await general.send(res)
        else:
            # if there is none, finds first text channel it can speak in.
            for channel in guild.text_channels:
                if channel.permissions_for(guild.me).send_messages:
                    await channel.send(
                        f'Hello {guild.name}, I\'m Roti! Thank you for adding me to this guild. You can check my commands by doing /help. Wait a moment while I prepare my database for this server...')
                    res = self.db.update_database(guild)
                    await channel.send(res)
                    break

    async def on_guild_remove(self, guild : discord.Guild):
        match self.db.delete_guild_entry(guild.id):
            case Some(error):
                self.logger.critical("Failed to delete %s's data. ID: %i. Error: %s", guild.name, guild.id, error)
            case Maybe.empty:
                self.logger.critical("Deleted guild %s's data.", guild.name)

roti = Roti()
roti.run(os.getenv('TOKEN') if not roti.test_build else os.getenv('TEST_TOKEN'))