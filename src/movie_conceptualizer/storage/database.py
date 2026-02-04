"""Database connection and setup for SQLite persistent storage.

This module provides async SQLite operations using aiosqlite,
including database initialization, migrations, and connection management.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import aiosqlite

if TYPE_CHECKING:
    from aiosqlite import Connection

# Default database path
DEFAULT_DB_DIR = Path.home() / ".movie-conceptualizer"
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "data.db"

# Current schema version
SCHEMA_VERSION = 1


class DatabaseError(Exception):
    """Base exception for database errors."""

    pass


class MigrationError(DatabaseError):
    """Error during database migration."""

    pass


class ConnectionError(DatabaseError):
    """Error establishing database connection."""

    pass


def get_database_path() -> Path:
    """Get the database file path from environment or default.

    Returns:
        Path to the SQLite database file.
    """
    env_path = os.environ.get("MOVIECON_DB_PATH")
    if env_path:
        return Path(env_path)
    return DEFAULT_DB_PATH


def ensure_db_directory(db_path: Path) -> None:
    """Ensure the database directory exists.

    Args:
        db_path: Path to the database file.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)


# SQL statements for table creation
CREATE_SCHEMA_VERSION_TABLE = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_PROJECTS_TABLE = """
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

CREATE_SCRIPTS_TABLE = """
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

CREATE_SCENES_TABLE = """
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

CREATE_SHOT_LISTS_TABLE = """
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

CREATE_STORYBOARDS_TABLE = """
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

CREATE_ANALYSES_TABLE = """
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

CREATE_PROJECT_ANALYSIS_TABLE = """
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

# Create indexes for common queries
CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_scripts_project_id ON scripts(project_id);
CREATE INDEX IF NOT EXISTS idx_scenes_project_id ON scenes(project_id);
CREATE INDEX IF NOT EXISTS idx_scenes_scene_number ON scenes(scene_number);
CREATE INDEX IF NOT EXISTS idx_shot_lists_project_id ON shot_lists(project_id);
CREATE INDEX IF NOT EXISTS idx_storyboards_project_id ON storyboards(project_id);
CREATE INDEX IF NOT EXISTS idx_analyses_project_id ON analyses(project_id);
CREATE INDEX IF NOT EXISTS idx_project_analyses_project_id ON project_analyses(project_id);
"""

# Migration definitions
MIGRATIONS: dict[int, list[str]] = {
    1: [
        CREATE_SCHEMA_VERSION_TABLE,
        CREATE_PROJECTS_TABLE,
        CREATE_SCRIPTS_TABLE,
        CREATE_SCENES_TABLE,
        CREATE_SHOT_LISTS_TABLE,
        CREATE_STORYBOARDS_TABLE,
        CREATE_ANALYSES_TABLE,
        CREATE_PROJECT_ANALYSIS_TABLE,
        CREATE_INDEXES,
    ],
}


class Database:
    """Async SQLite database manager with migration support.

    Handles database connections, schema migrations, and provides
    an async context manager for database operations.

    Example:
        db = Database()
        await db.initialize()

        async with db.connection() as conn:
            await conn.execute("SELECT * FROM projects")
    """

    def __init__(self, db_path: Path | str | None = None):
        """Initialize the database manager.

        Args:
            db_path: Optional custom path to the database file.
                    Uses MOVIECON_DB_PATH env var or default if not provided.
        """
        if db_path is None:
            self._db_path = get_database_path()
        else:
            self._db_path = Path(db_path)
        self._connection: Connection | None = None
        self._initialized = False

    @property
    def db_path(self) -> Path:
        """Get the database file path."""
        return self._db_path

    @property
    def is_initialized(self) -> bool:
        """Check if the database has been initialized."""
        return self._initialized

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
            for version in sorted(MIGRATIONS.keys()):
                if version > current_version:
                    await self._run_migration(conn, version)

            await conn.commit()

        self._initialized = True

    async def _get_schema_version(self, conn: Connection) -> int:
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

    async def _run_migration(self, conn: Connection, version: int) -> None:
        """Run a specific migration version.

        Args:
            conn: Database connection.
            version: Migration version to run.

        Raises:
            MigrationError: If migration fails.
        """
        if version not in MIGRATIONS:
            raise MigrationError(f"Unknown migration version: {version}")

        try:
            for sql in MIGRATIONS[version]:
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
    async def connection(self) -> AsyncIterator[Connection]:
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


# Global database instance
_db_instance: Database | None = None


def get_database() -> Database:
    """Get the global database instance.

    Returns:
        The global Database instance.
    """
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance


async def init_database(db_path: Path | str | None = None) -> Database:
    """Initialize the global database instance.

    Args:
        db_path: Optional custom path to the database file.

    Returns:
        The initialized Database instance.
    """
    global _db_instance
    _db_instance = Database(db_path)
    await _db_instance.initialize()
    return _db_instance


async def close_database() -> None:
    """Close the global database connection."""
    global _db_instance
    if _db_instance is not None:
        await _db_instance.close()
        _db_instance = None
