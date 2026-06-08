"""Authentication API routes for Movie Conceptualizer.

Provides endpoints for:
- POST /api/v1/auth/token - Login and get JWT token
- POST /api/v1/auth/register - Register new user (optional)
- GET /api/v1/auth/me - Get current user info
- GET /api/v1/auth/status - Get authentication status
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm

from movie_conceptualizer.api.auth import (
    ALLOW_DEV_FALLBACK,
    ALLOW_REGISTRATION,
    DEV_MODE,
    PASSWORD_POLICY_ENFORCE,
    REFRESH_ROTATE,
    REFRESH_TOKEN_EXPIRE_DAYS,
    REFRESH_TOKENS_ENABLED,
    REQUIRE_AUTH,
    TOKEN_EXPIRE_MINUTES,
    AuthStatusResponse,
    LoginRequest,
    RefreshTokenRequest,
    RegisterRequest,
    SetUserRoleRequest,
    Token,
    UserInDB,
    UserResponse,
    UserStore,
    _generate_refresh_token,
    _hash_refresh_token,
    create_access_token,
    get_current_active_user,
    get_optional_current_user,
    get_user_store,
    require_admin_access,
    validate_password_policy,
)
from movie_conceptualizer.api.ratelimit import AUTH_RATE_LIMIT, DEFAULT_RATE_LIMIT, limiter
from movie_conceptualizer.api.schemas import ErrorResponse
from movie_conceptualizer.storage import RefreshTokenRepository, UserRepository

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
@limiter.limit(AUTH_RATE_LIMIT)
async def login_for_access_token(
    request: Request,
    response: Response,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    user_store: Annotated[UserStore, Depends(get_user_store)],
) -> Token:
    """Authenticate user and return JWT access token.

    This endpoint supports OAuth2 password flow with form data:
    - username: User's username
    - password: User's password

    Returns a JWT token valid for the configured expiration time.
    """
    user = await user_store.authenticate_user(form_data.username, form_data.password)

    if (
        not user
        and REQUIRE_AUTH is False
        and DEV_MODE
        and ALLOW_DEV_FALLBACK
        and form_data.username == "dev"
    ):
        # Allow dev login without auth requirement
        user = await user_store.get_user_by_username("dev")

    if (
        not user
        and DEV_MODE
        and ALLOW_DEV_FALLBACK
        and form_data.username == "dev"
        and form_data.password == "dev123"
    ):
        # Dev fallback in case bcrypt backend is unavailable
        try:
            user = await user_store.create_user("dev", "dev123", enforce_policy=False)
        except ValueError:
            user = await user_store.get_user_by_username("dev")

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

    refresh_token = None
    if REFRESH_TOKENS_ENABLED:
        refresh_token = _generate_refresh_token()
        repo = RefreshTokenRepository()
        await repo.create(
            user_id=user.id,
            token_hash=_hash_refresh_token(refresh_token),
            expires_at=datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        )

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
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
@limiter.limit(AUTH_RATE_LIMIT)
async def login_json(
    request: Request,
    response: Response,
    body: LoginRequest,
    user_store: Annotated[UserStore, Depends(get_user_store)],
) -> Token:
    """Authenticate user with JSON body and return JWT access token."""
    user = await user_store.authenticate_user(body.username, body.password)

    if (
        not user
        and REQUIRE_AUTH is False
        and DEV_MODE
        and ALLOW_DEV_FALLBACK
        and body.username == "dev"
    ):
        user = await user_store.get_user_by_username("dev")

    if (
        not user
        and DEV_MODE
        and ALLOW_DEV_FALLBACK
        and body.username == "dev"
        and body.password == "dev123"
    ):
        try:
            user = await user_store.create_user("dev", "dev123", enforce_policy=False)
        except ValueError:
            user = await user_store.get_user_by_username("dev")

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

    refresh_token = None
    if REFRESH_TOKENS_ENABLED:
        refresh_token = _generate_refresh_token()
        repo = RefreshTokenRepository()
        await repo.create(
            user_id=user.id,
            token_hash=_hash_refresh_token(refresh_token),
            expires_at=datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        )

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
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
@limiter.limit(AUTH_RATE_LIMIT)
async def register_user(
    request: Request,
    response: Response,
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
    if await user_store.user_exists(body.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered",
        )

    if PASSWORD_POLICY_ENFORCE:
        errors = validate_password_policy(body.password)
        if errors:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=" ".join(errors),
            )

    # Create the user
    try:
        user = await user_store.create_user(
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
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.post(
    "/users/{user_id}/role",
    response_model=UserResponse,
    responses={
        200: {"description": "User role updated"},
        404: {"model": ErrorResponse, "description": "User not found"},
        429: {"model": ErrorResponse, "description": "Rate limit exceeded"},
    },
    summary="Update user role",
    description="Update a user's role (admin only).",
)
@limiter.limit(DEFAULT_RATE_LIMIT)
async def update_user_role(
    request: Request,
    response: Response,
    user_id: str,
    body: SetUserRoleRequest,
    current_user: Annotated[UserInDB, Depends(require_admin_access)] = None,
) -> UserResponse:
    repo = UserRepository()
    updated = await repo.set_role(user_id, body.role)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    user = await repo.get_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    return UserResponse(
        id=user.id,
        username=user.username,
        role=user.role,
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
    response: Response,
    current_user: Annotated[UserInDB, Depends(get_current_active_user)],
) -> UserResponse:
    """Get current authenticated user's information."""
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        role=current_user.role,
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
    response: Response,
    current_user: Annotated[UserInDB | None, Depends(get_optional_current_user)],
) -> AuthStatusResponse:
    """Get authentication status and configuration."""
    user_response = None
    if current_user:
        user_response = UserResponse(
            id=current_user.id,
            username=current_user.username,
            role=current_user.role,
            is_active=current_user.is_active,
            created_at=current_user.created_at,
        )

    return AuthStatusResponse(
        authenticated=current_user is not None,
        user=user_response,
        auth_required=REQUIRE_AUTH,
        registration_enabled=ALLOW_REGISTRATION,
    )


