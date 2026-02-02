import time
import discord 

from supabase import acreate_client, AsyncClient
from datetime import date
from dataclasses import dataclass, fields, field, asdict
from utils.Singleton import Singleton
from typing import Dict, Any, List, Optional, Tuple, Unpack, Dict, Type, TypeVar
from returns.result import Result, Success, Failure
from returns.maybe import Maybe, Some, Nothing
from database.bot_state import RotiState
from utils.RotiUtilities import TEST_GUILD
from concurrent.futures import Future
import logging
import asyncio
import threading

"""
Data types and Wrapper classes
"""
class DatabaseError(Exception):
    def __init__(self, reason : Optional[str]):
        super().__init__(reason)
        self.reason = reason

T = TypeVar('T')

"""
Database Schemas
Effectively the first argument is always the primary key of the table and the remaining are the column values
Most things have a default value, if they don't, it's usually integral to the function of the action.
"""

@dataclass
class TalkbackSettings:
    """Talkback settings for a server."""
    __tablename__ = "TalkbackSettings"
    server_id : int = field(metadata={"primary": True})
    enabled: bool = True
    duration: int = 0
    strict: bool = False
    res_probability: int = 100
    ai_probability: int = 5


@dataclass
class MusicSettings:
    """Music settings for a server."""
    __tablename__ = "MusicSettings"
    server_id : int = field(metadata={"primary": True})
    looped: bool = False
    speed: int = 100
    volume: int = 100
    pitch: int = 100

@dataclass
class Quotes:
    """Quotes table"""
    __tablename__ = "Quotes"
    id: int = field(metadata={"primary": True})
    server_id : int
    tag : str
    quote : str
    default : str = "None"
    name : str = "None"
    replaceable : bool = False
    has_original : bool = False

@dataclass
class Motd:
    """MOTD Table"""
    __tablename__ = "Motd"
    server_id : int = field(metadata={"primary": True})
    motd : str = None

@dataclass
class Talkbacks:
    """
    Talkback Table - Mostly for reference. \\
    This relies on a support table called 'talkback_triggers' that employs a layer of indirection to optimize talkback matching.
    For more info, checkout the TalkbackDriver class in `talkbacks.py`.
    """
    __tablename__ = "talkbacks"
    id : int = field(metadata={"primary": True})
    server_id : int
    responses : List[str]
    created_at : date

