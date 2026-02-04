"""API route modules."""

from movie_conceptualizer.api.routes.auth import router as auth_router
from movie_conceptualizer.api.routes.export import router as export_router
from movie_conceptualizer.api.routes.generation import router as generation_router
from movie_conceptualizer.api.routes.projects import router as projects_router
from movie_conceptualizer.api.routes.scripts import router as scripts_router

__all__ = [
    "auth_router",
    "projects_router",
    "scripts_router",
    "generation_router",
    "export_router",
]
