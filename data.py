import os
import time
import traceback

from pymongo import MongoClient
from dotenv import load_dotenv
from time import strftime, gmtime

load_dotenv(".env")
cluster = MongoClient(os.getenv('DATABASE'))

collections = cluster["Roti"]["data"]  # Actual MongoDB database
db = dict()  # quick access to data, but must be updated when values changed
bot_start_time = time.time()  # Used to calculate the uptime for the bot.

# Takes data, puts into variable named db and keys the data using the serverID
for data in collections.find({}):
    db[data['server_id']] = data

# To get a server's data, you need to do db[<server_id>][<category>] (ID IS NOT A STRING!)

# This is like a template for the data.
DATA_STRUCTURE = {
    "server_id": -1,
    "banned_phrases": [],
    "trigger_phrases": [],
    "response_phrases": [],
    "quotes": [],
    "motd": "",
    "music_queue": [],  # I would like to use a queue here..but there is a circular logic error that stops me
    "settings": {
        "talkback": {
            "enabled": True,  # Whether talkbacks are enabled
            "duration": 0,  # How long the message exists before being deleted, 0 is permanent.
            "strict": False,
            # Dictates if the bot will only look at substrings when responding, or will need EXACT matches of words to respond. (case ignored in both)
            "res_probability": 100  # Percentage that the bot will respond to a talkback
        },

        "music": {
            "looped": False,  # If its looped...duh
            "speed": 1  # Speed of songs, x1 - x2 speed.
        }
    },
}


def update_database(guild):
    serverID = guild.id

    if serverID not in db.keys():
        temp = DATA_STRUCTURE
        temp['server_id'] = serverID
        collections.insert_one(temp)
        db[serverID] = temp
        return "Successfully created database entry for {0.name}. Have fun!".format(guild)


# Updates the database with the given key.
# Ex. passing key = "trigger_phrases" will appropriately update the trigger database for the given server
def push_data(serverID, key: str):
    try:
        collections.update_one({"server_id": serverID}, {"$set": {key: db[serverID][key]}})
    except Exception as e:
        raise ConnectionError("Unable to connect to database")

def delete_guild_entry(serverID):
    collections.delete_one({"server_id": serverID})
    db[serverID].clear()


def get_data(serverID):
    return db[str(serverID)]


def calculate_uptime():
    return strftime("%d:%H:%M:%S", gmtime(time.time() - bot_start_time))
