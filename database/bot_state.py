import os
import time
import argparse
from utils.Singleton import Singleton
from dotenv import load_dotenv
from dataclasses import dataclass, field

class RotiState(metaclass=Singleton):
    """
    Management class to keep track of global state and environment variables for Roti \n
    READ ONLY!
    """
    start_time = time.time()
    def __init__(self):
        self._setup_cli_args()
        self.__dict__["credentials"] = BotCredentials()
    
    def _setup_cli_args(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--music", action=argparse.BooleanOptionalAction, help="Toggle Music Functionality")
        parser.add_argument("--test", action=argparse.BooleanOptionalAction, help="Toggle testing mode")
        parser.add_argument("--show-cog-load", "-scl", action=argparse.BooleanOptionalAction, help="Show what cogs are loaded during startup.")
        args = parser.parse_args()

        self.__dict__["args"] = RotiArguments(
            music=args.music,
            test=args.test,
            show_cog_load=args.show_cog_load
        )
        
    @classmethod
    def calculate_uptime(cls) -> str:
        total_seconds = int(time.time() - cls.start_time)
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        return f"{days}d {hours}h {minutes}m F{seconds}s"

    def __setattr__(self, key, value):
        """ Prevents modification of attributes after initialization. """
        raise AttributeError(f"Cannot modify read-only attribute '{key}'")

class BotCredentials(metaclass=Singleton):
    def __init__(self):
        load_dotenv(".env", override=True) # Load credentials
        self.__dict__["database_url"] = os.getenv("DATABASE")
        self.__dict__["database_pass"] = os.getenv("DATABASE_PASS")
        self.__dict__["token"] = os.getenv("TOKEN")
        self.__dict__["test_token"] = os.getenv("TEST_TOKEN")
        self.__dict__["music_pass"] = os.getenv("MUSIC_PASS")
        self.__dict__["music_ip"] = os.getenv("LAVALINK_HOST", "127.0.0.1")
        self.__dict__["application_id"] = os.getenv("APPLICATION_ID")
        self.__dict__["test_application_id"] = os.getenv("TEST_APPLICATION_ID")
        self.__dict__["youtube_name"] = os.getenv("YOUTUBE_NAME")
        self.__dict__["youtube_pass"] = os.getenv("YOUTUBE_PASS")
        self.__dict__["pollinations_key"] = os.getenv("POLLINATIONS_KEY", "")
    
    def __setattr__(self, key, value):
        """ Prevents modification of attributes after initialization. """
        raise AttributeError(f"Cannot modify read-only attribute '{key}'")

@dataclass(frozen=True, kw_only=True)
class RotiArguments:
    """
    Data class that contains the command line arguments passed into Roti at initialization
    """
    music : bool = field(default=True)
    test : bool = field(default=False)
    show_cog_load : bool = field(default=False)