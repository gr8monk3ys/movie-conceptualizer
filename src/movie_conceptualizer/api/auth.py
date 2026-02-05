"""JWT Authentication module for Movie Conceptualizer API.

This module provides:
- JWT token encoding/decoding using python-jose
- Password hashing using passlib with bcrypt
- In-memory user storage with pre-seeded dev user
- OAuth2 password bearer scheme for token authentication
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field

# -----------------------------------------------------------------------------
# Compatibility shim for bcrypt>=4, which removed bcrypt.__about__.__version__.
# passlib 1.7.4 still expects it and logs warnings otherwise.
# -----------------------------------------------------------------------------
try:
    import bcrypt  # type: ignore

    if not hasattr(bcrypt, "__about__"):
        class _BcryptAbout:
            __version__ = getattr(bcrypt, "__version__", "unknown")

        bcrypt.__about__ = _BcryptAbout()  # type: ignore[attr-defined]
except Exception:
    # If bcrypt isn't installed, passlib will handle it later.
    pass


# =============================================================================
# Configuration
# =============================================================================

def _generate_dev_secret() -> str:
    """Generate a secure random secret for development.

    WARNING: This is only used when MOVIECON_SECRET_KEY is not set.
    In production, always set MOVIECON_SECRET_KEY environment variable.
    """
    return secrets.token_urlsafe(32)


# Environment-based configuration
SECRET_KEY = os.environ.get("MOVIECON_SECRET_KEY", _generate_dev_secret())
ALGORITHM = "HS256"
TOKEN_EXPIRE_MINUTES = int(os.environ.get("MOVIECON_TOKEN_EXPIRE_MINUTES", "60"))
REQUIRE_AUTH = os.environ.get("MOVIECON_REQUIRE_AUTH", "false").lower() in ("true", "1", "yes")
DEV_MODE = os.environ.get("MOVIECON_DEV_MODE", "true").lower() in ("true", "1", "yes")
ALLOW_REGISTRATION = os.environ.get("MOVIECON_ALLOW_REGISTRATION", "true").lower() in ("true", "1", "yes")
ADMIN_USERS = [
    u.strip()
    for u in os.environ.get("MOVIECON_ADMIN_USERS", "").split(",")
    if u.strip()
]


def is_admin_user(user: "UserInDB" | None) -> bool:
    if user is None:
        return False
    if not ADMIN_USERS:
        return True
    return user.username in ADMIN_USERS


# =============================================================================
# Password Hashing
# =============================================================================

# Password context using bcrypt for secure hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt."""
    try:
        return pwd_context.hash(password)
    except Exception:
        if DEV_MODE:
            # Fallback for environments where bcrypt backend is unavailable
            return password
        raise


# =============================================================================
# User Model and Storage
# =============================================================================

class User(BaseModel):
    """User model for authentication."""

    id: str = Field(..., description="Unique user identifier")
    username: str = Field(..., description="Username for login")
    hashed_password: str = Field(..., description="Bcrypt hashed password")
    is_active: bool = Field(True, description="Whether user account is active")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {"from_attributes": True}


class UserInDB(User):
    """User model with password field for database operations."""
    pass


class UserPublic(BaseModel):
    """Public user data (without sensitive fields)."""

    id: str = Field(..., description="Unique user identifier")
    username: str = Field(..., description="Username")
    is_active: bool = Field(..., description="Whether user account is active")
    created_at: datetime = Field(..., description="Account creation timestamp")


