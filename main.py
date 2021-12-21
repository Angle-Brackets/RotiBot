#ROTI BOT V1.01 ALPHA
#BY SOUPA#0524, CURRENTLY WRITTEN IN PYTHON USING REPLIT DATABASE FOR DATA.

import discord
import os

from data import *
from webserver.keep_alive import keep_alive
from discord.utils import find
from discord.ext import commands
from discord_slash import SlashCommand, SlashContext
from cogs.motd import choose_motd

token = os.environ['TOKEN']

client = commands.Bot(command_prefix="prefix")
slash = SlashCommand(client, sync_commands=True, override_type=True)

@client.event
async def on_ready():
    print("Roti Bot Online, logged in as {0.user}".format(client))

    for guild in client.guilds:
        update_database(guild)
    
    await client.change_presence(activity=discord.Activity(name=choose_motd(), type=1))

@client.event
async def on_guild_join(guild):
    #tries to find a general channel in the discord to send this in.
    general = find(lambda x: x.name == 'general', guild.text_channels)
    if general and general.permissions_for(guild.me).send_messages:
        await general.send('Hello {0}, I\'m Roti! Thank you for adding me to this guild. You can check my commands by doing %commands. Wait a moment while I prepare my database for this server...'.format(guild.name))
        res = update_database(guild)
        await general.send(res)
    else:
        #if there is none, finds first text channel it can speak in.
        for channel in guild.text_channels:
            if channel.permissions_for(guild.me).send_messages:
                await channel.send('Hello {0}, I\'m Roti! Thank you for adding me to this guild. You can check my commands by doing %commands. Wait a moment while I prepare my database for this server...'.format(guild.name))
                res = update_database(guild)
                await channel.send(res)
                break

@slash.slash(description="Shows the bot's latency")
async def ping(ctx):
    await ctx.send(f'Pong! ({round(client.latency * 1000)}ms)')

#Just debug functions, only I can use them.
@client.event
async def on_message(message):
    if message.author == client.user:
        return
    
    msg = message.content

    if message.author.id == (163045781316698112):
        if msg.startswith("$print_phrases"):  
            print(get_data(message.guild.id))  
            await message.channel.send(get_data(message.guild.id))
        elif msg.startswith("$del_phrases"):
            await message.channel.send("Clearing all phrases from server...")
            delete_guild_entry(message.guild.id)
            update_database(message.guild)
            await message.channel.send("Successfully cleared phrase database for this guild.")
        elif msg.startswith("$shuffle_status"):
            await client.change_presence(activity=discord.Activity(name=choose_motd(), type=1))
            await message.channel.send("Shuffled!")
        elif msg.startswith("$update_msg"):
            update = msg[len("$update_msg"):] #actual update message
            guild_list = client.guilds[:] #Each guild is removed if it has some general channel and successfully sent the update, the remaining ones go into the more general algorithm that just finds the first channel the bot can send messages in.

            for guild in client.guilds:
                general = find(lambda x: x.name == 'general' or "general" in x.name, guild.text_channels)
                if general and general.permissions_for(guild.me).send_messages:
                    await general.send(update)
                    guild_list.remove(guild)
            
            for j in range(len(guild_list)):
                for channel in guild_list[j].text_channels:
                    if channel.permissions_for(guild.me).send_messages:
                        await channel.send(update)
                

        
keep_alive()

#registers all of the commands located in the cogs folder
if __name__ == '__main__':
    for cog_file in os.listdir("./cogs"):
        if cog_file.endswith(".py"):
            client.load_extension("cogs.{0}".format(cog_file[0:cog_file.index(".py")]))

client.run(token)