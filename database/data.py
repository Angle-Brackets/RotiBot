import time
import discord 

from utils.Singleton import Singleton
from pymongo import MongoClient
from enum import Enum
from copy import deepcopy
from typing import Dict, Any, Optional, Tuple, Unpack
from returns.result import Result, Success, Failure
from returns.maybe import Maybe, Some, Nothing
from database.bot_state import RotiState
from utils.RotiUtilities import TEST_GUILD
from concurrent.futures import Future
import logging
import asyncio
import threading

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
    }
}

"""
Data types and Wrapper classes
"""
class DatabaseError(Exception):
    def __init__(self, reason : Optional[str]):
        super().__init__(reason)
        self.reason = reason

KeyType = Tuple[int, str, Unpack[Tuple[str, ...]]]
DatabaseRequest = Tuple[KeyType, Any, Future]

class RotiDatabase(metaclass=Singleton):
    def __init__(self):
        self.state = RotiState()
        self._database_url = self.state.credentials.database_url
        self.logger = logging.getLogger(__name__)
        self._cluster : MongoClient = MongoClient(self._database_url)
        self._collections = self._cluster["Roti"]["data"]
        self._db : Dict[int, Dict[str, Any]] = dict() # Used for quick access to the data, but changes need to be pushed!

        # Initialize database.
        start = time.perf_counter()
        self.logger.info("Initializing Database...")
        self._download_database()
        self.logger.info(f"Database Initialized in {round(1000*(time.perf_counter() - start), 2)}ms")

        # Initialize Database Request Queue
        start = time.perf_counter()
        self.logger.info("Initializing Database Request Queue...")
        self._database_active = True
        self._loop = asyncio.new_event_loop()
        self._requests : asyncio.Queue[DatabaseRequest] = asyncio.Queue()
        self._worker_thread = threading.Thread(target=self._run_request_event_loop, name="Database Request Daemon", daemon=True)
        self._worker_thread.start()
        asyncio.run_coroutine_threadsafe(coro=self._process_requests(), loop=self._loop)
        self.logger.info(f"Database Request Queue Initialized in {round(1000*(time.perf_counter() - start), 2)}ms")


    def __contains__(self, value):
        return value in self._db

    def __getitem__(self, keys : Tuple[int, str, Unpack[Tuple[str, ...]]]) -> Result[Any, DatabaseError]:
        return self._get_nested(keys)

    def __setitem__(self, keys : Tuple[int, str, Unpack[Tuple[str, ...]]], value : Any) -> Future:
        """
        Sets a value in the database asynchronously.
        
        Returns a Future that will be resolved when the database operation completes.
        You can await this Future to wait for the operation to complete, or ignore it
        to let it run in the background.
        
        Example usage:
            # Non-blocking usage
            db[(server_id, "settings", "talkback", "enabled")] = True
            
            # Blocking usage (wait for operation to complete)
            future = db[(server_id, "settings", "talkback", "enabled")] = True
            await future
        """
        # Update the in-memory database immediately
        self._set_nested(keys, value)
        future = Future()

        # In testing modes, we don't want to actually perform any database changes unless its in the test guild.
        if not self.state.args.test or keys[0] == TEST_GUILD:
            self._loop.call_soon_threadsafe(self._requests.put_nowait, (keys, value, future))
        return future
    
    async def shutdown(self):
        """Gracefully shut down the database worker"""
        self.logger.info("Shutting down database worker...")
        self._database_active = False
        
        # Wait for all queued operations to complete
        if not self._requests.empty():
            self.logger.info(f"Waiting for {self._requests.qsize()} pending database operations to complete...")
            await self._requests.join()
            
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._worker_thread.join(timeout=5.0)
        self.logger.info("Database worker shutdown complete")

    def _run_request_event_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()
    
    async def _process_requests(self):
        """
        Continuously process database requests in order.
        """
        self.logger.info("Database request processor started")
        while self._database_active or not self._requests.empty():
            try:
                keys, value, future = await self._requests.get()
                self.logger.debug(f"Processing database write: {keys}, {value}")
                try:
                    match await self._write_to_database(keys, value):
                        case Success(_):
                            print(f"Successfully wrote to Database with keys: {keys} and value: {value}")
                        case Failure(DatabaseError() as error):
                            print(f"Failed to write to database with keys: {keys} and value: {value}\n" + error)
                            future.set_exception(error)
                except Exception as e:
                    self.logger.error(f"Exception during database write: {str(e)}", exc_info=True)
                    future.set_exception(e)
                self._requests.task_done()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Unexpected error in request processor: {str(e)}", exc_info=True)
            
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
    def _set_nested(self, keys : Tuple[int, str, Unpack[Tuple[str, ...]]], value : Any) -> Result[None, DatabaseError]:
        try:
            data = self._db
            key_to_change = keys[-1]
            for key in keys[:-1]:
                data = data[key]
            
            if not isinstance(value, type(data[key_to_change])):
                return Failure(DatabaseError(f"Source and destination type of value do not match. Expected: {type(data[key_to_change])}, got: {type(value)}."))
            data[key_to_change] = value
        except TypeError:
            return Failure(DatabaseError(f"Invalid key path! Keys: {keys}"))
        return Success(None)
    
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
    
    async def _write_to_database(self, keys: Tuple[int, str, Unpack[Tuple[str, ...]]], value: Any) -> Result[None, DatabaseError]:
        """Performs the actual database write operation"""
        try:
            server_id = keys[0]
            if server_id not in self._db:
                return Failure(DatabaseError(f"Invalid server_id passed: {server_id}"))
            
            # Create the MongoDB update path (e.g., "settings.talkback.enabled")
            key_path = ".".join(keys[1:])
            
            # Update the MongoDB database
            result = await asyncio.to_thread(
                self._collections.update_one,
                {"server_id": server_id},
                {"$set": {key_path: value}}
            )
            
            if result.modified_count == 0 and result.matched_count == 0:
                return Failure(DatabaseError(f"No document found for server_id: {server_id}"))
                
            return Success(None)
        except ConnectionError as ce:
            return Failure(DatabaseError(f"Unable to connect to database: {ce}"))
        except Exception as e:
            return Failure(DatabaseError(f"An exception occurred writing to the database: {e}"))
    
    def read_data(self, keys : Tuple[int, str, Unpack[Tuple[str, ...]]]) -> Result[Any, DatabaseError]:
        return self._get_nested(keys)

# Global used in the music.py file for /filter's modal
FilterParams = Enum("DistortionType", ["TREMOLO", "VIBRATO", "ROTATION", "DISTORTION"])


