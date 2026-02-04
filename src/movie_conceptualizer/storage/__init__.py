"""Persistent storage module for Movie Conceptualizer.

This module provides async database storage with support for both
SQLite (using aiosqlite) and PostgreSQL (using asyncpg), with:
- Database connection and migration management
- Repository pattern for data access
- Pydantic model serialization/deserialization

Example usage:
    from movie_conceptualizer.storage import (
        create_database,
        init_database,
        ProjectRepository,
        ScriptRepository,
        GenerationRepository,
    )

    # Initialize database (uses MOVIECON_DB_BACKEND env var)
    db = await init_database()

    # Use repositories
    project_repo = ProjectRepository(db)
    project = await project_repo.create(title="My Film")

Environment Variables:
    MOVIECON_DB_BACKEND: Database backend ('sqlite' or 'postgresql')
                         Defaults to 'sqlite'
    MOVIECON_DB_PATH: Custom path for the SQLite database file.
                      Defaults to ~/.movie-conceptualizer/data.db
    MOVIECON_DATABASE_URL: PostgreSQL connection string
    DATABASE_URL: Fallback PostgreSQL connection string
    MOVIECON_DB_POOL_SIZE: Connection pool size for PostgreSQL (default: 5)
"""

# Database module exports
from movie_conceptualizer.storage.database import (
    # Enums
    DatabaseBackend,
    # Base classes
    BaseDatabase,
    # Implementations
    SQLiteDatabase,
    PostgreSQLDatabase,
    # Backward compatibility alias
    Database,
    # Exceptions
    DatabaseError,
    MigrationError,
    ConnectionError,
    ConfigurationError,
    # Factory and utility functions
    create_database,
    get_database,
    get_database_path,
    get_database_backend,
    get_postgresql_url,
    get_pool_size,
    init_database,
    close_database,
)

# Repository module exports
from movie_conceptualizer.storage.repositories import (
    # Base class
    BaseRepository,
    # Repositories
    ProjectRepository,
    ScriptRepository,
    GenerationRepository,
    # Models
    ProjectModel,
    ScriptModel,
    # Data schemas
    SceneData,
    SceneAnalysis,
    ShotData,
    StoryboardPrompt,
    ProjectStatus,
    # Exceptions
    RepositoryError,
    NotFoundError,
    DuplicateError,
)

__all__ = [
    # Database Enums
    "DatabaseBackend",
    # Database Base Classes
    "BaseDatabase",
    # Database Implementations
    "SQLiteDatabase",
    "PostgreSQLDatabase",
    "Database",  # Backward compatibility alias for SQLiteDatabase
    # Database Exceptions
    "DatabaseError",
    "MigrationError",
    "ConnectionError",
    "ConfigurationError",
    # Database Functions
    "create_database",
    "get_database",
    "get_database_path",
    "get_database_backend",
    "get_postgresql_url",
    "get_pool_size",
    "init_database",
    "close_database",
    # Repository Base
    "BaseRepository",
    # Repositories
    "ProjectRepository",
    "ScriptRepository",
    "GenerationRepository",
    # Models
    "ProjectModel",
    "ScriptModel",
    # Data Schemas
    "SceneData",
    "SceneAnalysis",
    "ShotData",
    "StoryboardPrompt",
    "ProjectStatus",
    # Repository Exceptions
    "RepositoryError",
    "NotFoundError",
    "DuplicateError",
]
