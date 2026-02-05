"""FastAPI application for Movie Conceptualizer API."""

import os
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

import logging

from movie_conceptualizer.api.logging_utils import (
    RequestLogger,
    configure_logging,
    get_request_metrics,
    now_ms,
    request_id_var,
)
from movie_conceptualizer.api.arq_queue import get_queue_health
from movie_conceptualizer.api.ratelimit import (
    DEFAULT_RATE_LIMIT,
    check_redis_health,
    get_backend_type,
    get_rate_limit_status,
    is_redis_available,
    limiter,
    rate_limit_exceeded_handler,
)
from movie_conceptualizer.api.routes import (
    auth_router,
    export_router,
    generation_router,
    jobs_router,
    projects_router,
    scripts_router,
)
from movie_conceptualizer.api.auth import ADMIN_POLICY, ADMIN_USERS, ALLOWED_ROLES
from movie_conceptualizer.storage import JobRepository

# Auth configuration
REQUIRE_AUTH = os.environ.get("MOVIECON_REQUIRE_AUTH", "false").lower() in (
    "true",
    "1",
    "yes",
)
DEV_MODE = os.environ.get("MOVIECON_DEV_MODE", "true").lower() in ("true", "1", "yes")
ALLOW_DEV_FALLBACK = os.environ.get("MOVIECON_ALLOW_DEV_FALLBACK", "false").lower() in (
    "true",
    "1",
    "yes",
)
STRICT_CONFIG = os.environ.get("MOVIECON_STRICT_CONFIG", "false").lower() in (
    "true",
    "1",
    "yes",
)
JOB_BACKEND = os.environ.get("MOVIECON_JOB_BACKEND", "inprocess").lower()
METRICS_ENABLED = os.environ.get("MOVIECON_METRICS_ENABLED", "true").lower() in (
    "true",
    "1",
    "yes",
)

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

# Configure logging early
configure_logging()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await validate_config()
    yield


# Create FastAPI application
app = FastAPI(
    title=API_TITLE,
    description=API_DESCRIPTION,
    version=API_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
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
cors_origins_env = os.environ.get("MOVIECON_CORS_ORIGINS", "").strip()
if cors_origins_env:
    cors_origins = [origin.strip() for origin in cors_origins_env.split(",") if origin.strip()]
elif DEV_MODE:
    cors_origins = ["*"]
else:
    cors_origins = []

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=cors_origins not in ([], ["*"]),
    allow_methods=["*"],
    allow_headers=["*"],
)


# Include routers
app.include_router(auth_router, prefix="/api/v1")
app.include_router(projects_router, prefix="/api/v1")
app.include_router(scripts_router, prefix="/api/v1")
app.include_router(generation_router, prefix="/api/v1")
app.include_router(export_router, prefix="/api/v1")
app.include_router(jobs_router, prefix="/api/v1")

request_logger = RequestLogger(logging.getLogger(__name__))


async def validate_config() -> None:
    """Validate runtime configuration for production safety."""
    issues: list[str] = []
    if REQUIRE_AUTH and os.environ.get("MOVIECON_SECRET_KEY") is None:
        issues.append("MOVIECON_SECRET_KEY is required when auth is enabled.")
    if JOB_BACKEND == "arq":
        if not (os.environ.get("MOVIECON_JOB_REDIS_URL") or os.environ.get("MOVIECON_REDIS_URL")):
            issues.append("Arq backend requires MOVIECON_JOB_REDIS_URL or MOVIECON_REDIS_URL.")
    if ALLOW_DEV_FALLBACK:
        issues.append("MOVIECON_ALLOW_DEV_FALLBACK is enabled (dev-only).")
    if REQUIRE_AUTH:
        if ADMIN_POLICY not in ("env", "role"):
            issues.append("MOVIECON_ADMIN_POLICY must be 'env' or 'role'.")
        if ADMIN_POLICY == "env" and not ADMIN_USERS:
            issues.append("MOVIECON_ADMIN_USERS must be set when admin policy is 'env'.")
        if ADMIN_POLICY == "role" and "admin" not in ALLOWED_ROLES:
            issues.append("MOVIECON_ALLOWED_ROLES must include 'admin' when admin policy is 'role'.")
        if not ALLOWED_ROLES:
            issues.append("MOVIECON_ALLOWED_ROLES must include at least one role.")

    if issues and STRICT_CONFIG:
        raise RuntimeError("Configuration errors: " + "; ".join(issues))
    if issues:
        logging.getLogger(__name__).warning("Configuration warnings: %s", "; ".join(issues))