@router.post(
    "/refresh",
    response_model=Token,
    responses={
        200: {"description": "Token refreshed"},
        401: {"description": "Invalid refresh token"},
    },
    summary="Refresh access token",
)
@limiter.limit(AUTH_RATE_LIMIT)
async def refresh_access_token(
    request: Request,
    response: Response,
    body: RefreshTokenRequest,
) -> Token:
    if not REFRESH_TOKENS_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Refresh tokens are disabled",
        )

    token_hash = _hash_refresh_token(body.refresh_token)
    repo = RefreshTokenRepository()
    record = await repo.get_by_hash(token_hash)
    if not record or record.get("revoked_at"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    expires_at = record.get("expires_at")
    if expires_at and expires_at < datetime.now(UTC):
        await repo.revoke(token_hash)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token expired",
        )

    user_repo = UserRepository()
    user = await user_repo.get_by_id(record["user_id"])
    access_token_expires = timedelta(minutes=TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": record["user_id"], "username": user.username if user else None},
        expires_delta=access_token_expires,
    )

    refresh_token = body.refresh_token
    if REFRESH_ROTATE:
        await repo.revoke(token_hash)
        refresh_token = _generate_refresh_token()
        await repo.create(
            user_id=record["user_id"],
            token_hash=_hash_refresh_token(refresh_token),
            expires_at=datetime.now(UTC) + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        )

    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post(
    "/logout",
    responses={
        200: {"description": "Token revoked"},
    },
    summary="Revoke refresh token",
)
@limiter.limit(AUTH_RATE_LIMIT)
async def logout(
    request: Request,
    response: Response,
    body: RefreshTokenRequest,
) -> dict:
    token_hash = _hash_refresh_token(body.refresh_token)
    repo = RefreshTokenRepository()
    await repo.revoke(token_hash)
    return {"revoked": True}
