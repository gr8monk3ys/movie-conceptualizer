"""Database connection and setup for persistent storage.

This module provides async database operations with support for both
SQLite (using aiosqlite) and PostgreSQL (using asyncpg), including
database initialization, migrations, and connection management.

Environment Variables:
    MOVIECON_DB_BACKEND: Database backend to use ('sqlite' or 'postgresql')
    MOVIECON_DB_PATH: Path to SQLite database file (SQLite only)
    MOVIECON_DATABASE_URL: PostgreSQL connection string
    DATABASE_URL: Fallback PostgreSQL connection string
    MOVIECON_DB_POOL_SIZE: Connection pool size for PostgreSQL (default: 5)
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

import aiosqlite

if TYPE_CHECKING:
    from aiosqlite import Connection as SQLiteConnection

# Default database path for SQLite
DEFAULT_DB_DIR = Path.home() / ".movie-conceptualizer"
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "data.db"

# Current schema version
SCHEMA_VERSION = 1


class DatabaseBackend(StrEnum):
    """Supported database backends."""

    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"


class DatabaseError(Exception):
    """Base exception for database errors."""

    pass


class MigrationError(DatabaseError):
    """Error during database migration."""

    pass


class ConnectionError(DatabaseError):
    """Error establishing database connection."""

    pass


class ConfigurationError(DatabaseError):
    """Error in database configuration."""

    pass


@runtime_checkable
class DatabaseConnection(Protocol):
    """Protocol for database connections."""

    async def execute(self, query: str, params: tuple[Any, ...] | None = None) -> Any:
        """Execute a query."""
        ...

    async def fetchone(self) -> Any:
        """Fetch one result."""
        ...

    async def fetchall(self) -> list[Any]:
        """Fetch all results."""
        ...


def get_database_backend() -> DatabaseBackend:
    """Get the configured database backend.

    Returns:
        The configured DatabaseBackend enum value.
    """
    backend = os.environ.get("MOVIECON_DB_BACKEND", "sqlite").lower()
    if backend == "postgresql":
        return DatabaseBackend.POSTGRESQL
    return DatabaseBackend.SQLITE


def get_database_path() -> Path:
    """Get the SQLite database file path from environment or default.

    Returns:
        Path to the SQLite database file.
    """
    env_path = os.environ.get("MOVIECON_DB_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_DB_PATH


def get_postgresql_url() -> str | None:
    """Get the PostgreSQL connection URL from environment.

    Returns:
        PostgreSQL connection string or None if not configured.
    """
    return os.environ.get("MOVIECON_DATABASE_URL") or os.environ.get("DATABASE_URL")


def get_pool_size() -> int:
    """Get the connection pool size for PostgreSQL.

    Returns:
        Pool size (default: 5).
    """
    try:
        return int(os.environ.get("MOVIECON_DB_POOL_SIZE", "5"))
    except ValueError:
        return 5


def ensure_db_directory(db_path: Path) -> None:
    """Ensure the database directory exists.

    Args:
        db_path: Path to the database file.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)


# =============================================================================
# SQLite Schema Definitions
# =============================================================================

SQLITE_CREATE_SCHEMA_VERSION_TABLE = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

