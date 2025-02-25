import os
import time
from utils.Singleton import Singleton
from dotenv import load_dotenv

class RotiState(metaclass=Singleton):
    """
    Management class to keep track of global state and environment variables for Roti \n
    READ ONLY!
    """
    def __init__(self):
        self.__dict__["credentials"] = BotCredentials()
        self.__dict__["start_time"] = time.time()
    
    def calculate_uptime(self) -> str:
        total_seconds = int(time.time() - self.start_time)
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        return f"{days}d {hours}h {minutes}m {seconds}s"

    def __setattr__(self, key, value):
        """ Prevents modification of attributes after initialization. """
        raise AttributeError(f"Cannot modify read-only attribute '{key}'")

class BotCredentials(metaclass=Singleton):
    def __init__(self):
        load_dotenv(".env") # Load credentials
        self.__dict__["database_url"] = os.getenv("DATABASE")
        self.__dict__["token"] = os.getenv("TOKEN")
        self.__dict__["test_token"] = os.getenv("TEST_TOKEN")
        self.__dict__["music_pass"] = os.getenv("MUSIC_PASS")
        self.__dict__["music_ip"] = os.getenv("MUSIC_IP")
        self.__dict__["application_id"] = os.getenv("APPLICATION_ID")
        self.__dict__["test_application_id"] = os.getenv("TEST_APPLICATION_ID")
        self.__dict__["youtube_name"] = os.getenv("YOUTUBE_NAME")
        self.__dict__["youtube_pass"] = os.getenv("YOUTUBE_PASS")
    
    def __setattr__(self, key, value):
        """ Prevents modification of attributes after initialization. """
        raise AttributeError(f"Cannot modify read-only attribute '{key}'")