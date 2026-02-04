"""Rate limiting configuration for the Movie Conceptualizer API.

This module provides rate limiting using SlowAPI (built on limits library).
Configuration is done via environment variables:
- MOVIECON_RATE_LIMIT: Default rate limit (default: "100/minute")
- MOVIECON_RATE_LIMIT_GENERATION: Stricter limit for AI endpoints (default: "10/minute")
"""

import os
from typing import Callable

from fastapi import Request, Response
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.responses import JSONResponse

# Environment variable configuration
DEFAULT_RATE_LIMIT = os.environ.get("MOVIECON_RATE_LIMIT", "100/minute")
GENERATION_RATE_LIMIT = os.environ.get("MOVIECON_RATE_LIMIT_GENERATION", "10/minute")


def get_client_identifier(request: Request) -> str:
    """
    Get a unique identifier for the client making the request.

    Uses the following priority:
    1. X-Forwarded-For header (for clients behind proxies)
    2. X-Real-IP header
    3. Remote address from the connection

    Args:
        request: The incoming FastAPI request

    Returns:
        A string identifier for the client
    """
    # Check for forwarded headers (common in production behind load balancers)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # X-Forwarded-For can contain multiple IPs, take the first (client IP)
        return forwarded_for.split(",")[0].strip()

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    # Fall back to direct remote address
    return get_remote_address(request)


# Create the limiter instance with in-memory storage
# In production, you can upgrade to Redis by setting:
# limiter = Limiter(key_func=get_client_identifier, storage_uri="redis://localhost:6379")
limiter = Limiter(
    key_func=get_client_identifier,
    default_limits=[DEFAULT_RATE_LIMIT],
    headers_enabled=True,  # Enable X-RateLimit headers
)


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
]