SQLITE_CREATE_PROJECTS_TABLE = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    genre TEXT,
    style_notes TEXT,
    status TEXT NOT NULL DEFAULT 'created',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    progress REAL DEFAULT 0.0,
    current_step TEXT,
    steps_completed TEXT DEFAULT '[]',
    error_message TEXT,
    processing_started_at TIMESTAMP,
    processing_completed_at TIMESTAMP
);
"""

SQLITE_CREATE_SCRIPTS_TABLE = """
CREATE TABLE IF NOT EXISTS scripts (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL UNIQUE,
    content TEXT NOT NULL,
    format TEXT NOT NULL DEFAULT 'fountain',
    title TEXT,
    author TEXT,
    parsed_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
"""

SQLITE_CREATE_SCENES_TABLE = """
CREATE TABLE IF NOT EXISTS scenes (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    scene_number INTEGER NOT NULL,
    heading TEXT NOT NULL,
    location TEXT,
    time_of_day TEXT,
    int_ext TEXT,
    description TEXT,
    characters TEXT DEFAULT '[]',
    dialogue TEXT DEFAULT '[]',
    raw_content TEXT DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    UNIQUE(project_id, scene_number)
);
"""

SQLITE_CREATE_SHOT_LISTS_TABLE = """
CREATE TABLE IF NOT EXISTS shot_lists (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    scene_number INTEGER NOT NULL,
    shots TEXT NOT NULL DEFAULT '[]',
    total_shots INTEGER DEFAULT 0,
    estimated_duration REAL,
    style TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
"""

SQLITE_CREATE_STORYBOARDS_TABLE = """
CREATE TABLE IF NOT EXISTS storyboards (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    prompts TEXT NOT NULL DEFAULT '[]',
    total_prompts INTEGER DEFAULT 0,
    style TEXT,
    aspect_ratio TEXT DEFAULT '16:9',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
"""

SQLITE_CREATE_ANALYSES_TABLE = """
CREATE TABLE IF NOT EXISTS analyses (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    scene_number INTEGER NOT NULL,
    mood TEXT,
    themes TEXT DEFAULT '[]',
    visual_style TEXT,
    pacing TEXT,
    key_moments TEXT DEFAULT '[]',
    color_palette TEXT DEFAULT '[]',
    lighting_notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    UNIQUE(project_id, scene_number)
);
"""

SQLITE_CREATE_PROJECT_ANALYSIS_TABLE = """
CREATE TABLE IF NOT EXISTS project_analyses (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL UNIQUE,
    overall_tone TEXT,
    visual_motifs TEXT DEFAULT '[]',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
"""

SQLITE_CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_scripts_project_id ON scripts(project_id);
CREATE INDEX IF NOT EXISTS idx_scenes_project_id ON scenes(project_id);
CREATE INDEX IF NOT EXISTS idx_scenes_scene_number ON scenes(scene_number);
CREATE INDEX IF NOT EXISTS idx_shot_lists_project_id ON shot_lists(project_id);
CREATE INDEX IF NOT EXISTS idx_storyboards_project_id ON storyboards(project_id);
CREATE INDEX IF NOT EXISTS idx_analyses_project_id ON analyses(project_id);
CREATE INDEX IF NOT EXISTS idx_project_analyses_project_id ON project_analyses(project_id);
"""

# SQLite migration definitions
SQLITE_MIGRATIONS: dict[int, list[str]] = {
    1: [
        SQLITE_CREATE_SCHEMA_VERSION_TABLE,
        SQLITE_CREATE_PROJECTS_TABLE,
        SQLITE_CREATE_SCRIPTS_TABLE,
        SQLITE_CREATE_SCENES_TABLE,
        SQLITE_CREATE_SHOT_LISTS_TABLE,
        SQLITE_CREATE_STORYBOARDS_TABLE,
        SQLITE_CREATE_ANALYSES_TABLE,
        SQLITE_CREATE_PROJECT_ANALYSIS_TABLE,
        SQLITE_CREATE_INDEXES,
    ],
}

# =============================================================================
# PostgreSQL Schema Definitions
# =============================================================================

POSTGRESQL_CREATE_SCHEMA_VERSION_TABLE = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
"""

POSTGRESQL_CREATE_PROJECTS_TABLE = """
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    genre TEXT,
    style_notes TEXT,
    status TEXT NOT NULL DEFAULT 'created',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    progress DOUBLE PRECISION DEFAULT 0.0,
    current_step TEXT,
    steps_completed JSONB DEFAULT '[]'::jsonb,
    error_message TEXT,
    processing_started_at TIMESTAMP WITH TIME ZONE,
    processing_completed_at TIMESTAMP WITH TIME ZONE
);
"""

POSTGRESQL_CREATE_SCRIPTS_TABLE = """
CREATE TABLE IF NOT EXISTS scripts (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL UNIQUE REFERENCES projects(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    format TEXT NOT NULL DEFAULT 'fountain',
    title TEXT,
    author TEXT,
    parsed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

POSTGRESQL_CREATE_SCENES_TABLE = """
CREATE TABLE IF NOT EXISTS scenes (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    scene_number INTEGER NOT NULL,
    heading TEXT NOT NULL,
    location TEXT,
    time_of_day TEXT,
    int_ext TEXT,
    description TEXT,
    characters JSONB DEFAULT '[]'::jsonb,
    dialogue JSONB DEFAULT '[]'::jsonb,
    raw_content TEXT DEFAULT '',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, scene_number)
);
"""

POSTGRESQL_CREATE_SHOT_LISTS_TABLE = """
CREATE TABLE IF NOT EXISTS shot_lists (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    scene_number INTEGER NOT NULL,
    shots JSONB NOT NULL DEFAULT '[]'::jsonb,
    total_shots INTEGER DEFAULT 0,
    estimated_duration DOUBLE PRECISION,
    style TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

POSTGRESQL_CREATE_STORYBOARDS_TABLE = """
CREATE TABLE IF NOT EXISTS storyboards (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    prompts JSONB NOT NULL DEFAULT '[]'::jsonb,
    total_prompts INTEGER DEFAULT 0,
    style TEXT,
    aspect_ratio TEXT DEFAULT '16:9',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

POSTGRESQL_CREATE_ANALYSES_TABLE = """
CREATE TABLE IF NOT EXISTS analyses (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    scene_number INTEGER NOT NULL,
    mood TEXT,
    themes JSONB DEFAULT '[]'::jsonb,
    visual_style TEXT,
    pacing TEXT,
    key_moments JSONB DEFAULT '[]'::jsonb,
    color_palette JSONB DEFAULT '[]'::jsonb,
    lighting_notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, scene_number)
);
"""

POSTGRESQL_CREATE_PROJECT_ANALYSIS_TABLE = """
CREATE TABLE IF NOT EXISTS project_analyses (
    id UUID PRIMARY KEY,
    project_id UUID NOT NULL UNIQUE REFERENCES projects(id) ON DELETE CASCADE,
    overall_tone TEXT,
    visual_motifs JSONB DEFAULT '[]'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

POSTGRESQL_CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_scripts_project_id ON scripts(project_id);
CREATE INDEX IF NOT EXISTS idx_scenes_project_id ON scenes(project_id);
CREATE INDEX IF NOT EXISTS idx_scenes_scene_number ON scenes(scene_number);
CREATE INDEX IF NOT EXISTS idx_shot_lists_project_id ON shot_lists(project_id);
CREATE INDEX IF NOT EXISTS idx_storyboards_project_id ON storyboards(project_id);
CREATE INDEX IF NOT EXISTS idx_analyses_project_id ON analyses(project_id);
CREATE INDEX IF NOT EXISTS idx_project_analyses_project_id ON project_analyses(project_id);
"""

# PostgreSQL migration definitions
POSTGRESQL_MIGRATIONS: dict[int, list[str]] = {
    1: [
        POSTGRESQL_CREATE_SCHEMA_VERSION_TABLE,
        POSTGRESQL_CREATE_PROJECTS_TABLE,
        POSTGRESQL_CREATE_SCRIPTS_TABLE,
        POSTGRESQL_CREATE_SCENES_TABLE,
        POSTGRESQL_CREATE_SHOT_LISTS_TABLE,
        POSTGRESQL_CREATE_STORYBOARDS_TABLE,
        POSTGRESQL_CREATE_ANALYSES_TABLE,
        POSTGRESQL_CREATE_PROJECT_ANALYSIS_TABLE,
        POSTGRESQL_CREATE_INDEXES,
    ],
}


# =============================================================================
# Abstract Base Database Class
# =============================================================================


class BaseDatabase(ABC):
    """Abstract base class for database backends.

    Defines the common interface that all database backends must implement.
    """

    @property
    @abstractmethod
    def backend(self) -> DatabaseBackend:
        """Get the database backend type."""
        ...

    @property
    @abstractmethod
    def is_initialized(self) -> bool:
        """Check if the database has been initialized."""
        ...

    @property
    @abstractmethod
    def placeholder(self) -> str:
        """Get the parameter placeholder for this backend.

        Returns:
            '?' for SQLite, '$' for PostgreSQL (numbered: $1, $2, etc.)
        """
        ...

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the database and run migrations."""
        ...

    @abstractmethod
    @asynccontextmanager
    async def connection(self) -> AsyncIterator[Any]:
        """Get an async context manager for database connections."""
        yield  # pragma: no cover

    @abstractmethod
    async def close(self) -> None:
        """Close the database connection(s)."""
        ...

    @abstractmethod
    async def reset(self) -> None:
        """Reset the database (delete all data)."""
        ...

    def format_query(self, query: str, param_count: int = 0) -> str:
        """Format a query for this backend's placeholder style.

        Converts queries with numbered placeholders ({1}, {2}, etc.) to the
        backend-specific format.

        Args:
            query: Query string with {1}, {2}, etc. placeholders.
            param_count: Number of parameters (for validation).

        Returns:
            Formatted query string.
        """
        # For SQLite, replace {n} with ?
        # For PostgreSQL, replace {n} with $n
        if self.backend == DatabaseBackend.SQLITE:
            result = query
            for i in range(1, param_count + 1):
                result = result.replace(f"{{{i}}}", "?")
            return result
        else:
            result = query
            for i in range(1, param_count + 1):
                result = result.replace(f"{{{i}}}", f"${i}")
            return result


# =============================================================================
# SQLite Database Implementation
# =============================================================================


class SQLiteDatabase(BaseDatabase):
    """Async SQLite database manager with migration support.

    Handles database connections, schema migrations, and provides
    an async context manager for database operations.

    Example:
        db = SQLiteDatabase()
        await db.initialize()

        async with db.connection() as conn:
            await conn.execute("SELECT * FROM projects")
    """

    def __init__(self, db_path: Path | str | None = None):
        """Initialize the SQLite database manager.

        Args:
            db_path: Optional custom path to the database file.
                    Uses MOVIECON_DB_PATH env var or default if not provided.
        """
        if db_path is None:
            self._db_path = get_database_path()
        else:
            self._db_path = Path(db_path)
        self._connection: SQLiteConnection | None = None
        self._initialized = False

    @property
    def backend(self) -> DatabaseBackend:
        """Get the database backend type."""
        return DatabaseBackend.SQLITE

    @property
    def db_path(self) -> Path:
        """Get the database file path."""
        return self._db_path

    @property
    def is_initialized(self) -> bool:
        """Check if the database has been initialized."""
        return self._initialized

    @property
    def placeholder(self) -> str:
        """Get the parameter placeholder for SQLite."""
        return "?"

    async def initialize(self) -> None:
        """Initialize the database and run migrations.

        Creates the database file and directory if they don't exist,
        then runs any pending migrations.

        Raises:
            MigrationError: If migration fails.
        """
        ensure_db_directory(self._db_path)

        async with aiosqlite.connect(self._db_path) as conn:
            # Enable foreign keys
            await conn.execute("PRAGMA foreign_keys = ON")

            # Get current schema version
            current_version = await self._get_schema_version(conn)

            # Run pending migrations
            for version in sorted(SQLITE_MIGRATIONS.keys()):
                if version > current_version:
                    await self._run_migration(conn, version)

            await conn.commit()

        self._initialized = True

    async def _get_schema_version(self, conn: SQLiteConnection) -> int:
        """Get the current schema version from the database.

        Args:
            conn: Database connection.

        Returns:
            Current schema version, or 0 if not set.
        """
        try:
            cursor = await conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'"
            )
            if await cursor.fetchone() is None:
                return 0

            cursor = await conn.execute(
                "SELECT MAX(version) FROM schema_version"
            )
            row = await cursor.fetchone()
            return row[0] if row and row[0] is not None else 0
        except Exception:
            return 0

    async def _run_migration(self, conn: SQLiteConnection, version: int) -> None:
        """Run a specific migration version.

        Args:
            conn: Database connection.
            version: Migration version to run.

        Raises:
            MigrationError: If migration fails.
        """
        if version not in SQLITE_MIGRATIONS:
            raise MigrationError(f"Unknown migration version: {version}")

        try:
            for sql in SQLITE_MIGRATIONS[version]:
                # Execute multi-statement SQL
                for statement in sql.strip().split(";"):
                    statement = statement.strip()
                    if statement:
                        await conn.execute(statement)

            # Record the migration
            await conn.execute(
                "INSERT INTO schema_version (version) VALUES (?)",
                (version,)
            )
        except Exception as e:
            raise MigrationError(f"Migration to version {version} failed: {e}") from e

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[SQLiteConnection]:
        """Get an async context manager for database connections.

        Yields:
            An aiosqlite connection.

        Raises:
            ConnectionError: If database is not initialized.

        Example:
            async with db.connection() as conn:
                await conn.execute("SELECT * FROM projects")
        """
        if not self._initialized:
            await self.initialize()

        async with aiosqlite.connect(self._db_path) as conn:
            # Enable foreign keys
            await conn.execute("PRAGMA foreign_keys = ON")
            # Return rows as sqlite3.Row for dict-like access
            conn.row_factory = aiosqlite.Row
            try:
                yield conn
            except Exception:
                await conn.rollback()
                raise
            else:
                await conn.commit()

    async def close(self) -> None:
        """Close the database connection if open."""
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    async def reset(self) -> None:
        """Reset the database by deleting the file and reinitializing.

        WARNING: This will delete all data!
        """
        await self.close()
        if self._db_path.exists():
            self._db_path.unlink()
        self._initialized = False
        await self.initialize()


# =============================================================================
# PostgreSQL Database Implementation
# =============================================================================


class PostgreSQLDatabase(BaseDatabase):
    """Async PostgreSQL database manager with connection pooling.

    Handles database connections, schema migrations, and provides
    an async context manager for database operations using asyncpg.

    Example:
        db = PostgreSQLDatabase("postgresql://user:pass@localhost/dbname")
        await db.initialize()

        async with db.connection() as conn:
            await conn.execute("SELECT * FROM projects")
    """

    def __init__(
        self,
        database_url: str | None = None,
        pool_size: int | None = None,
    ):
        """Initialize the PostgreSQL database manager.

        Args:
            database_url: PostgreSQL connection string. Uses MOVIECON_DATABASE_URL
                         or DATABASE_URL env var if not provided.
            pool_size: Connection pool size. Uses MOVIECON_DB_POOL_SIZE env var
                      or default of 5 if not provided.

        Raises:
            ConfigurationError: If no database URL is configured.
        """
        self._database_url = database_url or get_postgresql_url()
        if not self._database_url:
            raise ConfigurationError(
                "PostgreSQL database URL not configured. "
                "Set MOVIECON_DATABASE_URL or DATABASE_URL environment variable."
            )
        self._pool_size = pool_size or get_pool_size()
        self._pool: Any = None  # asyncpg.Pool
        self._initialized = False

    @property
    def backend(self) -> DatabaseBackend:
        """Get the database backend type."""
        return DatabaseBackend.POSTGRESQL

    @property
    def is_initialized(self) -> bool:
        """Check if the database has been initialized."""
        return self._initialized

    @property
    def placeholder(self) -> str:
        """Get the parameter placeholder for PostgreSQL."""
        return "$"

    @property
    def pool(self) -> Any:
        """Get the connection pool."""
        return self._pool

    async def initialize(self) -> None:
        """Initialize the database and run migrations.

        Creates the connection pool and runs any pending migrations.

        Raises:
            MigrationError: If migration fails.
            ConfigurationError: If asyncpg is not installed.
        """
        try:
            import asyncpg
        except ImportError as e:
            raise ConfigurationError(
                "asyncpg is required for PostgreSQL support. "
                "Install with: pip install movie-conceptualizer[postgresql]"
            ) from e

        # Create connection pool
        self._pool = await asyncpg.create_pool(
            self._database_url,
            min_size=1,
            max_size=self._pool_size,
        )

        # Run migrations
        async with self._pool.acquire() as conn:
            # Get current schema version
            current_version = await self._get_schema_version(conn)

            # Run pending migrations
            for version in sorted(POSTGRESQL_MIGRATIONS.keys()):
                if version > current_version:
                    await self._run_migration(conn, version)

        self._initialized = True

    async def _get_schema_version(self, conn: Any) -> int:
        """Get the current schema version from the database.

        Args:
            conn: Database connection (asyncpg.Connection).

        Returns:
            Current schema version, or 0 if not set.
        """
        try:
            # Check if schema_version table exists
            result = await conn.fetchval(
                """
                SELECT EXISTS (
                    SELECT FROM information_schema.tables
                    WHERE table_name = 'schema_version'
                )
                """
            )
            if not result:
                return 0

            version = await conn.fetchval(
                "SELECT MAX(version) FROM schema_version"
            )
            return version if version is not None else 0
        except Exception:
            return 0

    async def _run_migration(self, conn: Any, version: int) -> None:
        """Run a specific migration version.

        Args:
            conn: Database connection (asyncpg.Connection).
            version: Migration version to run.

        Raises:
            MigrationError: If migration fails.
        """
        if version not in POSTGRESQL_MIGRATIONS:
            raise MigrationError(f"Unknown migration version: {version}")

        try:
            for sql in POSTGRESQL_MIGRATIONS[version]:
                # Execute multi-statement SQL
                for statement in sql.strip().split(";"):
                    statement = statement.strip()
                    if statement:
                        await conn.execute(statement)

            # Record the migration
            await conn.execute(
                "INSERT INTO schema_version (version) VALUES ($1)",
                version
            )
        except Exception as e:
            raise MigrationError(f"Migration to version {version} failed: {e}") from e

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[Any]:
        """Get an async context manager for database connections.

        Yields:
            An asyncpg connection from the pool.

        Raises:
            ConnectionError: If database is not initialized.

        Example:
            async with db.connection() as conn:
                await conn.execute("SELECT * FROM projects")
        """
        if not self._initialized:
            await self.initialize()

        if self._pool is None:
            raise ConnectionError("Database pool not initialized")

        async with self._pool.acquire() as conn:
            # Start a transaction
            async with conn.transaction():
                yield conn

    async def close(self) -> None:
        """Close the connection pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None

    async def reset(self) -> None:
        """Reset the database by dropping and recreating all tables.

        WARNING: This will delete all data!
        """
        if self._pool is None:
            await self.initialize()
            return

        async with self._pool.acquire() as conn:
            # Drop all tables
            await conn.execute("DROP TABLE IF EXISTS storyboards CASCADE")
            await conn.execute("DROP TABLE IF EXISTS shot_lists CASCADE")
            await conn.execute("DROP TABLE IF EXISTS analyses CASCADE")
            await conn.execute("DROP TABLE IF EXISTS project_analyses CASCADE")
            await conn.execute("DROP TABLE IF EXISTS scenes CASCADE")
            await conn.execute("DROP TABLE IF EXISTS scripts CASCADE")
            await conn.execute("DROP TABLE IF EXISTS projects CASCADE")
            await conn.execute("DROP TABLE IF EXISTS schema_version CASCADE")

        self._initialized = False
        await self.initialize()


# =============================================================================
# Factory Function and Global Instance Management
# =============================================================================


# Alias for backward compatibility
Database = SQLiteDatabase


def create_database(
    backend: DatabaseBackend | str | None = None,
    **kwargs: Any,
) -> BaseDatabase:
    """Create a database instance based on configuration.

    Factory function that creates the appropriate database backend based on
    environment configuration or explicit backend parameter.

    Args:
        backend: Database backend to use. If None, uses MOVIECON_DB_BACKEND env var.
        **kwargs: Backend-specific arguments:
            - SQLite: db_path
            - PostgreSQL: database_url, pool_size

    Returns:
        A database instance (SQLiteDatabase or PostgreSQLDatabase).

    Raises:
        ConfigurationError: If PostgreSQL is selected but not configured.

    Example:
        # Use environment configuration
        db = create_database()

        # Explicitly use SQLite
        db = create_database(backend="sqlite", db_path="/tmp/test.db")

        # Explicitly use PostgreSQL
        db = create_database(
            backend="postgresql",
            database_url="postgresql://user:pass@localhost/dbname"
        )
    """
    if backend is None:
        backend = get_database_backend()
    elif isinstance(backend, str):
        backend = DatabaseBackend(backend.lower())

    if backend == DatabaseBackend.POSTGRESQL:
        return PostgreSQLDatabase(
            database_url=kwargs.get("database_url"),
            pool_size=kwargs.get("pool_size"),
        )
    else:
        return SQLiteDatabase(db_path=kwargs.get("db_path"))


# Global database instance
_db_instance: BaseDatabase | None = None


def get_database() -> BaseDatabase:
    """Get the global database instance.

    Creates a new instance if one doesn't exist, using environment configuration.

    Returns:
        The global database instance.
    """
    global _db_instance
    if _db_instance is None:
        _db_instance = create_database()
    return _db_instance


async def init_database(
    db_path: Path | str | None = None,
    backend: DatabaseBackend | str | None = None,
    **kwargs: Any,
) -> BaseDatabase:
    """Initialize the global database instance.

    Args:
        db_path: Optional custom path for SQLite database file.
        backend: Optional backend override.
        **kwargs: Additional backend-specific arguments.

    Returns:
        The initialized database instance.
    """
    global _db_instance

    # If db_path is provided without backend, assume SQLite for backward compatibility
    if db_path is not None and backend is None:
        _db_instance = SQLiteDatabase(db_path)
    else:
        _db_instance = create_database(backend=backend, db_path=db_path, **kwargs)

    await _db_instance.initialize()
    return _db_instance


async def close_database() -> None:
    """Close the global database connection."""
    global _db_instance
    if _db_instance is not None:
        await _db_instance.close()
        _db_instance = None


# Keep old migration dict for backward compatibility in tests
MIGRATIONS = SQLITE_MIGRATIONS
