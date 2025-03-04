import time
import functools
from collections import defaultdict
from typing import Callable, Optional, List
from dataclasses import dataclass, field
from database.data import RotiDatabase

@dataclass(frozen=True)
class FunctionName:
    display_name : str
    qualified_name : str

@dataclass(order=True)
class FunctionStatistics:
    shortest_exec_time : float = field(default=float("inf"))
    longest_exec_time : float = field(default=float("-inf"))
    average_exec_time : float = field(default=0.0)
    times_invoked : int = field(default=0)

_statistics : dict[FunctionName, FunctionStatistics] = defaultdict(FunctionStatistics)

def statistic(display_name: Optional[str] = None):
    """
    This decorator can be used on any function to measure its performance with some metrics.
    """
    def decorator(func: Callable):
        func_name = func.__name__
        
        if display_name:
            _statistics[func_name].display_name = display_name
        else:
            _statistics[func_name].display_name = func_name

        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            result = func(*args, **kwargs)
            end_time = time.perf_counter()
            
            exec_time = end_time - start_time
            stats = _statistics[func_name]

            stats.times_invoked += 1
            stats.shortest_exec_time = min(stats.shortest_exec_time, exec_time)
            stats.longest_exec_time = max(stats.longest_exec_time, exec_time)
            stats.average_exec_time = (
                (stats.average_exec_time * (stats.times_invoked - 1)) + exec_time
            ) / stats.times_invoked

            return result

        return wrapper
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
                    print("CACHE HIT!")
                    return cached_value

            # Otherwise, compute the result and cache it
            result = func(*args, **kwargs)
            cache[cache_key] = (result, current_time)
            return result

        return wrapper
    return decorator


def pretty_print_statistics() -> str:
    if not _statistics.values():
        return "No statistics recorded!"
    
    output = []
    for func_name, stats in _statistics.items():
        display_name = stats.display_name if stats.display_name else func_name
        output.append(f"Function: {display_name}")
        output.append(f"  Shortest Execution Time: {stats.shortest_exec_time:.6f} seconds")
        output.append(f"  Longest Execution Time: {stats.longest_exec_time:.6f} seconds")
        output.append(f"  Average Execution Time: {stats.average_exec_time:.6f} seconds")
        output.append(f"  Times Invoked: {stats.times_invoked}")
        output.append("-" * 40)
    return "\n".join(output)

def pretty_print_usage_statistics(db : RotiDatabase, guild_ids : List[int]) -> str:
    return \
    f"""
    Talkback Statistics: 
    {calculate_talkback_count(db, guild_ids)}
    {"-" * 40}
    """

@ttl_cache(ttl=300)
def calculate_talkback_count(db : RotiDatabase, guild_ids : List[int]) -> str:
    """
    This is a cached function to calculate the number of talkbacks that are present across all servers.
    """
    trigger_count = 0
    response_count = 0

    for guild in guild_ids:
        trigger_count += sum([len(trigger_set) for trigger_set in db[guild, "trigger_phrases"]])
        response_count += sum([len(response_set) for response_set in db[guild, "response_phrases"]])
    
    return f"There are currently {trigger_count} trigger phrases and {response_count} response phrases registered with me across all servers!"
