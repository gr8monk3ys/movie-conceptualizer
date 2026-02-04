"""Authentication API routes for Movie Conceptualizer.

Provides endpoints for:
- POST /api/v1/auth/token - Login and get JWT token
- POST /api/v1/auth/register - Register new user (optional)
- GET /api/v1/auth/me - Get current user info
- GET /api/v1/auth/status - Get authentication status
"""

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm

from movie_conceptualizer.api.auth import (
    ALLOW_REGISTRATION,
    REQUIRE_AUTH,
    TOKEN_EXPIRE_MINUTES,
    AuthStatusResponse,
    LoginRequest,
    RegisterRequest,
    Token,
    UserInDB,
    UserResponse,
    UserStore,
    create_access_token,
    get_current_active_user,
    get_optional_current_user,
    get_user_store,
)
from movie_conceptualizer.api.ratelimit import DEFAULT_RATE_LIMIT, GENERATION_RATE_LIMIT, limiter
from movie_conceptualizer.api.schemas import ErrorResponse

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post(
    "/token",
    response_model=Token,
    responses={
        200: {"description": "Successfully authenticated"},
        401: {"description": "Invalid credentials"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Login and get access token",
    description="""
Authenticate with username and password to receive a JWT access token.

The token should be included in subsequent requests using the Authorization header:
`Authorization: Bearer <token>`

Supports both JSON body and OAuth2 form data for compatibility.
""",
)
@limiter.limit(GENERATION_RATE_LIMIT)
async def login_for_access_token(
    request: Request,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    user_store: Annotated[UserStore, Depends(get_user_store)],
) -> Token:
    """Authenticate user and return JWT access token.

    This endpoint supports OAuth2 password flow with form data:
    - username: User's username
    - password: User's password

    Returns a JWT token valid for the configured expiration time.
    """
    user = user_store.authenticate_user(form_data.username, form_data.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account",
        )

    # Create access token with user ID and username in payload
    access_token_expires = timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.id, "username": user.username},
        expires_delta=access_token_expires,
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post(
    "/login",
    response_model=Token,
    responses={
        200: {"description": "Successfully authenticated"},
        401: {"description": "Invalid credentials"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Login with JSON body",
    description="""
Alternative login endpoint that accepts JSON body instead of form data.

Useful for API clients that prefer JSON over form encoding.
""",
)
@limiter.limit(GENERATION_RATE_LIMIT)
async def login_json(
    request: Request,
    body: LoginRequest,
    user_store: Annotated[UserStore, Depends(get_user_store)],
) -> Token:
    """Authenticate user with JSON body and return JWT access token."""
    user = user_store.authenticate_user(body.username, body.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account",
        )

    access_token_expires = timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.id, "username": user.username},
        expires_delta=access_token_expires,
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        201: {"description": "User created successfully"},
        400: {"description": "Username already exists"},
        403: {"description": "Registration is disabled"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Register a new user",
    description="""
Register a new user account.

Registration can be disabled by setting `MOVIECON_ALLOW_REGISTRATION=false`.

Password requirements:
- Minimum 8 characters

Username requirements:
- 3-50 characters
- Alphanumeric, underscores, and hyphens only
""",
)
@limiter.limit(GENERATION_RATE_LIMIT)
async def register_user(
    request: Request,
    body: RegisterRequest,
    user_store: Annotated[UserStore, Depends(get_user_store)],
) -> UserResponse:
    """Register a new user account."""
    # Check if registration is enabled
    if not ALLOW_REGISTRATION:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User registration is disabled",
        )

    # Check if username is already taken
    if user_store.user_exists(body.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    # Create the user
    try:
        user = user_store.create_user(
            username=body.username,
            password=body.password,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return UserResponse(
        id=user.id,
        username=user.username,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    responses={
        200: {"description": "Current user information"},
        401: {"description": "Not authenticated"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Get current user",
    description="Get information about the currently authenticated user.",
)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def get_current_user_info(
    request: Request,
    current_user: Annotated[UserInDB, Depends(get_current_active_user)],
) -> UserResponse:
    """Get current authenticated user's information."""
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        is_active=current_user.is_active,
        created_at=current_user.created_at,
    )


@router.get(
    "/status",
    response_model=AuthStatusResponse,
    responses={
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Get authentication status",
    description="""
Get the current authentication status and configuration.

Returns:
- Whether the user is authenticated
- User info (if authenticated)
- Whether authentication is required for this API
- Whether registration is enabled
""",
)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def get_auth_status(
    request: Request,
    current_user: Annotated[UserInDB | None, Depends(get_optional_current_user)],
) -> AuthStatusResponse:
    """Get authentication status and configuration."""
    user_response = None
    if current_user:
        user_response = UserResponse(
            id=current_user.id,
            username=current_user.username,
            is_active=current_user.is_active,
            created_at=current_user.created_at,
        )

    return AuthStatusResponse(
        authenticated=current_user is not None,
        user=user_response,
        auth_required=REQUIRE_AUTH,
        registration_enabled=ALLOW_REGISTRATION,
    )
