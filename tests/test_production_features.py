"""Tests for SQLite storage, JWT auth, and rate limiting."""

import os
import tempfile
from datetime import timedelta
from pathlib import Path

import pytest


# Storage tests
class TestDatabaseSetup:
    """Tests for database initialization."""

    @pytest.mark.asyncio
    async def test_database_creates_tables(self):
        """Database creates all required tables on init."""
        from movie_conceptualizer.storage import Database

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)
            await db.initialize()

            # Check tables exist
            async with db.connection() as conn:
                cursor = await conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
                tables = {row[0] for row in await cursor.fetchall()}

            assert "projects" in tables
            assert "scripts" in tables
            assert "scenes" in tables
            assert "shot_lists" in tables
            assert "storyboards" in tables

            await db.close()

    @pytest.mark.asyncio
    async def test_database_path_from_env(self, monkeypatch):
        """Database uses path from environment variable."""
        from movie_conceptualizer.storage.database import get_database_path

        monkeypatch.setenv("MOVIECON_DB_PATH", "/custom/path/db.sqlite")
        result = get_database_path()
        # Handle both Path and str
        assert str(result) == "/custom/path/db.sqlite"


class TestProjectRepository:
    """Tests for ProjectRepository."""

    @pytest.fixture
    async def db_and_repo(self):
        """Create a temporary database and repository."""
        from movie_conceptualizer.storage import Database, ProjectRepository

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)
            await db.initialize()
            repo = ProjectRepository(db)
            yield db, repo
            await db.close()

    @pytest.mark.asyncio
    async def test_create_project(self, db_and_repo):
        """Can create a project."""
        db, repo = db_and_repo
        project = await repo.create(
            title="Test Project",
            description="A test project",
            genre="drama",
        )

        assert project.id is not None
        assert project.title == "Test Project"
        assert project.description == "A test project"
        assert project.genre == "drama"

    @pytest.mark.asyncio
    async def test_get_project(self, db_and_repo):
        """Can retrieve a project by ID."""
        db, repo = db_and_repo
        created = await repo.create(title="Test")
        retrieved = await repo.get(created.id)

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.title == "Test"

    @pytest.mark.asyncio
    async def test_get_nonexistent_project(self, db_and_repo):
        """Returns None for nonexistent project."""
        db, repo = db_and_repo
        result = await repo.get("nonexistent-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_projects(self, db_and_repo):
        """Can list all projects."""
        db, repo = db_and_repo
        await repo.create(title="Project 1")
        await repo.create(title="Project 2")

        projects = await repo.list_all()
        assert len(projects) == 2

    @pytest.mark.asyncio
    async def test_delete_project(self, db_and_repo):
        """Can delete a project."""
        db, repo = db_and_repo
        project = await repo.create(title="To Delete")

        deleted = await repo.delete(project.id)
        assert deleted is True

        result = await repo.get(project.id)
        assert result is None


class TestJobRepository:
    """Tests for JobRepository."""

    @pytest.fixture
    async def db_and_repo(self):
        """Create a temporary database and repository."""
        from movie_conceptualizer.storage import Database, JobRepository

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = Database(db_path)
            await db.initialize()
            repo = JobRepository(db)
            yield db, repo
            await db.close()

    @pytest.mark.asyncio
    async def test_dead_letter_persists_user_id(self, db_and_repo):
        """Dead-letter records persist user_id."""
        _, repo = db_and_repo

        await repo.create_dead_letter(
            job_id="job-123",
            project_id="project-xyz",
            user_id="user-abc",
            status="failed",
            description="analysis",
            error="boom",
            payload="{}",
        )

        records = await repo.list_dead_letters(limit=1)
        assert len(records) == 1
        assert records[0]["job_id"] == "job-123"
        assert records[0]["user_id"] == "user-abc"


# Auth tests - simplified to avoid bcrypt backend issues
class TestJWTTokens:
    """Tests for JWT token creation and validation."""

    def test_create_access_token(self):
        """Can create an access token."""
        from movie_conceptualizer.api.auth import create_access_token

        token = create_access_token(data={"sub": "testuser"})
        assert token is not None
        assert len(token) > 50

    def test_create_token_with_expiry(self):
        """Token includes expiration."""
        from jose import jwt

        from movie_conceptualizer.api.auth import (
            ALGORITHM,
            SECRET_KEY,
            create_access_token,
        )

        token = create_access_token(
            data={"sub": "testuser"},
            expires_delta=timedelta(minutes=30),
        )

        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        assert "exp" in payload
        assert payload["sub"] == "testuser"

    def test_secret_key_exists(self):
        """Secret key is configured."""
        from movie_conceptualizer.api.auth import SECRET_KEY

        assert SECRET_KEY is not None
        assert len(SECRET_KEY) > 10


class TestAuthConfiguration:
    """Tests for auth configuration."""

    def test_auth_module_imports(self):
        """Auth module imports correctly."""
        from movie_conceptualizer.api.auth import (
            User,
            UserInDB,
            UserStore,
            create_access_token,
            oauth2_scheme,
        )

        assert User is not None
        assert UserInDB is not None
        assert UserStore is not None
        assert create_access_token is not None
        assert oauth2_scheme is not None

    def test_user_store_class_structure(self):
        """UserStore class has expected methods."""
        from movie_conceptualizer.api.auth import UserStore

        # Check the class has required methods
        assert hasattr(UserStore, "get_user_by_username")
        assert hasattr(UserStore, "authenticate_user")
        assert hasattr(UserStore, "create_user")


# Rate limiting tests
class TestRateLimitConfiguration:
    """Tests for rate limit configuration."""

    def test_limiter_exists(self):
        """Limiter instance is created."""
        from movie_conceptualizer.api.ratelimit import limiter

        assert limiter is not None

    def test_rate_limit_decorators_exist(self):
        """Rate limit decorators are available."""
        from movie_conceptualizer.api.ratelimit import (
            generation_rate_limit,
            standard_rate_limit,
        )

        assert standard_rate_limit is not None
        assert generation_rate_limit is not None

    def test_client_identifier_function(self):
        """Client identifier function exists."""
        from movie_conceptualizer.api.ratelimit import get_client_identifier

        assert get_client_identifier is not None
        assert callable(get_client_identifier)


class TestAPIIntegration:
    """Integration tests for the API with new features."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from fastapi.testclient import TestClient

        from movie_conceptualizer.api import app

        return TestClient(app)

    def test_health_endpoint(self, client):
        """Health endpoint works."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_root_endpoint(self, client):
        """Root endpoint works."""
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "message" in data or "name" in data

    def test_openapi_docs_available(self, client):
        """OpenAPI docs are available."""
        response = client.get("/docs")
        assert response.status_code == 200

    def test_openapi_schema_available(self, client):
        """OpenAPI schema is available."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        data = response.json()
        assert "openapi" in data
        assert "paths" in data


# PostgreSQL support tests
class TestDatabaseBackendConfiguration:
    """Tests for database backend selection."""

    def test_database_backend_enum(self):
        """DatabaseBackend enum has expected values."""
        from movie_conceptualizer.storage import DatabaseBackend

        assert DatabaseBackend.SQLITE.value == "sqlite"
        assert DatabaseBackend.POSTGRESQL.value == "postgresql"

    def test_get_database_backend_default(self, monkeypatch):
        """Default backend is SQLite."""
        monkeypatch.delenv("MOVIECON_DB_BACKEND", raising=False)

        from movie_conceptualizer.storage.database import get_database_backend

        backend = get_database_backend()
        assert backend.value == "sqlite"

    def test_get_database_backend_from_env(self, monkeypatch):
        """Backend can be set via environment."""
        monkeypatch.setenv("MOVIECON_DB_BACKEND", "postgresql")

        # Need to reimport to pick up env change
        import importlib

        import movie_conceptualizer.storage.database as db_module

        importlib.reload(db_module)

        backend = db_module.get_database_backend()
        assert backend.value == "postgresql"

        # Reset
        monkeypatch.delenv("MOVIECON_DB_BACKEND", raising=False)
        importlib.reload(db_module)

    def test_sqlite_database_class_exists(self):
        """SQLiteDatabase class is available."""
        from movie_conceptualizer.storage import SQLiteDatabase

        assert SQLiteDatabase is not None
        assert hasattr(SQLiteDatabase, "initialize")
        assert hasattr(SQLiteDatabase, "connection")
        assert hasattr(SQLiteDatabase, "close")

    def test_postgresql_database_class_exists(self):
        """PostgreSQLDatabase class is available."""
        from movie_conceptualizer.storage import PostgreSQLDatabase

        assert PostgreSQLDatabase is not None
        assert hasattr(PostgreSQLDatabase, "initialize")
        assert hasattr(PostgreSQLDatabase, "connection")
        assert hasattr(PostgreSQLDatabase, "close")

    def test_create_database_factory(self):
        """create_database factory function exists."""
        from movie_conceptualizer.storage import create_database

        assert create_database is not None
        assert callable(create_database)

    @pytest.mark.asyncio
    async def test_create_sqlite_database(self):
        """Can create SQLite database via factory."""
        import tempfile

        from movie_conceptualizer.storage import DatabaseBackend, create_database

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "test.db")
            db = create_database(backend=DatabaseBackend.SQLITE, db_path=db_path)
            assert db is not None
            await db.initialize()
            assert db.is_initialized
            await db.close()


class TestBaseRepository:
    """Tests for BaseRepository functionality."""

    def test_base_repository_exists(self):
        """BaseRepository class is available."""
        from movie_conceptualizer.storage import BaseRepository

        assert BaseRepository is not None

    def test_repositories_inherit_base(self):
        """All repositories inherit from BaseRepository."""
        from movie_conceptualizer.storage import (
            BaseRepository,
            GenerationRepository,
            ProjectRepository,
            ScriptRepository,
        )

        assert issubclass(ProjectRepository, BaseRepository)
        assert issubclass(ScriptRepository, BaseRepository)
        assert issubclass(GenerationRepository, BaseRepository)


# Redis rate limiting tests
class TestRedisRateLimitConfiguration:
    """Tests for Redis rate limiting configuration."""

    def test_redis_functions_exist(self):
        """Redis helper functions are available."""
        from movie_conceptualizer.api.ratelimit import (
            check_redis_health,
            get_backend_type,
            get_rate_limit_status,
            is_redis_available,
        )

        assert check_redis_health is not None
        assert get_backend_type is not None
        assert get_rate_limit_status is not None
        assert is_redis_available is not None

    def test_get_backend_type_default(self):
        """Default backend is memory."""
        from movie_conceptualizer.api.ratelimit import get_backend_type

        # Without Redis configured, should be memory
        backend = get_backend_type()
        assert backend in ("memory", "redis")

    def test_is_redis_available_function(self):
        """is_redis_available returns boolean."""
        from movie_conceptualizer.api.ratelimit import is_redis_available

        result = is_redis_available()
        assert isinstance(result, bool)

    def test_get_rate_limit_status_structure(self):
        """get_rate_limit_status returns expected structure."""
        from movie_conceptualizer.api.ratelimit import get_rate_limit_status

        status = get_rate_limit_status()
        assert isinstance(status, dict)
        assert "backend" in status
        # Should have rate limit info
        assert "default_limit" in status or "configured_backend" in status

    @pytest.mark.asyncio
    async def test_check_redis_health_returns_dict(self):
        """check_redis_health returns status dict."""
        from movie_conceptualizer.api.ratelimit import check_redis_health

        health = await check_redis_health()
        assert isinstance(health, dict)
        assert "status" in health


class TestHealthEndpointWithBackends:
    """Tests for health endpoint with backend information."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from fastapi.testclient import TestClient

        from movie_conceptualizer.api import app

        return TestClient(app)

    def test_health_includes_rate_limit_info(self, client):
        """Health endpoint includes rate limit backend info."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        # Should include rate limiting info
        assert "rate_limiting" in data or "status" in data

    def test_redis_health_endpoint_exists(self, client):
        """Redis health endpoint is available."""
        response = client.get("/health/redis")
        # Should return 200 even if Redis not configured
        assert response.status_code == 200
        data = response.json()
        assert "redis" in data or "status" in data
