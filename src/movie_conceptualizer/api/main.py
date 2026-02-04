"""FastAPI application for Movie Conceptualizer API."""

import os
from datetime import datetime

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from movie_conceptualizer.api.ratelimit import (
    DEFAULT_RATE_LIMIT,
    limiter,
    rate_limit_exceeded_handler,
)
from movie_conceptualizer.api.routes import (
    auth_router,
    export_router,
    generation_router,
    projects_router,
    scripts_router,
)

# Auth configuration
REQUIRE_AUTH = os.environ.get("MOVIECON_REQUIRE_AUTH", "false").lower() in (
    "true",
    "1",
    "yes",
)
DEV_MODE = os.environ.get("MOVIECON_DEV_MODE", "true").lower() in ("true", "1", "yes")

# API metadata
API_TITLE = "Movie Conceptualizer API"
API_DESCRIPTION = """
AI-powered filmmaking platform that transforms screenplays into visual pre-production materials.

## Features

* **Script Management** - Upload and parse screenplays in Fountain format
* **AI Analysis** - Analyze scenes for mood, themes, and visual style
* **Shot List Generation** - Automatically generate detailed shot lists
* **Storyboard Prompts** - Create AI image generation prompts for storyboards
* **Export** - Export data in JSON or PDF formats

## Workflow

1. Create a project
2. Upload a screenplay script
3. Run analysis (optional)
4. Generate shot list
5. Generate storyboard prompts
6. Export your materials

Or use the `/generate` endpoint to run the full pipeline at once.

## Rate Limiting

This API implements rate limiting to ensure fair usage:
- Standard endpoints: 100 requests per minute
- AI generation endpoints: 10 requests per minute

Rate limit headers are included in all responses:
- X-RateLimit-Limit: Maximum requests allowed
- X-RateLimit-Remaining: Requests remaining in current window
- X-RateLimit-Reset: Time when the window resets
"""
API_VERSION = "0.1.0"

# Create FastAPI application
app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    license_info={
        "name": "MIT",
        "url": "https://opensource.org/licenses/MIT",
    },
    contact={
        "name": "Movie Conceptualizer Team",
    },
)

# Configure rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers
app.include_router(auth_router, prefix="/api/v1")
app.include_router(projects_router, prefix="/api/v1")
app.include_router(scripts_router, prefix="/api/v1")
app.include_router(generation_router, prefix="/api/v1")
app.include_router(export_router, prefix="/api/v1")


# Exception handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions."""
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred",
            "detail": str(exc) if app.debug else None,
        },
    )


# Root and health endpoints
@app.get(
    "/",
    tags=["info"],
    summary="API Information",
    description="Get basic information about the API.",
)
async def root(request: Request) -> dict:
    """Root endpoint with API information."""
    return {
        "name": API_TITLE,
        "version": API_VERSION,
        "description": "AI-powered filmmaking platform: script to shot list to storyboard",
        "documentation": {
            "swagger": "/docs",
            "redoc": "/redoc",
            "openapi": "/openapi.json",
        },
        "endpoints": {
            "auth": "/api/v1/auth",
            "projects": "/api/v1/projects",
            "health": "/health",
        },
        "auth": {
            "required": REQUIRE_AUTH,
            "dev_mode": DEV_MODE,
        },
    }


@app.get(
    "/health",
    tags=["info"],
    summary="Health Check",
    description="Check if the API is running and healthy.",
)
@limiter.exempt
async def health_check() -> dict:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": API_VERSION,
    }


@app.get(
    "/api/v1",
    tags=["info"],
    summary="API v1 Information",
    description="Get information about API version 1.",
)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def api_v1_info(request: Request) -> dict:
    """API v1 information endpoint."""
    return {
        "version": "1",
        "status": "active",
        "auth": {
            "required": REQUIRE_AUTH,
            "dev_mode": DEV_MODE,
        },
        "endpoints": {
            "auth": {
                "token": "POST /api/v1/auth/token",
                "login": "POST /api/v1/auth/login",
                "register": "POST /api/v1/auth/register",
                "me": "GET /api/v1/auth/me",
                "status": "GET /api/v1/auth/status",
            },
            "projects": {
                "list": "GET /api/v1/projects",
                "create": "POST /api/v1/projects",
                "get": "GET /api/v1/projects/{id}",
                "delete": "DELETE /api/v1/projects/{id}",
            },
            "scripts": {
                "upload": "POST /api/v1/projects/{id}/script",
                "upload_file": "POST /api/v1/projects/{id}/script/upload",
                "get": "GET /api/v1/projects/{id}/script",
                "parse": "POST /api/v1/projects/{id}/script/parse",
            },
            "generation": {
                "analyze": "POST /api/v1/projects/{id}/analyze",
                "shots": "POST /api/v1/projects/{id}/shots",
                "storyboard": "POST /api/v1/projects/{id}/storyboard",
                "full_pipeline": "POST /api/v1/projects/{id}/generate",
                "status": "GET /api/v1/projects/{id}/status",
            },
            "export": {
                "shotlist": "GET /api/v1/projects/{id}/export/shotlist",
                "storyboard": "GET /api/v1/projects/{id}/export/storyboard",
                "analysis": "GET /api/v1/projects/{id}/export/analysis",
            },
        },
    }


def create_app() -> FastAPI:
    """Factory function to create the FastAPI application."""
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "movie_conceptualizer.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
