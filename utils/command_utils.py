from discord.ext import commands
from typing import Union

def cog_command(cls):
    """
    This is a decorator to identify a class as a cog, if this decorator is not used, then the 
    class is considered NOT a cog and won't be loaded as one.
    """
    cls.is_cog = True
    return cls