import os
import time
import discord 

from utils.Singleton import Singleton
from pymongo import MongoClient
from enum import Enum
from copy import deepcopy
from typing import Dict, Any, Optional, Tuple, Unpack, TypedDict
from returns.result import Result, Success, Failure
from returns.maybe import Maybe, Some, Nothing
import logging

"""
This is the structure of the data that is stored in both MongoDB and 
locally in memory. If they differ, then any fields stored here that are not
stored remotely are automatically populated and copied to the remote for parity.
"""
_SCHEMA = {
    "server_id": -1,
    "banned_phrases": [], # Unused.
    "trigger_phrases": [], # Parallel Array to "response_phrases" that stores index-by-index what set of triggers maps to what set of responses.
    "response_phrases": [], # Vice versa of above.
    "quotes": [], # Quote information stored as an N-tuple defined in the quotes.py class.
    "motd": "", # Message of the Day for the server that Roti cycles through
    "music_queue": [],  # Unused, all music queues are in memory.
    "settings": {
        "talkback": {
            "enabled": True,  # Whether talkbacks are enabled
            "duration": 0,  # How long the message exists before being deleted, 0 is permanent.
            "strict": False, # Dictates if Roti will only look at substrings when responding, or will need EXACT matches of words to respond. (case ignored in both)
            "res_probability": 100,  # Probability that Roti will respond to a talkback
            "ai_probability": 5, # Probability that Roti will respond with an AI talkback.
        },
        "music": {
            "looped": False,  # Unused
            "speed": 100,  # Speed of songs, x1 - x2 speed.
            "volume": 100, #Base volume of Roti while playing music, percentage of 0 - 100%.
            "pitch": 100 # Pitch of the music, x0 to x5.
        }
    },
    # / permissions set <category> <permission levels options> [cmd] 
    # "permissions": {
    #     "talkback": {
    #         "enabled": [],
    #         "duration": [],
    #         "strict": [],
    #         "res_probability": [],
    #         "ai_probability": [],
    #     },
    #     "music "
    # }
}

bot_start_time = time.time()
class DatabaseError(Exception):
    def __init__(self, reason : Optional[str]):
        super().__init__(reason)
        self.reason = reason

"""
The optional is required for the first instantiation of the Singleton.
"""
class RotiDatabase(metaclass=Singleton):
    def __init__(self, database_url : Optional[str]):
        self._database_url = database_url
        self.logger = logging.getLogger(__name__)
        self._cluster : MongoClient = MongoClient(self._database_url)
        self._collections = self._cluster["Roti"]["data"]
        self._db : Dict[str, Any] = dict() # Used for quick access to the data, but changes need to be pushed!

        # Initialize database.
        start = time.time()
        self.logger.info("Initializing Database...")
        self._download_database()
        self.logger.info(f"Database Initialized in {round(1000*(time.time() - start), 2)}ms")

    def __contains__(self, value):
        return value in self._db

    def __getitem__(self, keys : Tuple[int, str, Unpack[Tuple[str, ...]]]) -> Result[Any, DatabaseError]:
        return self._get_nested(keys)

    def __setitem__(self, keys : Tuple[int, str, Unpack[Tuple[str, ...]]], value : Any) -> Maybe[DatabaseError]:
        return self._set_nested(keys, value)
    
    """
    Reads from the in-memory db, indexing with the variable amount of keys provided.
    The first value is always the server id, the second is always some key, after that there
    can be a variable number of keys that are always strings.
    """
    def _get_nested(self, keys : Tuple[int, str, Unpack[Tuple[str, ...]]]) -> Result[Any, DatabaseError]:
        try:
            data = self._db
            for key in keys:
                data = data[key]
        except KeyError as ke:
            return Failure(DatabaseError(f"KeyError: {ke} not found in database."))
        except TypeError as te:
            return Failure(DatabaseError(f"Invalid key path: {keys}"))
        
        return Success(data)
    
    """
    Writes to the in-memory db, indexing with the variable amount of keys provided.
    The first value is always the server id, the second is always some key, after that there
    can be a variable number of keys that are always strings.
    """
    def _set_nested(self, keys : Tuple[int, str, Unpack[Tuple[str, ...]]], value : Any) -> Maybe[DatabaseError]:
        try:
            data = self._db
            key_to_change = keys[-1]
            for key in keys[:-1]:
                data = data[key]
            
            if not isinstance(value, type(data[key_to_change])):
                return Some(DatabaseError(f"Source and destination type of value do not match. Expected: {type(data[key_to_change])}, got: {type(value)}."))
            data[key_to_change] = value
        except TypeError:
            return Some(DatabaseError(f"Invalid key path! Keys: {keys}"))
        return Nothing
    
    """
    Recursively ensures all keys in `reference` exist in `target`.
    If a key is missing, it will be initialized with the default value from `reference`.
    """
    def _recursive_dict_copy(self, target : dict, reference : dict) -> None:
        for key, default_value in reference.items():
            if key not in target:
                target[key] = deepcopy(default_value)
            elif isinstance(default_value, dict):
                # Recurse!
                self._recursive_dict_copy(target[key], default_value)
    
    """
    Downloads the database into memory.
    """
    def _download_database(self) -> None:
        # Takes data, puts into variable named db and keys the data using the serverID
        # To get a server's data, you need to do db[<server_id>][<category>] (ID IS A INTEGER!)
        for data in self._collections.find({}):
            self._db[data['server_id']] = data
            # TODO: Reapply this 
            #self._recursive_dict_copy(self._db[data['server_id']], _SCHEMA)

    def update_database(self, guild : discord.Guild) -> str:
        serverID = guild.id

        if serverID not in self._db.keys():
            temp = _SCHEMA
            temp['server_id'] = serverID
            self._collections.insert_one(temp)
            self._db[serverID] = temp
            return f"Successfully created database entry for {guild.name}. Have fun!"
    
    def delete_guild_entry(self, server_id : int) -> Maybe[DatabaseError]:
        if not server_id in self._db:
            return Some(DatabaseError(f"Server with ID: {server_id} does not exist."))
        
        self._collections.delete_one({"server_id": server_id})
        self._db[server_id].clear()
        return Nothing
    
    # Updates the database with the given key.
    # Ex. passing key = "trigger_phrases" will appropriately update the trigger database for the given server
    def write_data(self, server_id : int, *keys : str) -> Maybe[DatabaseError]:
        try:
            if server_id not in self._db:
                return Some(DatabaseError(f"Invalid server_id passed: {server_id}"))
            
            full_path = (server_id, ) + keys
            match self._get_nested(full_path):
                case Success(value):
                    key_path = ".".join(keys)
                    self._collections.update_one({"server_id": server_id}, {"$set": {key_path: value}})
                case Failure(error):
                    return Some(error)
            return Nothing
        except Exception as e:
            return Some(DatabaseError("Unable to connect to database"))
    
    def read_data(self, keys : Tuple[int, str, Unpack[Tuple[str, ...]]]) -> Result[Any, DatabaseError]:
        return self._get_nested(keys)

def calculate_uptime() -> str:
        total_seconds = int(time.time() - bot_start_time)
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        return f"{days}d {hours}h {minutes}m {seconds}s"

# Global used in the music.py file for /filter's modal
FilterParams = Enum("DistortionType", ["TREMOLO", "VIBRATO", "ROTATION", "DISTORTION"])


