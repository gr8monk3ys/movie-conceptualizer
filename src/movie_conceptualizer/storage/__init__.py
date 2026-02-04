"""SQLite persistent storage module for Movie Conceptualizer.

This module provides async SQLite storage using aiosqlite, with:
- Database connection and migration management
- Repository pattern for data access
- Pydantic model serialization/deserialization

Example usage:
    from movie_conceptualizer.storage import (
        Database,
        init_database,
        ProjectRepository,
        ScriptRepository,
        GenerationRepository,
    )

    # Initialize database
    db = await init_database()

    # Use repositories
    project_repo = ProjectRepository(db)
    project = await project_repo.create(title="My Film")

Environment Variables:
    MOVIECON_DB_PATH: Custom path for the SQLite database file.
                      Defaults to ~/.movie-conceptualizer/data.db
"""

# Database module exports
from movie_conceptualizer.storage.database import (
    ConnectionError,
    Database,
    DatabaseError,
    MigrationError,
    close_database,
    get_database,
    get_database_path,
    init_database,
)

# Repository module exports
from movie_conceptualizer.storage.repositories import (
    DuplicateError,
    GenerationRepository,
    NotFoundError,
    ProjectModel,
    ProjectRepository,
    RepositoryError,
    ScriptModel,
    ScriptRepository,
)

__all__ = [
    # Database
    "Database",
    "DatabaseError",
    "MigrationError",
    "ConnectionError",
    "get_database",
    "get_database_path",
    "init_database",
    "close_database",
    # Repositories
    "ProjectRepository",
    "ScriptRepository",
    "GenerationRepository",
    # Models
    "ProjectModel",
    "ScriptModel",
    # Exceptions
    "RepositoryError",
    "NotFoundError",
    "DuplicateError",
]
