import time
import functools
import asyncio
from discord.ext import commands
from collections import defaultdict, namedtuple
from typing import Callable, Optional, List, NamedTuple
from dataclasses import dataclass, field
from database.data import RotiDatabase, TalkbackTriggersTable, QuotesTable

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

@dataclass(slots=True, frozen=True, kw_only=True)
class RotiPopulation:
    servers : int
    users : int

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
    def decorator(func: Callable):
        cache = {}

        def get_cache_key(*args, **kwargs):
            # Convert mutable lists in args to immutable tuples so they are hashable
            hashable_args = tuple(
                tuple(arg) if isinstance(arg, list) else arg 
                for arg in args
            )
            return (func.__name__, hashable_args, frozenset(kwargs.items()))

        # --- ASYNC WRAPPER ---
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            try:
                cache_key = get_cache_key(*args, **kwargs)
            except TypeError:
                return await func(*args, **kwargs)

            current_time = time.monotonic()
            if cache_key in cache:
                val, timestamp = cache[cache_key]
                if current_time - timestamp <= ttl:
                    return val

            result = await func(*args, **kwargs)
            cache[cache_key] = (result, current_time)
            return result

        # --- SYNC WRAPPER ---
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            try:
                cache_key = get_cache_key(*args, **kwargs)
            except TypeError:
                return func(*args, **kwargs)

            current_time = time.monotonic()
            if cache_key in cache:
                val, timestamp = cache[cache_key]
                if current_time - timestamp <= ttl:
                    return val

            result = func(*args, **kwargs)
            cache[cache_key] = (result, current_time)
            return result

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator

def get_perf_statistics():
    return _statistics

@ttl_cache(ttl=300)
async def get_usage_statistics(db : RotiDatabase) -> RotiUsage:
    talkbacks = await _calculate_talkback_count(db)
    quotes = await _calculate_quote_usage(db)
    return RotiUsage(
        talkback_usage=talkbacks,
        quote_usage=quotes
    )

def get_population(bot : commands.Bot, guild_ids : List[int]) -> RotiPopulation:
    return _calculate_population(bot, guild_ids)

async def _calculate_talkback_count(db: RotiDatabase) -> TalkbackUsage:
    """
    This is a cached function to calculate the number of talkbacks present across all servers.
    """
    trigger_count = await db.count(TalkbackTriggersTable)
    response_count = await db.raw_query(
        """
        SELECT SUM(array_length(responses, 1)) as total_responses
        FROM talkbacks
        """
    )

    response_count = response_count.unwrap()[0]["total_responses"]
    
    return TalkbackUsage(triggers=trigger_count, responses=response_count)

async def _calculate_quote_usage(db : RotiDatabase) -> QuoteUsage:
    """
    This is a cached function to calculate the number of quotes present across all servers, organized by type of quote.
    """
    nonreplaceable = await db.count(QuotesTable, replaceable=False)
    replaceable = await db.count(QuotesTable, replaceable=True)

    return QuoteUsage(nonreplaceable=nonreplaceable, replaceable=replaceable)

@ttl_cache(ttl=300)
def _calculate_population(bot : commands.Bot, guild_ids : List[int]) -> RotiPopulation:
    """
    This is a cached function to calculate the total population of servers that use Roti
    """
    total = 0

    for guild in guild_ids:
        total += bot.get_guild(guild).member_count
    
    return RotiPopulation(servers=len(guild_ids), users=total)


