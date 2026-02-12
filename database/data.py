import time
import discord 

from supabase import acreate_client, AsyncClient
from datetime import date
import dataclasses
from dataclasses import dataclass, fields, field, asdict
from utils.Singleton import Singleton
from typing import Dict, Any, List, Optional, Dict, Type, TypeVar, Final
from returns.result import Result, Success, Failure
from returns.maybe import Maybe, Some, Nothing
from database.bot_state import RotiState
from utils.RotiUtilities import TEST_GUILD
import logging
import asyncio

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
class GenerateSettings:
    """Generate settings for a server."""
    __tablename__ = "GenerateSettings"
    server_id : int = field(metadata={"primary": True})
    default_model : str = "gemini-fast"
    temperature : float = 0.9

@dataclass
class QuotesTable:
    """Quotes table"""
    __tablename__ = "Quotes"
    id: Final[int] = field(init=False, default=None, metadata={"primary": True})
    server_id : int
    tag : str
    quote : str
    default : str = "None"
    name : str = "None"
    replaceable : bool = False
    has_original : bool = False

@dataclass
class MotdTable:
    """MOTD Table"""
    __tablename__ = "Motd"
    user_id : int = field(metadata={"primary": True})
    motd : str = None

@dataclass
class TalkbacksTable:
    """
    Talkback Table - Mostly for reference. \\
    This relies on a support table called 'talkback_triggers' that employs a layer of indirection to optimize talkback matching.
    For more info, checkout the TalkbackDriver class in `talkbacks.py`.
    """
    __tablename__ = "talkbacks"
    id : Final[int] = field(init=False, default=None, metadata={"primary": True})
    server_id : int
    responses : List[str]
    created_at : date

