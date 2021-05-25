import discord
import os
from settings import *
from webserver.keep_alive import keep_alive
from discord.utils import find
from discord_slash import SlashCommand, SlashCommandOptionType, SlashContext
from discord.ext import commands


token = os.environ['TOKEN']

client = discord.Client()
slash = SlashCommand(client, sync_commands=True)

@client.event
async def on_ready():
    print("Roti Bot Online, logged in as {0.user}".format(client))

    for guild in client.guilds:
        update_phrase_database(guild)

@client.event
async def on_guild_join(guild):
    #tries to find a general channel in the discord to send this in.
    general = find(lambda x: x.name == 'general',  guild.text_channels)
    if general and general.permissions_for(guild.me).send_messages:
        await general.send('Hello {0}, I\'m Roti! Thank you for adding me to this guild. You can check my commands by doing %commands. Wait a moment while I prepare my database for this server...'.format(guild.name))
        res = update_phrase_database(guild)
        await general.send(res)
    else:
        #if there is none, finds first text channel it can speak in.
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                await channel.send('Hello {0}, I\'m Roti! Thank you for adding me to this guild. You can check my commands by doing %commands. Wait a moment while I prepare my database for this server...'.format(guild.name))
                res = update_phrase_database(guild)
                await channel.send(res)
                break

@slash.slash(description="Shows the bot's latency")
async def ping(ctx):
    await ctx.send(f'Pong! ({round(client.latency * 1000)}ms)')

talkback_options = [
    {
        "name": "triggers",
        "description": "The words/phrases that activate the bot. ",
        "required": True,
        "type": 3,
    },
    {
        "name": "responses",
        "description": "The words/phrases that the bot responds with.",
        "required": True,
        "type": 3
    }
]

@slash.subcommand(base="talkback", name="add", description="Add talkback trigger/response pair", options=talkback_options)
async def _talkback_add(ctx: SlashContext, triggers = str, responses = str):
    await ctx.defer()
    notif = add_talkback_phrase(ctx.guild.id, str(triggers), str(responses))
    await ctx.send(notif)

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    
    msg = message.content
    res = detect_response(message.guild, msg)

    if msg.startswith("$print_phrases"):    
        await message.channel.send(get_phrases(message.guild.id))
    if msg.startswith("$del_phrases"):
        await message.channel.send("Clearing all phrases from server...")
        delete_guild_entry(message.guild.id)
        update_phrase_database(message.guild)
        await message.channel.send("Successfully cleared phrase database for this guild.")
    if msg.startswith("%remove_talkback"):
        notif = remove_talkback(message.guild.id, msg)
        await message.channel.send(notif)
    elif res is not None:
        await message.channel.send(res)
        
keep_alive()
client.run(token)