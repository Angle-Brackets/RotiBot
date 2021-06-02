from replit import db
import re
import random

DATA_STRUCTURE = {
    "banned_phrases": [],
    "trigger_phrases": [],
    "response_phrases": [],
	"motd": "",
}


def update_phrase_database(guild):
    serverID = str(guild.id)

    if serverID not in db.keys():
        db[serverID] = DATA_STRUCTURE
        return "Successfully created database entry for {0.name}. Have fun!".format(guild)

    elif serverID in db.keys() and db[serverID].keys() != DATA_STRUCTURE.keys():
        if len(db[serverID].keys()) < len(DATA_STRUCTURE.keys()):
            db[serverID] = {**DATA_STRUCTURE, **db[serverID]}
            print("Successfully updated database in {0.name}".format(guild))
        elif len(db[serverID].keys()) >= len(DATA_STRUCTURE.keys()):
            tempDict = db[serverID]
            for key in db[serverID].keys():
                if key not in DATA_STRUCTURE.keys():
                    del tempDict[key]
            db[serverID] = tempDict
            print("Successfully updated database in {0.name}".format(guild))
    return "Failed to update database in {0.name}".format(guild)


def delete_guild_entry(serverID):
    if str(serverID) in db.keys():
        del db[str(serverID)]
        

def get_phrases(serverID):
    return db[str(serverID)]

def detect_response(guild, msg):
    serverID = str(guild.id)
    res = None

    if serverID in db.keys():
        #need to add what the bot would do if the word is banned
        for trigger_list in db[serverID]["trigger_phrases"]:
            for trigger in trigger_list:
                if trigger.casefold().strip() in msg.casefold():
                    res = random.choice(db[serverID]["response_phrases"][db[serverID]["trigger_phrases"].index(trigger_list)])
    return res
