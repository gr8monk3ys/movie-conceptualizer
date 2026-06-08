"""Rate limiting configuration for the Movie Conceptualizer API.

This module provides rate limiting using SlowAPI (built on limits library).
Configuration is done via environment variables:
- MOVIECON_RATE_LIMIT: Default rate limit (default: "100/minute")
- MOVIECON_RATE_LIMIT_GENERATION: Stricter limit for AI endpoints (default: "10/minute")
- MOVIECON_RATE_LIMIT_AUTH: Stricter limit for auth endpoints (default: "10/minute")
- MOVIECON_RATE_LIMIT_BACKEND: Storage backend - "memory" or "redis" (default: "memory")
- MOVIECON_REDIS_URL: Redis connection URL (default: "redis://localhost:6379/0")
- MOVIECON_REDIS_PREFIX: Key prefix for Redis (default: "moviecon:ratelimit:")
"""

import logging
import os
from collections.abc import Callable
from typing import TYPE_CHECKING, Optional

from fastapi import Request, Response
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse

if TYPE_CHECKING:
    from redis import Redis

logger = logging.getLogger(__name__)

# Environment variable configuration
DEFAULT_RATE_LIMIT = os.environ.get("MOVIECON_RATE_LIMIT", "100/minute")
GENERATION_RATE_LIMIT = os.environ.get("MOVIECON_RATE_LIMIT_GENERATION", "10/minute")
AUTH_RATE_LIMIT = os.environ.get("MOVIECON_RATE_LIMIT_AUTH", "10/minute")

# Redis configuration
RATE_LIMIT_BACKEND = os.environ.get("MOVIECON_RATE_LIMIT_BACKEND", "memory").lower()
REDIS_URL = os.environ.get("MOVIECON_REDIS_URL", "redis://localhost:6379/0")
REDIS_PREFIX = os.environ.get("MOVIECON_REDIS_PREFIX", "moviecon:ratelimit:")

# Global Redis client for health checks and connection management
_redis_client: Optional["Redis"] = None
_redis_available: bool = False
_backend_type: str = "memory"


def get_client_identifier(request: Request) -> str:
    """
    Get a unique identifier for the client making the request.

    Uses forwarded headers only when MOVIECON_TRUST_PROXY=true.
    Otherwise, falls back to the direct remote address to avoid spoofing.
    """
    trust_proxy = os.environ.get("MOVIECON_TRUST_PROXY", "false").lower() in (
        "true",
        "1",
        "yes",
    )

    if trust_proxy:
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # X-Forwarded-For can contain multiple IPs, take the first (client IP)
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

    # Fall back to direct remote address
    return get_remote_address(request)


def _create_redis_storage_uri() -> str:
    """
    Create the Redis storage URI for the limits library.

    Returns:
        Redis storage URI with prefix configuration
    """
    # The limits library expects the URL format with optional key_prefix
    # Format: redis://host:port/db
    return REDIS_URL


def _try_create_redis_limiter() -> tuple[Limiter, bool, str]:
    """
    Attempt to create a limiter with Redis backend.

    Returns:
        Tuple of (limiter, redis_available, backend_type)
    """
    global _redis_client, _redis_available, _backend_type

    try:
        # Try to import redis
        from redis import Redis
        from redis.connection import ConnectionPool

        # Create connection pool for efficient connection management
        pool = ConnectionPool.from_url(
            REDIS_URL,
            max_connections=10,
            decode_responses=True,
        )

        # Create Redis client with connection pool
        _redis_client = Redis(connection_pool=pool)

        # Test the connection
        _redis_client.ping()

        # Create limiter with Redis storage
        # SlowAPI/limits uses the storage_uri format
        storage_uri = _create_redis_storage_uri()

        limiter = Limiter(
            key_func=get_client_identifier,
            default_limits=[DEFAULT_RATE_LIMIT],
            headers_enabled=True,
            storage_uri=storage_uri,
            strategy="fixed-window",  # or "moving-window" for more accurate limiting
        )

        logger.info(f"Rate limiting initialized with Redis backend: {REDIS_URL}")
        _redis_available = True
        _backend_type = "redis"
        return limiter, True, "redis"

    except ImportError:
        logger.warning(
            "Redis package not installed. Install with: pip install 'movie-conceptualizer[redis]'. "
            "Falling back to in-memory storage."
        )
    except Exception as e:
        logger.warning(
            f"Failed to connect to Redis at {REDIS_URL}: {e}. Falling back to in-memory storage."
        )

    # Fallback to in-memory
    _redis_available = False
    _backend_type = "memory"
    return _create_memory_limiter(), False, "memory"


def _create_memory_limiter() -> Limiter:
    """
    Create a limiter with in-memory storage.

    Returns:
        Limiter with in-memory storage
    """
    return Limiter(
        key_func=get_client_identifier,
        default_limits=[DEFAULT_RATE_LIMIT],
        headers_enabled=True,
    )


def _initialize_limiter() -> Limiter:
    """
    Initialize the rate limiter based on configuration.

    Attempts to use Redis if configured, with automatic fallback to in-memory.

    Returns:
        Configured Limiter instance
    """
    global _backend_type

    if RATE_LIMIT_BACKEND == "redis":
        limiter, _, _ = _try_create_redis_limiter()
        return limiter
    else:
        logger.info("Rate limiting initialized with in-memory storage")
        _backend_type = "memory"
        return _create_memory_limiter()


# Create the limiter instance
limiter = _initialize_limiter()


