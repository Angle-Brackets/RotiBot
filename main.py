import discord
import os
from settings import *
from webserver.keep_alive import keep_alive
from discord.utils import find


token = os.environ['TOKEN']

client = discord.Client()

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

@client.event
async def on_message(message):
    if message.author == client.user:
        return
    
    msg = message.content
    res = detect_response(message.guild, msg)

    if msg.startswith("$print_phrases"):    
        await message.channel.send(get_phrases(message.guild.id))
    if msg.startswith("$del_phrases"):
        delete_guild_entry(message.guild.id)
    if msg.startswith("%new_talkback"):
        channel = message.channel
        author = message.author
        await channel.send("Please type the appropriate response for this trigger phrase below.")

        def check(m):
            return m.channel == channel and m.author == author
        
        response = await client.wait_for('message', check=check)
   
        notif = add_talkback_phrase(message.guild.id, msg, response.content if len(response.attachments) == 0 else response.attachments[0].url)

        await message.channel.send(notif)        

    if msg.startswith("%remove_talkback"):
        notif = remove_talkback(message.guild.id, msg)
        await message.channel.send(notif)
    elif res is not None:
        await message.channel.send(res)
        
keep_alive()
client.run(token)