@dataclass
class TalkbackTriggersTable:
    """
    This is a SUPPORT for the Talkbacks table. DO NOT USE THIS FOR NORMAL QUERIES! Only for counting or very simple operations.
    """
    __tablename__ = "talkback_triggers"
    talkback_id : int =  field(metadata={"primary": True})
    trigger : str = field(metadata={"primary": True})

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
    TABLES = [TalkbackSettings, MusicSettings, GenerateSettings, QuotesTable, MotdTable, TalkbacksTable, TalkbackTriggersTable]

    def __init__(self):
        self.state = RotiState()
        self.logger = logging.getLogger(__name__)
        self.supabase: Optional[AsyncClient] = None
        self._background_tasks = set() # Currently enqueued tasks
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
    
    async def shutdown(self):
        """Gracefully shut down the database client and finish background tasks."""
        self.logger.info("Shutting down database...")
        
        # Wait for all background tasks to finish
        if self._background_tasks:
            self.logger.info(f"Waiting for {len(self._background_tasks)} pending writes...")
            await asyncio.gather(*self._background_tasks, return_exceptions=True)
            self.logger.info("All pending writes completed.")

        if self.supabase:
            await self.supabase.auth.sign_out() 
            self.supabase = None

        self.logger.info("Database shutdown complete.")
    

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

    def _should_use_defaults(self, cls: Type) -> bool:
        """
        Check if this dataclass should return default values when not found in database.
        
        Settings tables (TalkbackSettings, MusicSettings) have defaults and should return
        an instance with default values. Data tables (Quotes, MOTD, etc.) should return None.
        
        Logic: A table should use defaults if all non-primary-key fields have default values.
        """
        all_fields = fields(cls)
        for f in all_fields:
            # Skip primary keys and init=False fields (like auto-generated IDs)
            if f.metadata.get("primary") or not f.init:
                continue
            # Check if field has a default value
            # dataclasses.MISSING is the sentinel value for no default
            if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING:
                # No default value defined
                return False
        return True

    def _dataclass_to_dict(self, obj: Any) -> Dict[str, Any]:
        """Convert dataclass to dict, excluding None values and primary key if auto-generated."""
        data = asdict(obj)
        # Remove None values
        return {k: v for k, v in data.items() if v is not None}
    
    def _dict_to_dataclass(self, dataclass_type: Type[T], data: Dict[str, Any]) -> T:
        """Convert dict to dataclass instance, handling init=False fields like 'id'."""
        # 1. Get all fields defined in the dataclass
        all_fields = fields(dataclass_type)
        
        # 2. Separate fields that go in the constructor (init=True) 
        # from those that don't (init=False)
        init_field_names = {f.name for f in all_fields if f.init}
        
        # 3. Create a dict of data for the constructor
        constructor_data = {k: v for k, v in data.items() if k in init_field_names}
        
        # 4. Create the instance
        instance = dataclass_type(**constructor_data)
        
        # 5. Manually set the fields that were init=False (like your 'id')
        # We use object.__setattr__ to bypass 'frozen=True' or 'Final' restrictions
        non_init_field_names = {f.name for f in all_fields if not f.init}
        for k, v in data.items():
            if k in non_init_field_names:
                object.__setattr__(instance, k, v)
                
        return instance
    
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
            
            start = time.perf_counter()
            result = await query.single().execute()
            delta = 1000 * (time.perf_counter() - start)

            if not result.data:
                # Check if this dataclass should use defaults when not found
                if self._should_use_defaults(dataclass_type):
                    self.logger.info(f"No record found for {dataclass_type.__name__}, using defaults")
                    return dataclass_type(**primary_key_kwargs)
                return None
            
            self.logger.info(f"Single SELECT took {delta:.2f}ms")
            return self._dict_to_dataclass(dataclass_type, result.data)
            
        except Exception as e:
            self.logger.warning(f"Failed to select {dataclass_type.__name__}: {e}")
            # On error, also attempt to return defaults for settings tables
            if self._should_use_defaults(dataclass_type):
                self.logger.info(f"Error during select, using defaults for {dataclass_type.__name__}")
                return dataclass_type(**primary_key_kwargs)
            return None
    
    async def select_one(
        self,
        dataclass_type: Type[T],
        **filter_kwargs
    ) -> Optional[T]:
        """
        Select a single record by any combination of fields (not just primary key).
        
        Use this when you want to select by a unique combination of fields
        that isn't the primary key (e.g., server_id + tag for quotes).
        
        Args:
            dataclass_type: The dataclass type
            **filter_kwargs: Filter conditions (e.g., server_id=12345, tag="funny")
            
        Returns:
            Single dataclass instance or None if not found
            
        Examples:
            # Select quote by server_id + tag (unique combination)
            quote = await db.select_one(QuotesTable, server_id=12345, tag="funny")
            
            # Select talkback by server_id + id
            talkback = await db.select_one(TalkbacksTable, server_id=12345, id=42)
            
            # If multiple rows match, returns the first one
            user_motd = await db.select_one(MotdTable, user_id=12345)
        """
        try:
            table_name = self._get_table_name(dataclass_type)
            
            # Build query with filters
            query = self.supabase.table(table_name).select('*')
            for key, value in filter_kwargs.items():
                query = query.eq(key, value)
            
            start = time.perf_counter()
            # Use .limit(1) instead of .single() to avoid errors if not found
            result = await query.limit(1).execute()
            delta = 1000 * (time.perf_counter() - start)
            
            if not result.data or len(result.data) == 0:
                return None
            
            self.logger.info(f"Single SELECT (by filter) took {delta:.2f}ms")
            return self._dict_to_dataclass(dataclass_type, result.data[0])
            
        except Exception as e:
            self.logger.warning(f"Failed to select_one {dataclass_type.__name__}: {e}")
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
            
            start = time.perf_counter()
            result = await query.execute()
            delta = 1000 * (time.perf_counter() - start)
            
            if not result.data:
                return []
            
            self.logger.info(f"Multi SELECT took {delta:.2f}ms")
            return [self._dict_to_dataclass(dataclass_type, row) for row in result.data]
            
        except Exception as e:
            self.logger.error(f"Failed to select all {dataclass_type.__name__}: {e}")
            return []

    def insert(self, obj: T, _sync: bool = False) -> asyncio.Task:
        """
        Insert a new record (fire-and-forget by default).
        
        Args:
            obj: Dataclass instance to insert
            _sync: Whether to wait for completion (default False)
            
        Returns:
            asyncio.Task that resolves to Result[T, DatabaseError]
            
        Examples:
            # Fire and forget (most common)
            db.insert(TalkbackSettings(server_id=12345))
            
            # Wait for result
            result = await db.insert(TalkbackSettings(server_id=12345), _sync=True)
            if isinstance(result, Success):
                inserted_obj = result.unwrap()
        """
        
        async def _perform_insert():
            try:
                dataclass_type = type(obj)
                server_id = getattr(obj, 'server_id', None)
                table_name = self._get_table_name(dataclass_type)
                data = self._dataclass_to_dict(obj)
                
                # Skip writes in test mode unless it's the test guild
                if self.state.args.test and server_id and server_id != TEST_GUILD:
                    self.logger.info(f"Test mode: Blocking insert for server {server_id}")
                    return Success(obj)
                
                if self.supabase is None:
                    raise RuntimeError("Database not initialized. Call await db.initialize()")
                
                start = time.perf_counter()
                result = await self.supabase.table(table_name).insert(data).execute()
                delta = 1000 * (time.perf_counter() - start)
                
                if not result.data:
                    return Failure(DatabaseError("Insert failed - no data returned"))
                
                self.logger.info(f"Single INSERT took {delta:.2f}ms")
                return Success(self._dict_to_dataclass(dataclass_type, result.data[0]))
                
            except Exception as e:
                self.logger.error(f"Failed to insert {dataclass_type.__name__}: {e}", exc_info=True)
                return Failure(DatabaseError(f"Insert failed: {e}"))
        
        # Create task on current loop
        task = asyncio.create_task(_perform_insert())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        
        if _sync:
            # If user wants to await it, we return the task (which is awaitable)
            return task
        
        # If fire-and-forget, add a logger callback so errors aren't silent
        def _log_error(t):
            try:
                t.result()
            except Exception as e:
                self.logger.error(f"Background insert task failed: {e}")
        
        task.add_done_callback(_log_error)
        return task
    
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

                start = time.perf_counter()
                await self.supabase.table(table_name)\
                    .update(update_data)\
                    .eq(primary_key, pk_value)\
                    .execute()
                delta = 1000 * (time.perf_counter() - start)
                self.logger.info(f"Single UPDATE took {delta:.2f}ms")
                
                return Success(None)
                
            except Exception as e:
                self.logger.error(f"Failed to update: {e}", exc_info=True)
                return Failure(DatabaseError(f"Update failed: {e}"))

        # Create task on current loop
        task = asyncio.create_task(_perform_update())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

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

    def upsert(self, obj_or_type, _sync: bool = False, **kwargs) -> asyncio.Task:
        """
        Upsert a record (Insert a new record or Update if the primary key exists).
        
        Args:
            obj_or_type: Either a dataclass instance or a dataclass type.
            _sync: Whether to wait for completion (default False).
            **kwargs: If obj_or_type is a type, provide the column values here.
            
        Returns:
            asyncio.Task: A task that resolves to a Result (Success/Failure).
        
        Examples:
            # Upsert with instance
            db.upsert(TalkbackSettings(server_id=123, enabled=True))
            
            # Upsert with kwargs
            db.upsert(TalkbackSettings, server_id=123, enabled=True)
        """
        
        async def _perform_upsert():
            try:
                # 1. Check if passed a CLASS (Type)
                if isinstance(obj_or_type, type):
                    dataclass_type = obj_or_type
                    table_name = self._get_table_name(dataclass_type)
                    primary_key = self._get_primary_key(dataclass_type)
                    
                    if primary_key not in kwargs:
                        raise DatabaseError(f"Primary key '{primary_key}' not provided for upsert")
                    
                    # Extract ID for Test Mode check
                    pk_value = kwargs[primary_key]
                    server_id = pk_value if primary_key == "server_id" else kwargs.get("server_id")
                    
                    # Prepare data (filter out _sync and other non-field args if necessary)
                    # Note: We trust kwargs contains valid columns here, similar to update
                    upsert_data = {k: v for k, v in kwargs.items() if k != '_sync'}

                # 2. Check if passed an INSTANCE
                else:
                    dataclass_type = type(obj_or_type)
                    table_name = self._get_table_name(dataclass_type)
                    primary_key = self._get_primary_key(dataclass_type)
                    
                    # Extract ID for Test Mode check
                    pk_value = getattr(obj_or_type, primary_key)
                    server_id = getattr(obj_or_type, 'server_id', pk_value if primary_key == "server_id" else None)
                    
                    # Convert to dict
                    upsert_data = self._dataclass_to_dict(obj_or_type)

                # Skip writes in test mode unless it's the test guild
                target_id = server_id if server_id is not None else pk_value

                if self.state.args.test and server_id and server_id != TEST_GUILD:
                    self.logger.info(f"Test mode: Skipping upsert to ID {target_id}")
                    return Success(None)
                
                if self.supabase is None:
                    raise RuntimeError("Database not initialized. Call await db.initialize()")

                start = time.perf_counter()
                
                # Perform the Upsert
                # Note: Supabase upsert requires the Primary Key to be present in the data payload
                await self.supabase.table(table_name)\
                    .upsert(upsert_data)\
                    .execute()
                
                delta = 1000 * (time.perf_counter() - start)
                self.logger.info(f"Single UPSERT took {delta:.2f}ms")
                
                return Success(None)
                
            except Exception as e:
                self.logger.error(f"Failed to upsert: {e}", exc_info=True)
                return Failure(DatabaseError(f"Upsert failed: {e}"))

        # Create task on current loop
        task = asyncio.create_task(_perform_upsert())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

        if _sync:
            return task
        
        # Fire-and-forget error logging
        def _log_error(t):
            try:
                t.result()
            except Exception as e:
                self.logger.error(f"Background upsert task failed: {e}")
        
        task.add_done_callback(_log_error)
        return task

    async def count(
        self,
        dataclass_type: Type[T],
        **filter_kwargs
    ) -> int:
        """
        Count the number of rows in a table with optional filters.
        
        Args:
            dataclass_type: The dataclass type
            **filter_kwargs: Optional filter conditions (e.g., server_id=12345)
            
        Returns:
            Number of rows matching the filter
            
        Examples:
            # Count all quotes for a server
            num_quotes = await db.count(Quotes, server_id=12345)
            
            # Count total talkback settings (all servers)
            total_servers = await db.count(TalkbackSettings)
            
            # Count quotes with specific tag
            funny_quotes = await db.count(Quotes, server_id=12345, tag="funny")
        """
        try:
            table_name = self._get_table_name(dataclass_type)
            
            # Build query with filters
            query = self.supabase.table(table_name).select('*', count='exact')
            for key, value in filter_kwargs.items():
                query = query.eq(key, value)
            
            # Limit to 0 rows since we only want the count
            result = await query.limit(0).execute()
            
            # The count is in result.count
            return result.count if result.count is not None else 0
            
        except Exception as e:
            self.logger.error(f"Failed to count {dataclass_type.__name__}: {e}")
            return 0

    async def raw_query(
        self,
        query: str,
    ) -> Result[List[Dict[str, Any]], DatabaseError]:
        """
        Execute a raw SQL query for one-off use cases.
        
        WARNING: Use with caution! No validation or protection against SQL injection.
        Prefer using the type-safe methods (select, update, etc.) when possible.
        
        Args:
            query: SQL query string (use $1, $2, etc. for parameters)
            params: Optional dictionary of parameters for the query
            
        Returns:
            Result containing list of rows as dicts, or error
            
        Examples:
            # Simple query
            result = await db.raw_query("SELECT * FROM TalkbackSettings WHERE enabled = true")
            if isinstance(result, Success):
                rows = result.unwrap()
            
            # Query with parameters (safer)
            result = await db.raw_query(
                "SELECT * FROM Quotes WHERE server_id = $1 AND tag = $2",
                {"1": 12345, "2": "funny"}
            )
            
            # Complex aggregation
            result = await db.raw_query(
                '''
                SELECT server_id, COUNT(*) as quote_count 
                FROM Quotes 
                GROUP BY server_id 
                HAVING COUNT(*) > 10
                '''
            )
        """
        try:
            # Use Supabase RPC to execute raw SQL
            # Note: This requires a PostgreSQL function in your database
            # You'll need to create this function in Supabase:
            #
            # CREATE OR REPLACE FUNCTION execute_raw_sql(query text)
            # RETURNS json
            # LANGUAGE plpgsql
            # SECURITY DEFINER
            # AS $$
            # DECLARE
            #   result json;
            # BEGIN
            #   EXECUTE 'SELECT json_agg(row_to_json(t)) FROM (' || query || ') t' INTO result;
            #   RETURN COALESCE(result, '[]'::json);
            # END;
            # $$;
            
            result = await self.supabase.rpc('execute_raw_sql', {'query': query}).execute()
            
            if result.data is None:
                return Success([])
            
            return Success(result.data)
            
        except Exception as e:
            self.logger.error(f"Raw query failed: {e}")
            return Failure(DatabaseError(f"Raw query failed: {e}"))

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
            await self.insert(MotdTable(server_id=server_id, motd=""))
            
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
            result = await self.delete(MotdTable, server_id=server_id)
            
            if isinstance(result, Failure):
                return Some(result.failure())
            
            self.logger.info(f"Deleted server: {server_id}")
            return Nothing
            
        except Exception as e:
            self.logger.error(f"Failed to delete server {server_id}: {e}", exc_info=True)
            return Some(DatabaseError(f"Failed to delete server: {e}"))
    
    async def server_exists(self, server_id: int) -> bool:
        """Check if a server exists in the database."""
        # TODO: Maybe add a server metadata table for stuff like this?
        result = await self.select(TalkbackSettings, server_id=server_id)
        return result is not None


