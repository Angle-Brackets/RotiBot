import time
import functools
import asyncio
from collections import defaultdict, namedtuple
from typing import Callable, Optional, List, NamedTuple
from dataclasses import dataclass, field
from database.data import RotiDatabase

@dataclass(slots=True, kw_only=True, frozen=True)
class FunctionInfo:
    """
    Information about a tracked function call.
    """
    display_name : str
    qualified_name : str
    category : str = field(default=None)

UNDEFINED_FUNCTION = FunctionInfo(
    display_name="UNDEFINED",
    qualified_name="UNDEFINED"
)

@dataclass(slots=True, frozen=True, kw_only=True)
class TalkbackUsage:
    triggers: int
    responses : int

@dataclass(slots=True, frozen=True, kw_only=True)
class QuoteUsage:
    nonreplaceable : int
    replaceable : int

@dataclass(slots=True, frozen=True, kw_only=True, order=True)
class RotiUsage:
    """
    Class to store information about global usage statistics on Roti
    """
    talkback_usage : TalkbackUsage
    quote_usage : QuoteUsage

@dataclass(slots=True, order=True)
class FunctionStatistics:
    """
    Class to store global performance statistics on Roti
    """
    function_info : FunctionInfo = field(default=UNDEFINED_FUNCTION)
    shortest_exec_time : float = field(default=float("inf"))
    longest_exec_time : float = field(default=float("-inf"))
    average_exec_time : float = field(default=0.0)
    times_invoked : int = field(default=0)

_statistics : dict[str, FunctionStatistics] = defaultdict(FunctionStatistics)

def statistic(display_name: Optional[str] = None, category : Optional[str] = None):
    """
    This decorator can be used on any function to measure its performance with some metrics.
    Works with both synchronous functions and coroutines.
    """
    def decorator(func: Callable):
        _statistics[func.__name__].function_info = FunctionInfo(
            display_name=display_name if display_name else func.__name__,
            qualified_name=func.__name__,
            category=category
        )

        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                start_time = time.perf_counter()
                result = await func(*args, **kwargs)
                end_time = time.perf_counter()
                
                exec_time = end_time - start_time
                stats = _statistics[func.__name__]

                stats.times_invoked += 1
                stats.shortest_exec_time = min(stats.shortest_exec_time, exec_time)
                stats.longest_exec_time = max(stats.longest_exec_time, exec_time)
                stats.average_exec_time = (
                    (stats.average_exec_time * (stats.times_invoked - 1)) + exec_time
                ) / stats.times_invoked
                return result
            
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                start_time = time.perf_counter()
                result = func(*args, **kwargs)
                end_time = time.perf_counter()
                
                exec_time = end_time - start_time
                stats = _statistics[func.__name__]

                stats.times_invoked += 1
                stats.shortest_exec_time = min(stats.shortest_exec_time, exec_time)
                stats.longest_exec_time = max(stats.longest_exec_time, exec_time)
                stats.average_exec_time = (
                    (stats.average_exec_time * (stats.times_invoked - 1)) + exec_time
                ) / stats.times_invoked
                return result
            
            return sync_wrapper
    
    return decorator

def ttl_cache(ttl: int):
    """
    This decorator caches the results of a method for an amount of seconds described by the ttl.
    Attributes:
        ttl (int) : The amount of seconds to invalidate the cache after.
    """
    def decorator(func: Callable):
        cache = {}
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Create a key from the function's arguments
            cache_key = func.__name__
            current_time = time.monotonic()

            # If the result is cached and valid (within N seconds), return it
            if cache_key in cache:
                cached_value, timestamp = cache[cache_key]
                if current_time - timestamp <= ttl:
                    return cached_value

            # Otherwise, compute the result and cache it
            result = func(*args, **kwargs)
            cache[cache_key] = (result, current_time)
            return result

        return wrapper
    return decorator

def get_perf_statistics():
    return _statistics

def get_usage_statistics(db : RotiDatabase, guild_ids : List[int]) -> RotiUsage:
    return RotiUsage(
        talkback_usage=_calculate_talkback_count(db, guild_ids),
        quote_usage=_calculate_quote_usage(db, guild_ids)
    )

@ttl_cache(ttl=300)
def _calculate_talkback_count(db: RotiDatabase, guild_ids: List[int]) -> TalkbackUsage:
    """
    This is a cached function to calculate the number of talkbacks present across all servers.
    """
    trigger_count = 0
    response_count = 0

    for guild in guild_ids:
        trigger_count += sum(len(trigger_set) for trigger_set in db[guild, "trigger_phrases"].unwrap())
        response_count += sum(len(response_set) for response_set in db[guild, "response_phrases"].unwrap())
    
    return TalkbackUsage(triggers=trigger_count, responses=response_count)

@ttl_cache(ttl=300)
def _calculate_quote_usage(db : RotiDatabase, guild_ids : List[int]) -> QuoteUsage:
    """
    This is a cached function to calculate the number of quotes present across all servers, organized by type of quote.
    """
    nonreplaceable = 0
    replaceable = 0

    for guild in guild_ids:
        for quote in db[guild, "quotes"].unwrap():
            nonreplaceable += int(not quote["replaceable"])
            replaceable += int(quote["replaceable"])
    
    return QuoteUsage(nonreplaceable=nonreplaceable, replaceable=replaceable)