@app.middleware("http")
async def add_request_logging(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID")
    token = request_id_var.set(request_id)
    start_ms = now_ms()
    try:
        response = await call_next(request)
    finally:
        duration_ms = now_ms() - start_ms
        status_code = response.status_code if "response" in locals() else 500
        request_logger.log_request(
            request.method,
            request.url.path,
            status_code,
            duration_ms,
        )
        request_id_var.reset(token)
    if request_id and response:
        response.headers["X-Request-ID"] = request_id
    return response


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
            "metrics": "/metrics" if METRICS_ENABLED else None,
        },
        "auth": {
            "required": REQUIRE_AUTH,
            "dev_mode": DEV_MODE,
        },
    }


@app.get(
    "/metrics",
    tags=["info"],
    summary="Metrics endpoint",
    description="Expose structured request and job metrics.",
)
@limiter.exempt
async def metrics_endpoint():
    if not METRICS_ENABLED:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Metrics disabled"})

    job_repo = JobRepository()
    job_metrics = await job_repo.get_metrics()
    request_metrics = get_request_metrics()

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "requests": request_metrics,
        "jobs": job_metrics,
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
    health_response = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": API_VERSION,
        "rate_limiting": {
            "backend": get_backend_type(),
        },
        "jobs": {
            "backend": JOB_BACKEND,
        },
    }

    # Include Redis status if Redis backend is configured
    if is_redis_available():
        redis_health = await check_redis_health()
        health_response["rate_limiting"]["redis"] = {
            "status": redis_health.get("status"),
            "version": redis_health.get("redis_version"),
        }
        # Mark overall status as degraded if Redis is unhealthy
        if redis_health.get("status") == "unhealthy":
            health_response["status"] = "degraded"
            health_response["issues"] = ["Redis connection unhealthy"]

    return health_response


@app.get(
    "/health/redis",
    tags=["info"],
    summary="Redis Health Check",
    description="Check the health of the Redis connection for rate limiting.",
)
@limiter.exempt
async def redis_health_check() -> dict:
    """Redis-specific health check endpoint."""
    redis_health = await check_redis_health()

    # Add rate limit configuration info
    rate_limit_info = get_rate_limit_status()

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "redis": redis_health,
        "rate_limiting": {
            "configured_backend": rate_limit_info["configured_backend"],
            "active_backend": rate_limit_info["backend"],
            "default_limit": rate_limit_info["default_limit"],
            "generation_limit": rate_limit_info["generation_limit"],
        },
    }


@app.get(
    "/health/jobs",
    tags=["info"],
    summary="Job Queue Health Check",
    description="Check health of the background job backend.",
)
@limiter.exempt
async def jobs_health_check() -> dict:
    """Job backend health check endpoint."""
    if JOB_BACKEND != "arq":
        return {
            "status": "not_configured",
            "backend": JOB_BACKEND,
        }
    queue_health = await get_queue_health()
    return {
        "status": queue_health.get("status", "unknown"),
        "backend": JOB_BACKEND,
        "details": queue_health,
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
            "jobs": {
                "get": "GET /api/v1/jobs/{id}",
                "list": "GET /api/v1/jobs",
                "dead_letter": "GET /api/v1/jobs/dead-letter",
                "dead_letter_replay": "POST /api/v1/jobs/dead-letter/replay",
                "retry": "POST /api/v1/jobs/{id}/retry",
                "metrics": "GET /api/v1/jobs/metrics",
                "purge": "POST /api/v1/jobs/purge",
                "audit": "GET /api/v1/jobs/audit",
                "audit_purge": "POST /api/v1/jobs/audit/purge",
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
