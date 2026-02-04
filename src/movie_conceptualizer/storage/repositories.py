"""Repository pattern for data access.

This module provides repository classes for CRUD operations on
both SQLite and PostgreSQL databases, using Pydantic models for serialization.

The repositories handle the differences between database backends transparently,
including parameter placeholder styles (? vs $1) and JSON field handling.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, TypeVar
from uuid import uuid4

from pydantic import BaseModel, Field

from movie_conceptualizer.storage.database import (
    BaseDatabase,
    DatabaseBackend,
    get_database,
)

if TYPE_CHECKING:
    pass


# Type variables for generic repository
T = TypeVar("T", bound=BaseModel)


# Define schemas locally to avoid circular imports with api.schemas
# These are storage-layer representations that map to database columns


class ProjectStatus(StrEnum):
    """Project processing status."""

    CREATED = "created"
    SCRIPT_UPLOADED = "script_uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    ANALYZING = "analyzing"
    ANALYZED = "analyzed"
    GENERATING_SHOTS = "generating_shots"
    SHOTS_GENERATED = "shots_generated"
    GENERATING_STORYBOARD = "generating_storyboard"
    COMPLETED = "completed"
    ERROR = "error"


class SceneData(BaseModel):
    """Schema for parsed scene data."""

    scene_number: int = Field(..., description="Scene number")
    heading: str = Field(..., description="Scene heading")
    location: str | None = Field(default=None)
    time_of_day: str | None = Field(default=None)
    int_ext: str | None = Field(default=None)
    description: str | None = Field(default=None)
    characters: list[str] = Field(default_factory=list)
    dialogue: list[dict[str, str]] = Field(default_factory=list)
    raw_content: str = Field(default="")


class SceneAnalysis(BaseModel):
    """Schema for scene analysis data."""

    scene_number: int = Field(...)
    mood: str | None = Field(default=None)
    themes: list[str] = Field(default_factory=list)
    visual_style: str | None = Field(default=None)
    pacing: str | None = Field(default=None)
    key_moments: list[str] = Field(default_factory=list)
    color_palette: list[str] = Field(default_factory=list)
    lighting_notes: str | None = Field(default=None)


class ShotData(BaseModel):
    """Schema for shot data."""

    scene_number: int = Field(...)
    shot_number: str = Field(...)
    shot_type: str = Field(...)
    camera_movement: str | None = Field(default=None)
    camera_angle: str | None = Field(default=None)
    description: str = Field(...)
    duration_seconds: float | None = Field(default=None)
    characters: list[str] = Field(default_factory=list)
    notes: str | None = Field(default=None)


class StoryboardPrompt(BaseModel):
    """Schema for storyboard prompt data."""

    shot_id: str = Field(...)
    scene_number: int = Field(...)
    shot_number: str = Field(...)
    image_prompt: str = Field(...)
    composition_notes: str | None = Field(default=None)
    lighting_notes: str | None = Field(default=None)
    style_reference: str | None = Field(default=None)


class RepositoryError(Exception):
    """Base exception for repository errors."""

    pass


class NotFoundError(RepositoryError):
    """Entity not found in the database."""

    def __init__(self, entity_type: str, entity_id: str):
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(f"{entity_type} with ID '{entity_id}' not found")


class DuplicateError(RepositoryError):
    """Duplicate entity error."""

    def __init__(self, entity_type: str, entity_id: str):
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(f"{entity_type} with ID '{entity_id}' already exists")


def _json_dumps(data: Any) -> str:
    """Serialize data to JSON string."""
    if isinstance(data, BaseModel):
        return data.model_dump_json()
    return json.dumps(data, default=str)


def _json_loads(data: str | list | dict | None) -> Any:
    """Deserialize JSON string or already-parsed data.

    PostgreSQL JSONB fields return already-parsed Python objects,
    while SQLite TEXT fields return JSON strings that need parsing.
    """
    if data is None:
        return None
    if isinstance(data, (list, dict)):
        # Already parsed (PostgreSQL JSONB)
        return data
    return json.loads(data)


def _row_to_dict(row: Any, backend: DatabaseBackend) -> dict[str, Any]:
    """Convert a database row to a dictionary.

    Args:
        row: Database row (sqlite3.Row or asyncpg.Record).
        backend: The database backend being used.

    Returns:
        Dictionary of column names to values.
    """
    if backend == DatabaseBackend.POSTGRESQL:
        # asyncpg.Record is already dict-like
        return dict(row)
    else:
        # sqlite3.Row
        return dict(row)


class ProjectModel(BaseModel):
    """Pydantic model for project database representation."""

    id: str
    title: str
    description: str | None = None
    genre: str | None = None
    style_notes: str | None = None
    status: ProjectStatus = ProjectStatus.CREATED
    created_at: datetime
    updated_at: datetime
    progress: float = 0.0
    current_step: str | None = None
    steps_completed: list[str] = []
    error_message: str | None = None
    processing_started_at: datetime | None = None
    processing_completed_at: datetime | None = None

    # Computed fields from related data
    has_script: bool = False
    scene_count: int = 0
    shot_count: int = 0

    model_config = {"from_attributes": True}


class ScriptModel(BaseModel):
    """Pydantic model for script database representation."""

    id: str
    project_id: str
    content: str
    format: str = "fountain"
    title: str | None = None
    author: str | None = None
    parsed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BaseRepository:
    """Base repository with common database operations.

    Provides helper methods for working with different database backends.
    """

    def __init__(self, database: BaseDatabase | None = None):
        """Initialize the repository.

        Args:
            database: Database instance. Uses global instance if not provided.
        """
        self._db = database or get_database()

    @property
    def backend(self) -> DatabaseBackend:
        """Get the database backend type."""
        return self._db.backend

    def _param(self, index: int) -> str:
        """Get the parameter placeholder for the given index.

        Args:
            index: 1-based parameter index.

        Returns:
            '?' for SQLite, '$n' for PostgreSQL.
        """
        if self.backend == DatabaseBackend.POSTGRESQL:
            return f"${index}"
        return "?"

    def _params(self, count: int) -> str:
        """Get comma-separated parameter placeholders.

        Args:
            count: Number of parameters.

        Returns:
            Comma-separated placeholder string (e.g., "?, ?, ?" or "$1, $2, $3").
        """
        if self.backend == DatabaseBackend.POSTGRESQL:
            return ", ".join(f"${i}" for i in range(1, count + 1))
        return ", ".join("?" for _ in range(count))

    async def _execute(
        self, conn: Any, query: str, params: tuple[Any, ...] | None = None
    ) -> Any:
        """Execute a query with backend-appropriate handling.

        Args:
            conn: Database connection.
            query: SQL query string.
            params: Query parameters (optional).

        Returns:
            Cursor (SQLite) or result string (PostgreSQL).
        """
        if self.backend == DatabaseBackend.POSTGRESQL:
            if params:
                return await conn.execute(query, *params)
            return await conn.execute(query)
        else:
            if params:
                return await conn.execute(query, params)
            return await conn.execute(query)

    async def _fetchone(self, conn: Any, query: str, params: tuple[Any, ...] | None = None) -> Any:
        """Execute a query and fetch one row.

        Args:
            conn: Database connection.
            query: SQL query string.
            params: Query parameters (optional).

        Returns:
            Single row or None.
        """
        if self.backend == DatabaseBackend.POSTGRESQL:
            if params:
                return await conn.fetchrow(query, *params)
            return await conn.fetchrow(query)
        else:
            if params:
                cursor = await conn.execute(query, params)
            else:
                cursor = await conn.execute(query)
            return await cursor.fetchone()

    async def _fetchall(self, conn: Any, query: str, params: tuple[Any, ...] | None = None) -> list[Any]:
        """Execute a query and fetch all rows.

        Args:
            conn: Database connection.
            query: SQL query string.
            params: Query parameters (optional).

        Returns:
            List of rows.
        """
        if self.backend == DatabaseBackend.POSTGRESQL:
            if params:
                return await conn.fetch(query, *params)
            return await conn.fetch(query)
        else:
            if params:
                cursor = await conn.execute(query, params)
            else:
                cursor = await conn.execute(query)
            return await cursor.fetchall()

    async def _fetchval(self, conn: Any, query: str, params: tuple[Any, ...] | None = None) -> Any:
        """Execute a query and fetch a single value.

        Args:
            conn: Database connection.
            query: SQL query string.
            params: Query parameters (optional).

        Returns:
            Single value or None.
        """
        if self.backend == DatabaseBackend.POSTGRESQL:
            if params:
                return await conn.fetchval(query, *params)
            return await conn.fetchval(query)
        else:
            if params:
                cursor = await conn.execute(query, params)
            else:
                cursor = await conn.execute(query)
            row = await cursor.fetchone()
            return row[0] if row else None

    def _serialize_json(self, data: Any) -> Any:
        """Serialize data for JSON storage.

        Args:
            data: Data to serialize.

        Returns:
            JSON string for SQLite, Python object for PostgreSQL.
        """
        if self.backend == DatabaseBackend.POSTGRESQL:
            # PostgreSQL JSONB accepts Python objects directly
            if isinstance(data, BaseModel):
                return data.model_dump()
            return data
        else:
            # SQLite needs JSON string
            return _json_dumps(data)


class ProjectRepository(BaseRepository):
    """Repository for project CRUD operations.

    Provides async methods for creating, reading, updating, and deleting
    projects in the database.

    Example:
        repo = ProjectRepository(db)
        project = await repo.create(title="My Film", genre="drama")
        projects = await repo.list_all()
    """

    async def create(
        self,
        title: str,
        description: str | None = None,
        genre: str | None = None,
        style_notes: str | None = None,
    ) -> ProjectModel:
        """Create a new project.

        Args:
            title: Project title.
            description: Optional project description.
            genre: Optional film genre.
            style_notes: Optional visual style notes.

        Returns:
            The created ProjectModel.
        """
        project_id = str(uuid4())
        now = datetime.utcnow()

        async with self._db.connection() as conn:
            query = f"""
                INSERT INTO projects
                (id, title, description, genre, style_notes, status, created_at, updated_at)
                VALUES ({self._params(8)})
            """
            await self._execute(
                conn,
                query,
                (
                    project_id, title, description, genre, style_notes,
                    ProjectStatus.CREATED, now, now
                ),
            )

        return ProjectModel(
            id=project_id,
            title=title,
            description=description,
            genre=genre,
            style_notes=style_notes,
            status=ProjectStatus.CREATED,
            created_at=now,
            updated_at=now,
        )

    async def get(self, project_id: str) -> ProjectModel | None:
        """Get a project by ID.

        Args:
            project_id: The project ID.

        Returns:
            The ProjectModel if found, None otherwise.
        """
        async with self._db.connection() as conn:
            query = f"SELECT * FROM projects WHERE id = {self._param(1)}"
            row = await self._fetchone(conn, query, (project_id,))

            if row is None:
                return None

            project = self._row_to_project(row)

            # Get related counts
            count_query = f"SELECT COUNT(*) FROM scripts WHERE project_id = {self._param(1)}"
            script_count = await self._fetchval(conn, count_query, (project_id,))
            project.has_script = (script_count or 0) > 0

            count_query = f"SELECT COUNT(*) FROM scenes WHERE project_id = {self._param(1)}"
            scene_count = await self._fetchval(conn, count_query, (project_id,))
            project.scene_count = scene_count or 0

            count_query = f"SELECT SUM(total_shots) FROM shot_lists WHERE project_id = {self._param(1)}"
            shot_count = await self._fetchval(conn, count_query, (project_id,))
            project.shot_count = shot_count or 0

            return project

    async def get_or_raise(self, project_id: str) -> ProjectModel:
        """Get a project by ID or raise NotFoundError.

        Args:
            project_id: The project ID.

        Returns:
            The ProjectModel.

        Raises:
            NotFoundError: If project is not found.
        """
        project = await self.get(project_id)
        if project is None:
            raise NotFoundError("Project", project_id)
        return project

    async def list_all(self) -> list[ProjectModel]:
        """List all projects.

        Returns:
            List of all ProjectModels.
        """
        async with self._db.connection() as conn:
            query = "SELECT * FROM projects ORDER BY updated_at DESC"
            rows = await self._fetchall(conn, query)

            projects = []
            for row in rows:
                project = self._row_to_project(row)

                # Get related counts
                count_query = f"SELECT COUNT(*) FROM scripts WHERE project_id = {self._param(1)}"
                script_count = await self._fetchval(conn, count_query, (project.id,))
                project.has_script = (script_count or 0) > 0

                count_query = f"SELECT COUNT(*) FROM scenes WHERE project_id = {self._param(1)}"
                scene_count = await self._fetchval(conn, count_query, (project.id,))
                project.scene_count = scene_count or 0

                count_query = f"SELECT SUM(total_shots) FROM shot_lists WHERE project_id = {self._param(1)}"
                shot_count = await self._fetchval(conn, count_query, (project.id,))
                project.shot_count = shot_count or 0

                projects.append(project)

            return projects

    async def update(
        self,
        project_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        genre: str | None = None,
        style_notes: str | None = None,
        status: ProjectStatus | None = None,
        progress: float | None = None,
        current_step: str | None = None,
        steps_completed: list[str] | None = None,
        error_message: str | None = None,
        processing_started_at: datetime | None = None,
        processing_completed_at: datetime | None = None,
    ) -> ProjectModel:
        """Update a project.

        Args:
            project_id: The project ID.
            **kwargs: Fields to update.

        Returns:
            The updated ProjectModel.

        Raises:
            NotFoundError: If project is not found.
        """
        # Build update query dynamically
        updates: list[str] = []
        values: list[Any] = []
        param_idx = 1

        if title is not None:
            updates.append(f"title = {self._param(param_idx)}")
            values.append(title)
            param_idx += 1
        if description is not None:
            updates.append(f"description = {self._param(param_idx)}")
            values.append(description)
            param_idx += 1
        if genre is not None:
            updates.append(f"genre = {self._param(param_idx)}")
            values.append(genre)
            param_idx += 1
        if style_notes is not None:
            updates.append(f"style_notes = {self._param(param_idx)}")
            values.append(style_notes)
            param_idx += 1
        if status is not None:
            updates.append(f"status = {self._param(param_idx)}")
            values.append(status)
            param_idx += 1
        if progress is not None:
            updates.append(f"progress = {self._param(param_idx)}")
            values.append(progress)
            param_idx += 1
        if current_step is not None:
            updates.append(f"current_step = {self._param(param_idx)}")
            values.append(current_step)
            param_idx += 1
        if steps_completed is not None:
            updates.append(f"steps_completed = {self._param(param_idx)}")
            values.append(self._serialize_json(steps_completed))
            param_idx += 1
        if error_message is not None:
            updates.append(f"error_message = {self._param(param_idx)}")
            values.append(error_message)
            param_idx += 1
        if processing_started_at is not None:
            updates.append(f"processing_started_at = {self._param(param_idx)}")
            values.append(processing_started_at)
            param_idx += 1
        if processing_completed_at is not None:
            updates.append(f"processing_completed_at = {self._param(param_idx)}")
            values.append(processing_completed_at)
            param_idx += 1

        # Always update the timestamp
        updates.append(f"updated_at = {self._param(param_idx)}")
        values.append(datetime.utcnow())
        param_idx += 1

        values.append(project_id)

        async with self._db.connection() as conn:
            query = f"UPDATE projects SET {', '.join(updates)} WHERE id = {self._param(param_idx)}"

            if self.backend == DatabaseBackend.POSTGRESQL:
                result = await conn.execute(query, *values)
                # Check if any rows were updated
                if result == "UPDATE 0":
                    raise NotFoundError("Project", project_id)
            else:
                cursor = await conn.execute(query, tuple(values))
                if cursor.rowcount == 0:
                    raise NotFoundError("Project", project_id)

        return await self.get_or_raise(project_id)

    async def delete(self, project_id: str) -> bool:
        """Delete a project by ID.

        Args:
            project_id: The project ID.

        Returns:
            True if deleted, False if not found.
        """
        async with self._db.connection() as conn:
            query = f"DELETE FROM projects WHERE id = {self._param(1)}"

            if self.backend == DatabaseBackend.POSTGRESQL:
                result = await conn.execute(query, project_id)
                return result != "DELETE 0"
            else:
                cursor = await conn.execute(query, (project_id,))
                return cursor.rowcount > 0

    async def exists(self, project_id: str) -> bool:
        """Check if a project exists.

        Args:
            project_id: The project ID.

        Returns:
            True if project exists.
        """
        async with self._db.connection() as conn:
            query = f"SELECT 1 FROM projects WHERE id = {self._param(1)}"
            row = await self._fetchone(conn, query, (project_id,))
            return row is not None

    def _row_to_project(self, row: Any) -> ProjectModel:
        """Convert a database row to a ProjectModel."""
        data = _row_to_dict(row, self.backend)
        # Convert UUID to string if needed
        if "id" in data and not isinstance(data["id"], str):
            data["id"] = str(data["id"])
        # Parse JSON fields
        if data.get("steps_completed"):
            data["steps_completed"] = _json_loads(data["steps_completed"])
        else:
            data["steps_completed"] = []
        return ProjectModel(**data)


class ScriptRepository(BaseRepository):
    """Repository for script CRUD operations.

    Handles script content storage and retrieval, as well as
    parsed scene data.

    Example:
        repo = ScriptRepository(db)
        await repo.save_script(project_id, content, "fountain")
        script = await repo.get_script(project_id)
    """

    async def save_script(
        self,
        project_id: str,
        content: str,
        format: str = "fountain",
        title: str | None = None,
        author: str | None = None,
    ) -> ScriptModel:
        """Save or update a script for a project.

        Args:
            project_id: The project ID.
            content: Script content.
            format: Script format (e.g., "fountain").
            title: Optional script title.
            author: Optional script author.

        Returns:
            The saved ScriptModel.
        """
        script_id = str(uuid4())
        now = datetime.utcnow()

        async with self._db.connection() as conn:
            # Check if script already exists for this project
            query = f"SELECT id FROM scripts WHERE project_id = {self._param(1)}"
            existing = await self._fetchone(conn, query, (project_id,))

            if existing:
                # Update existing script
                update_query = f"""
                    UPDATE scripts
                    SET content = {self._param(1)}, format = {self._param(2)},
                        title = {self._param(3)}, author = {self._param(4)},
                        updated_at = {self._param(5)}
                    WHERE project_id = {self._param(6)}
                """
                await self._execute(
                    conn,
                    update_query,
                    (content, format, title, author, now, project_id),
                )
                # Get the existing script ID
                script_id = str(existing[0]) if self.backend == DatabaseBackend.POSTGRESQL else existing[0]
            else:
                # Insert new script
                insert_query = f"""
                    INSERT INTO scripts
                    (id, project_id, content, format, title, author, created_at, updated_at)
                    VALUES ({self._params(8)})
                """
                await self._execute(
                    conn,
                    insert_query,
                    (script_id, project_id, content, format, title, author, now, now),
                )

        return ScriptModel(
            id=script_id,
            project_id=project_id,
            content=content,
            format=format,
            title=title,
            author=author,
            created_at=now,
            updated_at=now,
        )

    async def get_script(self, project_id: str) -> ScriptModel | None:
        """Get a script by project ID.

        Args:
            project_id: The project ID.

        Returns:
            The ScriptModel if found, None otherwise.
        """
        async with self._db.connection() as conn:
            query = f"SELECT * FROM scripts WHERE project_id = {self._param(1)}"
            row = await self._fetchone(conn, query, (project_id,))

            if row is None:
                return None

            data = _row_to_dict(row, self.backend)
            # Convert UUIDs to strings
            if "id" in data and not isinstance(data["id"], str):
                data["id"] = str(data["id"])
            if "project_id" in data and not isinstance(data["project_id"], str):
                data["project_id"] = str(data["project_id"])
            return ScriptModel(**data)

    async def update_parsed_info(
        self,
        project_id: str,
        title: str | None = None,
        author: str | None = None,
    ) -> None:
        """Update parsed info for a script.

        Args:
            project_id: The project ID.
            title: Parsed script title.
            author: Parsed script author.
        """
        now = datetime.utcnow()

        async with self._db.connection() as conn:
            query = f"""
                UPDATE scripts
                SET title = {self._param(1)}, author = {self._param(2)},
                    parsed_at = {self._param(3)}, updated_at = {self._param(4)}
                WHERE project_id = {self._param(5)}
            """
            await self._execute(conn, query, (title, author, now, now, project_id))

    async def save_scenes(
        self,
        project_id: str,
        scenes: list[SceneData],
    ) -> None:
        """Save parsed scenes for a project.

        Replaces any existing scenes for the project.

        Args:
            project_id: The project ID.
            scenes: List of parsed SceneData.
        """
        async with self._db.connection() as conn:
            # Delete existing scenes
            delete_query = f"DELETE FROM scenes WHERE project_id = {self._param(1)}"
            await self._execute(conn, delete_query, (project_id,))

            # Insert new scenes
            for scene in scenes:
                scene_id = str(uuid4())
                insert_query = f"""
                    INSERT INTO scenes
                    (id, project_id, scene_number, heading, location, time_of_day,
                     int_ext, description, characters, dialogue, raw_content, created_at)
                    VALUES ({self._params(12)})
                """
                await self._execute(
                    conn,
                    insert_query,
                    (
                        scene_id,
                        project_id,
                        scene.scene_number,
                        scene.heading,
                        scene.location,
                        scene.time_of_day,
                        scene.int_ext,
                        scene.description,
                        self._serialize_json(scene.characters),
                        self._serialize_json(scene.dialogue),
                        scene.raw_content,
                        datetime.utcnow(),
                    ),
                )

    async def get_scenes(self, project_id: str) -> list[SceneData]:
        """Get all scenes for a project.

        Args:
            project_id: The project ID.

        Returns:
            List of SceneData.
        """
        async with self._db.connection() as conn:
            query = f"SELECT * FROM scenes WHERE project_id = {self._param(1)} ORDER BY scene_number"
            rows = await self._fetchall(conn, query, (project_id,))

            scenes = []
            for row in rows:
                data = _row_to_dict(row, self.backend)
                # Parse JSON fields
                data["characters"] = _json_loads(data.get("characters", "[]"))
                data["dialogue"] = _json_loads(data.get("dialogue", "[]"))
                scenes.append(SceneData(**data))

            return scenes

    async def delete_script(self, project_id: str) -> bool:
        """Delete a script and its scenes.

        Args:
            project_id: The project ID.

        Returns:
            True if deleted.
        """
        async with self._db.connection() as conn:
            # Scenes are deleted via CASCADE
            query = f"DELETE FROM scripts WHERE project_id = {self._param(1)}"

            if self.backend == DatabaseBackend.POSTGRESQL:
                result = await conn.execute(query, project_id)
                return result != "DELETE 0"
            else:
                cursor = await conn.execute(query, (project_id,))
                return cursor.rowcount > 0


class GenerationRepository(BaseRepository):
    """Repository for storing analysis results, shot lists, and storyboards.

    Handles all AI-generated content storage and retrieval.

    Example:
        repo = GenerationRepository(db)
        await repo.save_analyses(project_id, analyses, tone, motifs)
        await repo.save_shots(project_id, shots)
    """

    # --- Analysis Methods ---

    async def save_analyses(
        self,
        project_id: str,
        analyses: list[SceneAnalysis],
        overall_tone: str | None = None,
        visual_motifs: list[str] | None = None,
    ) -> None:
        """Save scene analyses for a project.

        Args:
            project_id: The project ID.
            analyses: List of SceneAnalysis.
            overall_tone: Overall tone of the project.
            visual_motifs: List of visual motifs.
        """
        now = datetime.utcnow()

        async with self._db.connection() as conn:
            # Delete existing analyses
            delete_query = f"DELETE FROM analyses WHERE project_id = {self._param(1)}"
            await self._execute(conn, delete_query, (project_id,))

            # Insert new analyses
            for analysis in analyses:
                analysis_id = str(uuid4())
                insert_query = f"""
                    INSERT INTO analyses
                    (id, project_id, scene_number, mood, themes, visual_style,
                     pacing, key_moments, color_palette, lighting_notes, created_at)
                    VALUES ({self._params(11)})
                """
                await self._execute(
                    conn,
                    insert_query,
                    (
                        analysis_id,
                        project_id,
                        analysis.scene_number,
                        analysis.mood,
                        self._serialize_json(analysis.themes),
                        analysis.visual_style,
                        analysis.pacing,
                        self._serialize_json(analysis.key_moments),
                        self._serialize_json(analysis.color_palette),
                        analysis.lighting_notes,
                        now,
                    ),
                )

            # Save or update project-level analysis
            check_query = f"SELECT id FROM project_analyses WHERE project_id = {self._param(1)}"
            existing = await self._fetchone(conn, check_query, (project_id,))

            if existing:
                update_query = f"""
                    UPDATE project_analyses
                    SET overall_tone = {self._param(1)}, visual_motifs = {self._param(2)},
                        updated_at = {self._param(3)}
                    WHERE project_id = {self._param(4)}
                """
                await self._execute(
                    conn,
                    update_query,
                    (overall_tone, self._serialize_json(visual_motifs or []), now, project_id),
                )
            else:
                pa_id = str(uuid4())
                insert_query = f"""
                    INSERT INTO project_analyses
                    (id, project_id, overall_tone, visual_motifs, created_at, updated_at)
                    VALUES ({self._params(6)})
                """
                await self._execute(
                    conn,
                    insert_query,
                    (
                        pa_id, project_id, overall_tone,
                        self._serialize_json(visual_motifs or []), now, now
                    ),
                )

    async def get_analyses(self, project_id: str) -> list[SceneAnalysis]:
        """Get scene analyses for a project.

        Args:
            project_id: The project ID.

        Returns:
            List of SceneAnalysis.
        """
        async with self._db.connection() as conn:
            query = f"SELECT * FROM analyses WHERE project_id = {self._param(1)} ORDER BY scene_number"
            rows = await self._fetchall(conn, query, (project_id,))

            analyses = []
            for row in rows:
                data = _row_to_dict(row, self.backend)
                data["themes"] = _json_loads(data.get("themes", "[]"))
                data["key_moments"] = _json_loads(data.get("key_moments", "[]"))
                data["color_palette"] = _json_loads(data.get("color_palette", "[]"))
                analyses.append(SceneAnalysis(**data))

            return analyses

    async def get_project_analysis(
        self, project_id: str
    ) -> tuple[str | None, list[str]]:
        """Get project-level analysis info.

        Args:
            project_id: The project ID.

        Returns:
            Tuple of (overall_tone, visual_motifs).
        """
        async with self._db.connection() as conn:
            query = f"""
                SELECT overall_tone, visual_motifs FROM project_analyses
                WHERE project_id = {self._param(1)}
            """
            row = await self._fetchone(conn, query, (project_id,))

            if row is None:
                return None, []

            data = _row_to_dict(row, self.backend)
            return data.get("overall_tone"), _json_loads(data.get("visual_motifs", "[]"))

    # --- Shot List Methods ---

    async def save_shots(
        self,
        project_id: str,
        shots: list[ShotData],
        style: str | None = None,
    ) -> None:
        """Save shot list for a project.

        Args:
            project_id: The project ID.
            shots: List of ShotData.
            style: Optional style used for generation.
        """
        now = datetime.utcnow()

        async with self._db.connection() as conn:
            # Delete existing shot lists
            delete_query = f"DELETE FROM shot_lists WHERE project_id = {self._param(1)}"
            await self._execute(conn, delete_query, (project_id,))

            # Group shots by scene
            shots_by_scene: dict[int, list[ShotData]] = {}
            for shot in shots:
                if shot.scene_number not in shots_by_scene:
                    shots_by_scene[shot.scene_number] = []
                shots_by_scene[shot.scene_number].append(shot)

            # Insert shot lists grouped by scene
            for scene_number, scene_shots in shots_by_scene.items():
                shot_list_id = str(uuid4())
                total_duration = sum(s.duration_seconds or 0 for s in scene_shots)

                # Serialize shots to JSON
                shots_data = [s.model_dump() for s in scene_shots]

                insert_query = f"""
                    INSERT INTO shot_lists
                    (id, project_id, scene_number, shots, total_shots,
                     estimated_duration, style, created_at, updated_at)
                    VALUES ({self._params(9)})
                """
                await self._execute(
                    conn,
                    insert_query,
                    (
                        shot_list_id,
                        project_id,
                        scene_number,
                        self._serialize_json(shots_data),
                        len(scene_shots),
                        total_duration if total_duration > 0 else None,
                        style,
                        now,
                        now,
                    ),
                )

    async def get_shots(self, project_id: str) -> list[ShotData]:
        """Get all shots for a project.

        Args:
            project_id: The project ID.

        Returns:
            List of ShotData.
        """
        async with self._db.connection() as conn:
            query = f"SELECT shots FROM shot_lists WHERE project_id = {self._param(1)} ORDER BY scene_number"
            rows = await self._fetchall(conn, query, (project_id,))

            all_shots = []
            for row in rows:
                shots_data = row[0] if self.backend == DatabaseBackend.POSTGRESQL else row[0]
                shots_list = _json_loads(shots_data)
                for shot_dict in shots_list:
                    all_shots.append(ShotData(**shot_dict))

            return all_shots

    async def get_shot_count(self, project_id: str) -> int:
        """Get total shot count for a project.

        Args:
            project_id: The project ID.

        Returns:
            Total number of shots.
        """
        async with self._db.connection() as conn:
            query = f"SELECT SUM(total_shots) FROM shot_lists WHERE project_id = {self._param(1)}"
            result = await self._fetchval(conn, query, (project_id,))
            return result or 0

    async def get_estimated_duration(self, project_id: str) -> float | None:
        """Get total estimated duration for a project.

        Args:
            project_id: The project ID.

        Returns:
            Total duration in seconds, or None.
        """
        async with self._db.connection() as conn:
            query = f"SELECT SUM(estimated_duration) FROM shot_lists WHERE project_id = {self._param(1)}"
            result = await self._fetchval(conn, query, (project_id,))
            return result if result else None

    # --- Storyboard Methods ---

    async def save_storyboard(
        self,
        project_id: str,
        prompts: list[StoryboardPrompt],
        style: str | None = None,
        aspect_ratio: str = "16:9",
    ) -> None:
        """Save storyboard prompts for a project.

        Args:
            project_id: The project ID.
            prompts: List of StoryboardPrompt.
            style: Optional style used for generation.
            aspect_ratio: Aspect ratio for the storyboard.
        """
        now = datetime.utcnow()

        async with self._db.connection() as conn:
            # Delete existing storyboard
            delete_query = f"DELETE FROM storyboards WHERE project_id = {self._param(1)}"
            await self._execute(conn, delete_query, (project_id,))

            # Insert new storyboard
            storyboard_id = str(uuid4())
            prompts_data = [p.model_dump() for p in prompts]

            insert_query = f"""
                INSERT INTO storyboards
                (id, project_id, prompts, total_prompts, style, aspect_ratio,
                 created_at, updated_at)
                VALUES ({self._params(8)})
            """
            await self._execute(
                conn,
                insert_query,
                (
                    storyboard_id,
                    project_id,
                    self._serialize_json(prompts_data),
                    len(prompts),
                    style,
                    aspect_ratio,
                    now,
                    now,
                ),
            )

    async def get_storyboard_prompts(
        self, project_id: str
    ) -> list[StoryboardPrompt]:
        """Get storyboard prompts for a project.

        Args:
            project_id: The project ID.

        Returns:
            List of StoryboardPrompt.
        """
        async with self._db.connection() as conn:
            query = f"SELECT prompts FROM storyboards WHERE project_id = {self._param(1)}"
            row = await self._fetchone(conn, query, (project_id,))

            if row is None:
                return []

            prompts_data = row[0] if self.backend == DatabaseBackend.POSTGRESQL else row[0]
            prompts_list = _json_loads(prompts_data)
            return [StoryboardPrompt(**p) for p in prompts_list]

    async def get_storyboard_count(self, project_id: str) -> int:
        """Get total storyboard prompt count for a project.

        Args:
            project_id: The project ID.

        Returns:
            Total number of prompts.
        """
        async with self._db.connection() as conn:
            query = f"SELECT total_prompts FROM storyboards WHERE project_id = {self._param(1)}"
            result = await self._fetchval(conn, query, (project_id,))
            return result or 0