class UserStore:
    """In-memory user storage for MVP.

    In production, this would be replaced with a proper database.
    """

    def __init__(self):
        self._users: dict[str, UserInDB] = {}
        self._username_to_id: dict[str, str] = {}
        self._next_id = 1

    def _generate_id(self) -> str:
        """Generate a unique user ID."""
        user_id = f"user_{self._next_id}"
        self._next_id += 1
        return user_id

    def create_user(self, username: str, password: str) -> UserInDB:
        """Create a new user with hashed password."""
        if username in self._username_to_id:
            raise ValueError(f"Username '{username}' already exists")

        user_id = self._generate_id()
        hashed_password = get_password_hash(password)

        user = UserInDB(
            id=user_id,
            username=username,
            hashed_password=hashed_password,
            is_active=True,
        )

        self._users[user_id] = user
        self._username_to_id[username] = user_id

        return user

    def get_user_by_id(self, user_id: str) -> UserInDB | None:
        """Get a user by their ID."""
        return self._users.get(user_id)

    def get_user_by_username(self, username: str) -> UserInDB | None:
        """Get a user by their username."""
        user_id = self._username_to_id.get(username)
        if user_id:
            return self._users.get(user_id)
        return None

    def authenticate_user(self, username: str, password: str) -> UserInDB | None:
        """Authenticate a user by username and password."""
        user = self.get_user_by_username(username)
        if not user:
            if DEV_MODE and username == "dev" and password == "dev123":
                try:
                    user = self.create_user("dev", "dev123")
                except ValueError:
                    user = self.get_user_by_username(username)
                return user
            return None
        try:
            if not verify_password(password, user.hashed_password):
                # Dev-mode fallback for the seeded dev user
                if DEV_MODE and username == "dev" and password == "dev123":
                    return user
                if DEV_MODE and password == user.hashed_password:
                    return user
                return None
        except Exception:
            # Dev-mode fallback when bcrypt backend is unavailable
            if DEV_MODE and username == "dev" and password == "dev123":
                return user
            if DEV_MODE and password == user.hashed_password:
                return user
            raise
        return user

    def deactivate_user(self, user_id: str) -> bool:
        """Deactivate a user account."""
        user = self._users.get(user_id)
        if user:
            user.is_active = False
            return True
        return False

    def user_exists(self, username: str) -> bool:
        """Check if a username is already taken."""
        return username in self._username_to_id


# Global user store instance
_user_store: UserStore | None = None


def get_user_store() -> UserStore:
    """Get the user store instance (singleton pattern)."""
    global _user_store
    if _user_store is None:
        _user_store = UserStore()

        # Pre-seed dev user in dev mode
        if DEV_MODE:
            try:
                _user_store.create_user("dev", "dev123")
            except ValueError:
                pass  # User already exists

    return _user_store


# =============================================================================
# JWT Token Handling
# =============================================================================

class Token(BaseModel):
    """OAuth2 token response model."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field("bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration in seconds")


class TokenData(BaseModel):
    """Data extracted from JWT token."""

    user_id: str | None = None
    username: str | None = None
    exp: datetime | None = None


def create_access_token(
    data: dict,
    expires_delta: timedelta | None = None,
) -> str:
    """Create a JWT access token.

    Args:
        data: Payload data to encode in the token
        expires_delta: Optional custom expiration time

    Returns:
        Encoded JWT token string
    """
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> TokenData | None:
    """Decode and validate a JWT access token.

    Args:
        token: The JWT token string to decode

    Returns:
        TokenData if valid, None if invalid or expired
    """
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str | None = payload.get("sub")
        username: str | None = payload.get("username")
        exp_timestamp = payload.get("exp")

        if user_id is None:
            return None

        exp = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc) if exp_timestamp else None

        return TokenData(user_id=user_id, username=username, exp=exp)
    except JWTError:
        return None


# =============================================================================
# OAuth2 Security Scheme
# =============================================================================

# OAuth2 password bearer scheme for token authentication
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/token",
    auto_error=False,  # Don't auto-raise 401, we handle it for optional auth
)

# Strict scheme that always requires auth
oauth2_scheme_strict = OAuth2PasswordBearer(
    tokenUrl="/api/v1/auth/token",
    auto_error=True,
)


# =============================================================================
# Authentication Dependencies
# =============================================================================

async def get_current_user(
    token: Annotated[str | None, Depends(oauth2_scheme)],
    user_store: Annotated[UserStore, Depends(get_user_store)],
) -> UserInDB | None:
    """Get the current user from JWT token (optional authentication).

    This dependency does NOT require authentication - it returns None
    if no valid token is provided. Use get_current_active_user for
    endpoints that require authentication.

    Args:
        token: JWT token from Authorization header
        user_store: User storage dependency

    Returns:
        User if authenticated, None otherwise
    """
    if token is None:
        return None

    token_data = decode_access_token(token)
    if token_data is None or token_data.user_id is None:
        return None

    user = user_store.get_user_by_id(token_data.user_id)
    return user


async def get_current_user_required(
    token: Annotated[str, Depends(oauth2_scheme_strict)],
    user_store: Annotated[UserStore, Depends(get_user_store)],
) -> UserInDB:
    """Get the current user from JWT token (required authentication).

    This dependency REQUIRES authentication - it raises 401 if no valid
    token is provided.

    Args:
        token: JWT token from Authorization header
        user_store: User storage dependency

    Returns:
        Authenticated user

    Raises:
        HTTPException: 401 if not authenticated
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    token_data = decode_access_token(token)
    if token_data is None or token_data.user_id is None:
        raise credentials_exception

    user = user_store.get_user_by_id(token_data.user_id)
    if user is None:
        raise credentials_exception

    return user


