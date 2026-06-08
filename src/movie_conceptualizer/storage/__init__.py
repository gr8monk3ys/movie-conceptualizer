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
    # Base classes
    BaseDatabase,
    ConfigurationError,
    ConnectionError,
    # Backward compatibility alias
    Database,
    # Enums
    DatabaseBackend,
    # Exceptions
    DatabaseError,
    MigrationError,
    PostgreSQLDatabase,
    # Implementations
    SQLiteDatabase,
    close_database,
    # Factory and utility functions
    create_database,
    get_database,
    get_database_backend,
    get_database_path,
    get_pool_size,
    get_postgresql_url,
    init_database,
)

# Repository module exports
from movie_conceptualizer.storage.repositories import (
    # Base class
    BaseRepository,
    DuplicateError,
    GenerationRepository,
    # Models
    JobAuditLogModel,
    # Repositories
    JobAuditLogRepository,
    JobIdempotencyRepository,
    JobModel,
    JobRepository,
    NotFoundError,
    ProjectModel,
    ProjectRepository,
    ProjectStatus,
    RefreshTokenRepository,
    # Exceptions
    RepositoryError,
    SceneAnalysis,
    # Data schemas
    SceneData,
    ScriptModel,
    ScriptRepository,
    ShotData,
    StoryboardPrompt,
    UserModel,
    UserRepository,
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
    "JobRepository",
    "JobAuditLogRepository",
    "ProjectRepository",
    "UserRepository",
    "JobIdempotencyRepository",
    "RefreshTokenRepository",
    "ScriptRepository",
    "GenerationRepository",
    # Models
    "JobModel",
    "JobAuditLogModel",
    "ProjectModel",
    "UserModel",
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
