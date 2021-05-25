from replit import db
import re
import random

PHRASE_CATEGORIES = {
    "banned_phrases": [],
    "trigger_phrases": [],
    "response_phrases": [],
}


def update_phrase_database(guild):
    serverID = str(guild.id)

    if serverID not in db.keys():
        db[serverID] = PHRASE_CATEGORIES
        return "Successfully created database entry for {0.name}. Have fun!".format(guild)

    elif serverID in db.keys() and db[serverID].keys() != PHRASE_CATEGORIES.keys():
        if len(db[serverID].keys()) < len(PHRASE_CATEGORIES.keys()):
            db[serverID] = {**PHRASE_CATEGORIES, **db[serverID]}
            print("Successfully updated phrase database in {0.name}".format(guild))
        elif len(db[serverID].keys()) >= len(PHRASE_CATEGORIES.keys()):
            tempDict = db[serverID]
            for key in db[serverID].keys():
                if key not in PHRASE_CATEGORIES.keys():
                    del tempDict[key]
            db[serverID] = tempDict
            print("Successfully updated phrase database in {0.name}".format(guild))
    return "Failed to update phrase database in {0.name}".format(guild)


def delete_guild_entry(serverID):
    if str(serverID) in db.keys():
        del db[str(serverID)]
        

def get_phrases(serverID):
    return db[str(serverID)]

def add_talkback_phrase(serverID, trigger_phrases, response_phrases):
    # try:
    #     trigger = trigger_phrase[len("%new_talkback"):]
    #     if not trigger.strip() == "" and not response_phrase.strip() == "":
    #         response = response_phrase
    #         db[str(serverID)]["trigger_phrases"].append(trigger)
    #         db[str(serverID)]["response_phrases"].append(response)
    #         return "New talkback action successfully created."
    #     return "Failed to create new talkback action."
    # except:
    #     return "Failed to create new talkback action."

    try:
        trigger_list = re.split(r'\s+(?=[^"]*(?:"[^"]*"[^"]*)*$)',trigger_phrases)

        response_list = re.split(r'\s+(?=[^"]*(?:"[^"]*"[^"]*)*$)',response_phrases)

        if len(trigger_list) > 10 or len(response_list) > 10:
            return "Failed to create new talkback action (greater than 10 triggers or responses given)."

        for i in range(len(trigger_list)):
            trigger_list[i] = trigger_list[i].replace("\"", "")
        for i in range(len(response_list)):
            response_list[i] = response_list[i].replace("\"", "")
        
        db[str(serverID)]["trigger_phrases"].append(trigger_list)
        db[str(serverID)]["response_phrases"].append(response_list)

        return "New talkback action successfully created."
    except:
        return "Failed to create new talkback action"

def remove_talkback(serverID, msg):
    #format is %remove_talkback TRIGGER
    trigger_db = db[str(serverID)]["trigger_phrases"]
    for trigger in trigger_db:
        if trigger.strip() in msg.casefold():
            res = db[str(serverID)]["response_phrases"][trigger_db.index(trigger)]

            trigger_db.remove(trigger)
            db[str(serverID)]["response_phrases"].remove(res)

            return "Successfully removed talkback pair " + trigger.strip() + "/" + res.strip() + "."
    return "No matching trigger phrase found."


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