class RotiDatabase(metaclass=Singleton):
    """
    Generic Supabase database with type-safe dataclass-based operations.
    No in-memory cache (for now :P) - all operations go directly to Supabase.
    
    Usage Examples:
        # Read (async required)
        settings = await db.select(TalkbackSettings, server_id=12345)
        # Returns: TalkbackSettings(server_id=12345, enabled=True, ...)
        
        # Update with dataclass instance (queued, non-blocking)
        settings.enabled = False
        future = db.update(settings)
        
        # Update with kwargs (queued, non-blocking)
        db.update(TalkbackSettings, server_id=12345, enabled=False, duration=60)
        
        # Update with await (blocking)
        await db.update(TalkbackSettings, server_id=12345, enabled=False, _sync=True)
        
        # Insert new record
        await db.insert(TalkbackSettings(server_id=12345))
        
        # Delete record
        await db.delete(TalkbackSettings, server_id=12345)
        
        # List all (with filters)
        quotes = await db.select_all(Quote, server_id=12345)
        # Returns: List[Quote]
    """
    

    """
    This is a list of the tables in the supabase database. If you don't add a table here, it won't be registered.
    """
    TABLES = [TalkbackSettings, MusicSettings, Quotes, Motd, Talkbacks]

    def __init__(self):
        self.state = RotiState()
        self.logger = logging.getLogger(__name__)
        self.supabase: Optional[AsyncClient] = None
        self.PRIMARY_KEYS = self._get_primary_keys()
    
    async def initialize(self):
        """
        Initializes the Supabase client on the event loop.
        """
        self.logger.info("Initializing Database...")
        start = time.perf_counter()
        
        # Initialize client on the current running loop
        self.supabase = await acreate_client(
            supabase_url=self.state.credentials.database_url, 
            supabase_key=self.state.credentials.database_pass
        )
        
        self.logger.info(f"Database Initialized in {round(1000*(time.perf_counter() - start), 2)}ms")


    # ========================================================================
    # LIFECYCLE METHODS
    # ========================================================================
    
    def _run_write_loop(self):
        """Run the event loop for the write worker thread."""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()
    
    async def _process_writes(self):
        """Process queued database writes."""
        self.logger.info("Database write processor started")
        while self._database_active or not self._write_queue.empty():
            try:
                write_func, future = await self._write_queue.get()
                try:
                    result = await write_func()
                    future.set_result(result)
                    self.logger.debug(f"Write completed successfully")
                except Exception as e:
                    self.logger.error(f"Write operation failed: {e}", exc_info=True)
                    future.set_exception(e)
                finally:
                    self._write_queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Unexpected error in write processor: {e}", exc_info=True)
    
    async def shutdown(self):
        """Gracefully shut down the database worker."""
        self.logger.info("Shutting down database worker...")
        self._database_active = False
        
        if not self._write_queue.empty():
            self.logger.info(f"Waiting for {self._write_queue.qsize()} pending writes...")
            await self._write_queue.join()
        
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._worker_thread.join(timeout=5.0)
        self.logger.info("Database worker shutdown complete")
    

    # ========================================================================
    # HELPER METHODS
    # ========================================================================
    def _get_primary_keys(self) -> Dict[Type, str]:
        """
        Generates the primary keys from the given TABLE_NAMES
        """
        mapping = {}
        for table in self.TABLES:
            mapping[table] = self._get_primary_key(table)
        
        return mapping

    def _get_table_name(self, cls: Type) -> str:
        """Get table name for a dataclass type."""
        return getattr(cls, "__tablename__", cls.__name__)
    
    def _get_primary_key(self, cls: Type) -> str:
        """Get primary key field name for a dataclass type."""
        for field in fields(cls):
            if field.metadata.get("primary"):
                return field.name
        return "id" # Fallback default

    def _dataclass_to_dict(self, obj: Any) -> Dict[str, Any]:
        """Convert dataclass to dict, excluding None values and primary key if auto-generated."""
        data = asdict(obj)
        # Remove None values
        return {k: v for k, v in data.items() if v is not None}
    
    def _dict_to_dataclass(self, dataclass_type: Type[T], data: Dict[str, Any]) -> T:
        """Convert dict to dataclass instance."""
        # Get field names from dataclass
        field_names = {f.name for f in fields(dataclass_type)}
        # Filter dict to only include fields that exist in dataclass
        filtered_data = {k: v for k, v in data.items() if k in field_names}
        return dataclass_type(**filtered_data)
    
    # ========================================================================
    # CORE OPERATIONS
    # ========================================================================
    
    async def select(
        self,
        dataclass_type: Type[T],
        **primary_key_kwargs
    ) -> Optional[T]:
        """
        Select a single record by primary key.
        
        Args:
            dataclass_type: The dataclass type (e.g., TalkbackSettings)
            **primary_key_kwargs: Primary key value(s) (e.g., server_id=12345)
            
        Returns:
            Dataclass instance or None if not found
            
        Example:
            settings = await db.select(TalkbackSettings, server_id=12345)
        """
        try:
            table_name = self._get_table_name(dataclass_type)
            
            # Build query with primary key filter
            query = self.supabase.table(table_name).select('*')
            for key, value in primary_key_kwargs.items():
                query = query.eq(key, value)
            
            result = await query.single().execute()
            
            if not result.data:
                return None
            
            return self._dict_to_dataclass(dataclass_type, result.data)
            
        except Exception as e:
            self.logger.error(f"Failed to select {dataclass_type.__name__}: {e}")
            return None
            
    async def select_all(
        self,
        dataclass_type: Type[T],
        **filter_kwargs
    ) -> List[T]:
        """
        Select multiple records with optional filters.
        
        Args:
            dataclass_type: The dataclass type
            **filter_kwargs: Filter conditions (e.g., server_id=12345)
            
        Returns:
            List of dataclass instances
            
        Example:
            quotes = await db.select_all(Quote, server_id=12345)
        """
        try:
            table_name = self._get_table_name(dataclass_type)
            
            # Build query with filters
            query = self.supabase.table(table_name).select('*')
            for key, value in filter_kwargs.items():
                query = query.eq(key, value)
            
            result = await query.execute()
            
            if not result.data:
                return []
            
            return [self._dict_to_dataclass(dataclass_type, row) for row in result.data]
            
        except Exception as e:
            self.logger.error(f"Failed to select all {dataclass_type.__name__}: {e}")
            return []

    async def insert(self, obj: T, _sync: bool = True) -> Result[T, DatabaseError]:
        """
        Insert a new record.
        
        Args:
            obj: Dataclass instance to insert
            _sync: Whether to execute synchronously (default True)
            
        Returns:
            Result with inserted object or error
            
        Example:
            await db.insert(TalkbackSettings(server_id=12345))
        """
        try:
            dataclass_type = type(obj)
            server_id = getattr(obj, 'server_id', None)
            table_name = self._get_table_name(dataclass_type)
            data = self._dataclass_to_dict(obj)
            
            result = await self.supabase.table(table_name).insert(data).execute()

            if self.state.args.test and server_id != TEST_GUILD:
                self.logger.info(f"Test Mode: Blocking insert for server {server_id}")
                return Success(obj)
            
            if not result.data:
                return Failure(DatabaseError("Insert failed - no data returned"))
            
            return Success(self._dict_to_dataclass(dataclass_type, result.data[0]))
            
        except Exception as e:
            self.logger.error(f"Failed to insert {dataclass_type.__name__}: {e}")
            return Failure(DatabaseError(f"Insert failed: {e}"))
    
    def update(self, obj_or_type, _sync: bool = False, **kwargs) -> asyncio.Task:
        """
        Update a record (fire-and-forget by default).
        
        Args:
            obj_or_type: Either a dataclass instance or a dataclass type
            _sync: Whether to wait for completion (default False)
            **kwargs: If obj_or_type is a type, provide update values here
        """
        
        async def _perform_update():
            try:
                # 1. Check if passed a CLASS (Type)
                pk_value = None
                if isinstance(obj_or_type, type):
                    dataclass_type = obj_or_type
                    table_name = self._get_table_name(dataclass_type)
                    primary_key = self._get_primary_key(dataclass_type)
                    
                    if primary_key not in kwargs:
                        raise DatabaseError(f"Primary key '{primary_key}' not provided")
                    
                    pk_value = kwargs[primary_key]
                    server_id = pk_value if primary_key == "server_id" else kwargs.get("server_id")

                    update_data = {k: v for k, v in kwargs.items() if k not in [primary_key, '_sync']}
                # 2. Check if passed an INSTANCE
                else:
                    dataclass_type = type(obj_or_type)
                    primary_key = self._get_primary_key(dataclass_type)
                    
                    pk_value = getattr(obj_or_type, primary_key)
                    server_id = getattr(obj_or_type, 'server_id', pk_value if primary_key == "server_id" else None)
                    
                    data = self._dataclass_to_dict(obj_or_type)
                    update_data = {k: v for k, v in data.items() if k != primary_key}

                # Skip writes in test mode unless it's the test guild
                target_id = server_id if server_id is not None else pk_value

                if self.state.args.test and server_id != TEST_GUILD:
                    self.logger.info(f"Test mode: Skipping write to ID {target_id}")
                    return Success(None)
                
                if self.supabase is None:
                    raise RuntimeError("Database not initialized. Call await db.initialize()")

                await self.supabase.table(table_name)\
                    .update(update_data)\
                    .eq(primary_key, pk_value)\
                    .execute()
                
                return Success(None)
                
            except Exception as e:
                self.logger.error(f"Failed to update: {e}", exc_info=True)
                return Failure(DatabaseError(f"Update failed: {e}"))

        # Create task on current loop
        task = asyncio.create_task(_perform_update())

        if _sync:
            # If user wants to await it, we return the task (which is awaitable)
            return task
        
        # If fire-and-forget, add a logger callback so errors aren't silent
        def _log_error(t):
            try:
                t.result()
            except Exception as e:
                self.logger.error(f"Background update task failed: {e}")
        
        task.add_done_callback(_log_error)
        return task

    async def delete(
        self,
        dataclass_type: Type[T],
        **primary_key_kwargs
    ) -> Result[None, DatabaseError]:
        """
        Delete a record by primary key.
        
        Args:
            dataclass_type: The dataclass type
            **primary_key_kwargs: Primary key value(s)
            
        Returns:
            Success or Failure
            
        Example:
            await db.delete(TalkbackSettings, server_id=12345)
        """
        try:
            table_name = self._get_table_name(dataclass_type)
            
            # Build delete query
            query = self.supabase.table(table_name).delete()
            for key, value in primary_key_kwargs.items():
                query = query.eq(key, value)
            
            await query.execute()
            
            return Success(None)
            
        except Exception as e:
            self.logger.error(f"Failed to delete {dataclass_type.__name__}: {e}")
            return Failure(DatabaseError(f"Delete failed: {e}"))
    
    # ========================================================================
    # SERVER INITIALIZATION
    # ========================================================================

    async def initialize_server(self, guild: discord.Guild) -> Result[str, DatabaseError]:
        """
        Initialize a new server with default settings.
        
        Args:
            guild: Discord guild object
            
        Returns:
            Success with message or Failure with error
        """
        server_id = guild.id
        
        try:
            # Check if server already exists
            existing = await self.select(TalkbackSettings, server_id=server_id)
            if existing:
                return Failure(DatabaseError(f"Server {guild.name} already initialized"))
            
            # Insert server config (for MOTD)
            await self.insert(Motd(server_id=server_id, motd=""))
            
            # Insert talkback settings
            await self.insert(TalkbackSettings(server_id=server_id))
            
            # Insert music settings
            await self.insert(MusicSettings(server_id=server_id))
            
            self.logger.info(f"Initialized server: {guild.name} ({server_id})")
            return Success(f"Successfully created database entry for {guild.name}. Have fun!")
            
        except Exception as e:
            self.logger.error(f"Failed to initialize server {guild.name}: {e}", exc_info=True)
            return Failure(DatabaseError(f"Failed to initialize server: {e}"))
    
    async def delete_server(self, server_id: int) -> Maybe[DatabaseError]:
        """
        Delete a server and all its data (cascades).
        
        Args:
            server_id: Discord server ID
            
        Returns:
            Nothing on success, Some(DatabaseError) on failure
        """
        try:
            # Delete server config (cascades to settings via foreign keys)
            result = await self.delete(Motd, server_id=server_id)
            
            if isinstance(result, Failure):
                return Some(result.failure())
            
            self.logger.info(f"Deleted server: {server_id}")
            return Nothing
            
        except Exception as e:
            self.logger.error(f"Failed to delete server {server_id}: {e}", exc_info=True)
            return Some(DatabaseError(f"Failed to delete server: {e}"))
    
    async def server_exists(self, server_id: int) -> bool:
        """Check if a server exists in the database."""
        result = await self.select(TalkbackSettings, server_id=server_id)
        return result is not None


