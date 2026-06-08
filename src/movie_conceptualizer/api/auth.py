"""JWT Authentication module for Movie Conceptualizer API.

This module provides:
- JWT token encoding/decoding using python-jose
- Password hashing using passlib with bcrypt
- In-memory user storage with pre-seeded dev user
- OAuth2 password bearer scheme for token authentication
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, Field, field_validator

from movie_conceptualizer.storage import UserRepository

# -----------------------------------------------------------------------------
# Compatibility shim for bcrypt>=4, which removed bcrypt.__about__.__version__.
# passlib 1.7.4 still expects it and logs warnings otherwise.
# -----------------------------------------------------------------------------
try:
    import bcrypt

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
REFRESH_TOKEN_EXPIRE_DAYS = int(os.environ.get("MOVIECON_REFRESH_TOKEN_EXPIRE_DAYS", "14"))
REFRESH_TOKENS_ENABLED = os.environ.get("MOVIECON_REFRESH_TOKENS_ENABLED", "true").lower() in (
    "true",
    "1",
    "yes",
)
REFRESH_ROTATE = os.environ.get("MOVIECON_REFRESH_ROTATE", "true").lower() in (
    "true",
    "1",
    "yes",
)
REQUIRE_AUTH = os.environ.get("MOVIECON_REQUIRE_AUTH", "false").lower() in ("true", "1", "yes")
DEV_MODE = os.environ.get("MOVIECON_DEV_MODE", "true").lower() in ("true", "1", "yes")
ALLOW_DEV_FALLBACK = os.environ.get("MOVIECON_ALLOW_DEV_FALLBACK", "false").lower() in (
    "true",
    "1",
    "yes",
)
ALLOW_REGISTRATION = os.environ.get("MOVIECON_ALLOW_REGISTRATION", "true").lower() in (
    "true",
    "1",
    "yes",
)
ADMIN_USERS = [
    u.strip() for u in os.environ.get("MOVIECON_ADMIN_USERS", "").split(",") if u.strip()
]
ADMIN_POLICY = os.environ.get("MOVIECON_ADMIN_POLICY", "role").lower()
ADMIN_MFA_SECRET = os.environ.get("MOVIECON_ADMIN_MFA_SECRET", "").strip()
ADMIN_MFA_WINDOW = int(os.environ.get("MOVIECON_ADMIN_MFA_WINDOW", "1"))
ALLOWED_ROLES = [
    role.strip()
    for role in os.environ.get("MOVIECON_ALLOWED_ROLES", "user,admin").split(",")
    if role.strip()
]
PASSWORD_MIN_LENGTH = int(os.environ.get("MOVIECON_PASSWORD_MIN_LENGTH", "8"))
PASSWORD_REQUIRE_UPPER = os.environ.get("MOVIECON_PASSWORD_REQUIRE_UPPER", "false").lower() in (
    "true",
    "1",
    "yes",
)
PASSWORD_REQUIRE_LOWER = os.environ.get("MOVIECON_PASSWORD_REQUIRE_LOWER", "true").lower() in (
    "true",
    "1",
    "yes",
)
PASSWORD_REQUIRE_DIGIT = os.environ.get("MOVIECON_PASSWORD_REQUIRE_DIGIT", "true").lower() in (
    "true",
    "1",
    "yes",
)
PASSWORD_REQUIRE_SPECIAL = os.environ.get("MOVIECON_PASSWORD_REQUIRE_SPECIAL", "false").lower() in (
    "true",
    "1",
    "yes",
)
PASSWORD_POLICY_ENFORCE = os.environ.get("MOVIECON_PASSWORD_POLICY_ENFORCE", "true").lower() in (
    "true",
    "1",
    "yes",
)


def is_admin_user(user: UserInDB | None) -> bool:
    if user is None:
        return False
    if ADMIN_POLICY == "role":
        return user.role == "admin"
    if ADMIN_USERS:
        return user.username in ADMIN_USERS
    return False


# =============================================================================
# Password Hashing
# =============================================================================

# Password context using bcrypt for secure hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against a hashed password."""
    return bool(pwd_context.verify(plain_password, hashed_password))


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt."""
    try:
        return str(pwd_context.hash(password))
    except Exception:
        if DEV_MODE and ALLOW_DEV_FALLBACK:
            # Fallback for environments where bcrypt backend is unavailable
            return password
        raise


def validate_password_policy(password: str) -> list[str]:
    """Validate password against configurable complexity rules."""
    errors: list[str] = []
    if len(password) < PASSWORD_MIN_LENGTH:
        errors.append(f"Password must be at least {PASSWORD_MIN_LENGTH} characters.")
    if PASSWORD_REQUIRE_UPPER and not any(c.isupper() for c in password):
        errors.append("Password must include an uppercase letter.")
    if PASSWORD_REQUIRE_LOWER and not any(c.islower() for c in password):
        errors.append("Password must include a lowercase letter.")
    if PASSWORD_REQUIRE_DIGIT and not any(c.isdigit() for c in password):
        errors.append("Password must include a digit.")
    if PASSWORD_REQUIRE_SPECIAL and not any(not c.isalnum() for c in password):
        errors.append("Password must include a special character.")
    return errors


# =============================================================================
# User Model and Storage
# =============================================================================


class User(BaseModel):
    """User model for authentication."""

    id: str = Field(..., description="Unique user identifier")
    username: str = Field(..., description="Username for login")
    hashed_password: str = Field(..., description="Bcrypt hashed password")
    role: str = Field("user", description="User role")
    is_active: bool = Field(True, description="Whether user account is active")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = {"from_attributes": True}


class UserInDB(User):
    """User model with password field for database operations."""

    pass


class UserPublic(BaseModel):
    """Public user data (without sensitive fields)."""

    id: str = Field(..., description="Unique user identifier")
    username: str = Field(..., description="Username")
    role: str = Field(..., description="User role")
    is_active: bool = Field(..., description="Whether user account is active")
    created_at: datetime = Field(..., description="Account creation timestamp")


class UserStore:
    """Database-backed user storage."""

    def __init__(self, repository: UserRepository | None = None):
        self._repo = repository or UserRepository()

    async def create_user(
        self,
        username: str,
        password: str,
        *,
        enforce_policy: bool = True,
    ) -> UserInDB:
        """Create a new user with hashed password."""
        if await self._repo.user_exists(username):
            raise ValueError(f"Username '{username}' already exists")

        if enforce_policy and PASSWORD_POLICY_ENFORCE:
            errors = validate_password_policy(password)
            if errors:
                raise ValueError("; ".join(errors))

        hashed_password = get_password_hash(password)
        role = "admin" if username in ADMIN_USERS else "user"
        model = await self._repo.create(
            username=username,
            hashed_password=hashed_password,
            role=role,
            is_active=True,
        )
        return UserInDB(
            id=model.id,
            username=model.username,
            hashed_password=model.hashed_password,
            role=model.role,
            is_active=model.is_active,
            created_at=model.created_at,
        )

    async def get_user_by_id(self, user_id: str) -> UserInDB | None:
        """Get a user by their ID."""
        model = await self._repo.get_by_id(user_id)
        if model is None:
            return None
        return UserInDB(
            id=model.id,
            username=model.username,
            hashed_password=model.hashed_password,
            role=model.role,
            is_active=model.is_active,
            created_at=model.created_at,
        )

    async def get_user_by_username(self, username: str) -> UserInDB | None:
        """Get a user by their username."""
        model = await self._repo.get_by_username(username)
        if model is None:
            return None
        return UserInDB(
            id=model.id,
            username=model.username,
            hashed_password=model.hashed_password,
            role=model.role,
            is_active=model.is_active,
            created_at=model.created_at,
        )

    async def authenticate_user(self, username: str, password: str) -> UserInDB | None:
        """Authenticate a user by username and password."""
        user = await self.get_user_by_username(username)
        if not user:
            if DEV_MODE and ALLOW_DEV_FALLBACK and username == "dev" and password == "dev123":
                try:
                    return await self.create_user("dev", "dev123")
                except ValueError:
                    return await self.get_user_by_username(username)
            return None
        try:
            if not verify_password(password, user.hashed_password):
                if DEV_MODE and ALLOW_DEV_FALLBACK and username == "dev" and password == "dev123":
                    return user
                if DEV_MODE and ALLOW_DEV_FALLBACK and password == user.hashed_password:
                    return user
                return None
        except Exception:
            if DEV_MODE and ALLOW_DEV_FALLBACK and username == "dev" and password == "dev123":
                return user
            if DEV_MODE and ALLOW_DEV_FALLBACK and password == user.hashed_password:
                return user
            raise
        return user

    async def deactivate_user(self, user_id: str) -> bool:
        """Deactivate a user account."""
        return await self._repo.set_active(user_id, False)

    async def user_exists(self, username: str) -> bool:
        """Check if a username is already taken."""
        return await self._repo.user_exists(username)


# Global user store instance
_user_store: UserStore | None = None


def get_user_store() -> UserStore:
    """Get the user store instance (singleton pattern)."""
    global _user_store
    if _user_store is None:
        _user_store = UserStore()
    return _user_store


# =============================================================================
# JWT Token Handling
# =============================================================================


class Token(BaseModel):
    """OAuth2 token response model."""

    access_token: str = Field(..., description="JWT access token")
    refresh_token: str | None = Field(None, description="Refresh token")
    token_type: str = Field("bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration in seconds")


class TokenData(BaseModel):
    """Data extracted from JWT token."""

    user_id: str | None = None
    username: str | None = None
    exp: datetime | None = None


class RefreshTokenRequest(BaseModel):
    """Refresh token request."""

    refresh_token: str = Field(..., min_length=1)


def create_access_token(
    data: dict[str, Any],
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
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})

    encoded_jwt: str = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
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

        exp = datetime.fromtimestamp(exp_timestamp, tz=UTC) if exp_timestamp else None

        return TokenData(user_id=user_id, username=username, exp=exp)
    except JWTError:
        return None


def _hash_refresh_token(token: str) -> str:
    digest = hmac.new(SECRET_KEY.encode("utf-8"), token.encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()


def _generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def _verify_totp(secret_b32: str, code: str, window: int = 1) -> bool:
    try:
        key = base64.b32decode(secret_b32, casefold=True)
    except Exception:
        return False
    try:
        int(code)
    except ValueError:
        return False

    timestep = 30
    now = int(datetime.now(UTC).timestamp())
    counter = now // timestep
    for offset in range(-window, window + 1):
        counter_bytes = (counter + offset).to_bytes(8, "big")
        digest = hmac.new(key, counter_bytes, hashlib.sha1).digest()
        offset_bits = digest[-1] & 0x0F
        code_int = int.from_bytes(digest[offset_bits : offset_bits + 4], "big") & 0x7FFFFFFF
        otp = str(code_int % 1_000_000).zfill(6)
        if otp == code:
            return True
    return False


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

    user = await user_store.get_user_by_id(token_data.user_id)
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

    user = await user_store.get_user_by_id(token_data.user_id)
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


def require_admin_access(
    request: Request,
    current_user: Annotated[UserInDB | None, Depends(get_current_user)],
) -> UserInDB:
    """Require admin access and optional MFA."""
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not is_admin_user(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    if ADMIN_MFA_SECRET:
        otp = request.headers.get("X-Admin-OTP", "")
        if not _verify_totp(ADMIN_MFA_SECRET, otp, ADMIN_MFA_WINDOW):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin MFA required",
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


class SetUserRoleRequest(BaseModel):
    """User role update request."""

    role: str = Field(..., pattern=r"^[a-zA-Z0-9_-]+$", description="Role name")

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        role = value.strip()
        if role not in ALLOWED_ROLES:
            raise ValueError(f"Role must be one of: {', '.join(ALLOWED_ROLES)}")
        return role


class UserResponse(BaseModel):
    """User information response."""

    id: str = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    role: str = Field(..., description="User role")
    is_active: bool = Field(..., description="Account active status")
    created_at: datetime = Field(..., description="Account creation time")


class AuthStatusResponse(BaseModel):
    """Authentication status response."""

    authenticated: bool = Field(..., description="Whether user is authenticated")
    user: UserResponse | None = Field(None, description="User info if authenticated")
    auth_required: bool = Field(..., description="Whether auth is required for this API")
    registration_enabled: bool = Field(..., description="Whether registration is enabled")