async def check_redis_health() -> dict:
    """
    Check the health of the Redis connection.

    Returns:
        Dictionary with Redis health status information
    """
    global _redis_client, _redis_available

    if _backend_type != "redis":
        return {
            "status": "not_configured",
            "message": "Redis backend is not configured",
            "backend": _backend_type,
        }

    if _redis_client is None:
        return {
            "status": "unavailable",
            "message": "Redis client not initialized",
            "backend": _backend_type,
        }

    try:
        # Ping Redis to check connection
        _redis_client.ping()

        # Get some basic info
        info = _redis_client.info(section="server")
        memory_info = _redis_client.info(section="memory")

        return {
            "status": "healthy",
            "backend": "redis",
            "url": _mask_redis_url(REDIS_URL),
            "prefix": REDIS_PREFIX,
            "redis_version": info.get("redis_version", "unknown"),
            "used_memory_human": memory_info.get("used_memory_human", "unknown"),
            "connected_clients": _redis_client.info(section="clients").get(
                "connected_clients", "unknown"
            ),
        }
    except Exception as e:
        _redis_available = False
        return {
            "status": "unhealthy",
            "message": f"Redis connection error: {str(e)}",
            "backend": "redis",
            "url": _mask_redis_url(REDIS_URL),
        }


def _mask_redis_url(url: str) -> str:
    """
    Mask sensitive parts of the Redis URL for logging/display.

    Args:
        url: The Redis URL

    Returns:
        Masked URL safe for display
    """
    # Simple masking - hide password if present
    if "@" in url:
        # URL has credentials
        parts = url.split("@")
        host_part = parts[-1]
        return f"redis://***:***@{host_part}"
    return url


def get_rate_limit_status() -> dict:
    """
    Get the current rate limiting configuration status.

    Returns:
        Dictionary with rate limiting configuration information
    """
    return {
        "backend": _backend_type,
        "redis_available": _redis_available,
        "default_limit": DEFAULT_RATE_LIMIT,
        "generation_limit": GENERATION_RATE_LIMIT,
        "auth_limit": AUTH_RATE_LIMIT,
        "configured_backend": RATE_LIMIT_BACKEND,
        "redis_url": _mask_redis_url(REDIS_URL) if RATE_LIMIT_BACKEND == "redis" else None,
        "redis_prefix": REDIS_PREFIX if RATE_LIMIT_BACKEND == "redis" else None,
    }


def is_redis_available() -> bool:
    """
    Check if Redis is available and being used.

    Returns:
        True if Redis is available and configured, False otherwise
    """
    return _redis_available and _backend_type == "redis"


def get_backend_type() -> str:
    """
    Get the current backend type being used.

    Returns:
        "redis" or "memory"
    """
    return _backend_type


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """
    Handle rate limit exceeded exceptions.

    Returns a clear 429 response with information about when the limit resets.

    Args:
        request: The incoming request that triggered the rate limit
        exc: The rate limit exceeded exception

    Returns:
        A JSONResponse with status 429 and rate limit information
    """
    # Parse the rate limit from the exception
    limit_value = str(exc.detail) if hasattr(exc, "detail") else "Rate limit exceeded"

    response = JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "message": f"Rate limit exceeded: {limit_value}",
            "detail": "You have exceeded the allowed number of requests. Please wait before trying again.",
            "retry_after": "Please check the Retry-After header for reset time.",
        },
    )

    # Add standard rate limit headers
    response.headers["Retry-After"] = "60"  # Default retry after 60 seconds

    return response


def get_rate_limit_headers(request: Request, response: Response) -> Response:
    """
    Add rate limit information headers to the response.

    This is handled automatically by SlowAPI when headers_enabled=True,
    but this function can be used for custom header additions.

    Headers added:
    - X-RateLimit-Limit: Maximum requests allowed in the window
    - X-RateLimit-Remaining: Requests remaining in the current window
    - X-RateLimit-Reset: Time when the rate limit window resets

    Args:
        request: The incoming request
        response: The response to add headers to

    Returns:
        The response with rate limit headers added
    """
    return response


# Rate limit decorators for different endpoint types


def standard_rate_limit() -> Callable:
    """
    Standard rate limit decorator for regular endpoints.

    Uses the DEFAULT_RATE_LIMIT (configurable via MOVIECON_RATE_LIMIT env var).
    Default: 100 requests per minute.

    Usage:
        @router.get("/endpoint")
        @standard_rate_limit()
        async def my_endpoint():
            ...
    """
    return limiter.limit(DEFAULT_RATE_LIMIT)


def generation_rate_limit() -> Callable:
    """
    Stricter rate limit decorator for AI generation endpoints.

    Uses the GENERATION_RATE_LIMIT (configurable via MOVIECON_RATE_LIMIT_GENERATION env var).
    Default: 10 requests per minute.

    These endpoints are expensive (AI/LLM calls), so we apply stricter limits.

    Usage:
        @router.post("/generate")
        @generation_rate_limit()
        async def generate_content():
            ...
    """
    return limiter.limit(GENERATION_RATE_LIMIT)


def no_rate_limit() -> Callable:
    """
    Exempt endpoint from rate limiting.

    Use this for health check and other critical monitoring endpoints.

    Usage:
        @router.get("/health")
        @no_rate_limit()
        async def health_check():
            ...
    """
    return limiter.exempt


# Export commonly used items
__all__ = [
    "limiter",
    "rate_limit_exceeded_handler",
    "get_client_identifier",
    "standard_rate_limit",
    "generation_rate_limit",
    "no_rate_limit",
    "DEFAULT_RATE_LIMIT",
    "GENERATION_RATE_LIMIT",
    "RATE_LIMIT_BACKEND",
    "REDIS_URL",
    "REDIS_PREFIX",
    "check_redis_health",
    "get_rate_limit_status",
    "is_redis_available",
    "get_backend_type",
]