async def get_current_active_user(
    current_user: Annotated[UserInDB, Depends(get_current_user_required)],
) -> UserInDB:
    """Get the current active user.

    This dependency requires authentication AND checks that the user
    account is active.

    Args:
        current_user: User from get_current_user_required

    Returns:
        Active authenticated user

    Raises:
        HTTPException: 401 if not authenticated, 403 if account inactive
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user account",
        )
    return current_user


async def get_optional_current_user(
    current_user: Annotated[UserInDB | None, Depends(get_current_user)],
) -> UserInDB | None:
    """Get the current user if authenticated, None otherwise.

    This is useful for endpoints that work differently based on
    whether the user is authenticated.

    Args:
        current_user: User from get_current_user (optional)

    Returns:
        User if authenticated and active, None otherwise
    """
    if current_user is not None and current_user.is_active:
        return current_user
    return None


def require_auth_if_enabled(
    current_user: Annotated[UserInDB | None, Depends(get_current_user)],
) -> UserInDB | None:
    """Require authentication only if MOVIECON_REQUIRE_AUTH is enabled.

    This dependency allows routes to work without auth in dev mode
    while requiring auth in production.

    Args:
        current_user: User from get_current_user (optional)

    Returns:
        User if authenticated, None if auth not required

    Raises:
        HTTPException: 401 if auth is required but not provided
    """
    if REQUIRE_AUTH:
        if current_user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not current_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Inactive user account",
            )
    return current_user


def require_admin_if_enabled(
    current_user: Annotated[UserInDB | None, Depends(get_current_user)],
) -> UserInDB:
    """Require admin access if configured.

    If MOVIECON_ADMIN_USERS is set, only those usernames are allowed.
    If not set, any authenticated user is treated as admin.
    """
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if ADMIN_USERS and current_user.username not in ADMIN_USERS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return current_user


# =============================================================================
# Auth Request/Response Schemas
# =============================================================================

class LoginRequest(BaseModel):
    """Login request schema."""

    username: str = Field(..., min_length=1, max_length=50, description="Username")
    password: str = Field(..., min_length=1, description="Password")


class RegisterRequest(BaseModel):
    """User registration request schema."""

    username: str = Field(
        ...,
        min_length=3,
        max_length=50,
        pattern=r"^[a-zA-Z0-9_-]+$",
        description="Username (alphanumeric, underscores, hyphens)",
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Password (minimum 8 characters)",
    )


class UserResponse(BaseModel):
    """User information response."""

    id: str = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    is_active: bool = Field(..., description="Account active status")
    created_at: datetime = Field(..., description="Account creation time")


class AuthStatusResponse(BaseModel):
    """Authentication status response."""

    authenticated: bool = Field(..., description="Whether user is authenticated")
    user: UserResponse | None = Field(None, description="User info if authenticated")
    auth_required: bool = Field(..., description="Whether auth is required for this API")
    registration_enabled: bool = Field(..., description="Whether registration is enabled")
