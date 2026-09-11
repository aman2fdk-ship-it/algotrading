import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.config import settings
from app.utils.ratelimit import ip_key, login_limiter, register_limiter, refresh_limiter

from app.database import get_db
from app.models.user import User
from app.schemas.auth import (
    UserRegisterRequest,
    UserLoginRequest,
    ForgotPasswordRequest,
    TokenResponse,
    RefreshTokenRequest,
    UserResponse,
    UserSettingsUpdate,
    MessageResponse,
)
from app.utils.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.utils.dependencies import get_current_user
from app.services.observability import metrics

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])


def _record_auth_failure() -> None:
    """Bump the observability counter for a failed authentication event."""
    metrics.record_auth_failure()


def _raise_rate_limited() -> None:
    """Raise a standard 429 Too Many Requests with a clear message."""
    _record_auth_failure()
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many requests. Please slow down and try again later.",
        headers={"Retry-After": str(int(settings.AUTH_RATE_LIMIT_WINDOW_SECONDS))},
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    request: UserRegisterRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user account (rate-limited per IP + per email)."""
    key = ip_key(http_request)
    if not register_limiter.allow(f"ip:{key}"):
        _raise_rate_limited()
    if not register_limiter.allow(f"email:{request.email.lower()}"):
        _raise_rate_limited()
    # Check if email already exists
    result = await db.execute(select(User).where(User.email == request.email))
    if result.scalar_one_or_none() is not None:
        _record_auth_failure()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = User(
        email=request.email,
        hashed_password=hash_password(request.password),
        name=request.name,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)

    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    logger.info(f"User registered: {user.email} (id={user.id})")
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/login", response_model=TokenResponse)
async def login(
    request: UserLoginRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate and return tokens (rate-limited per IP + per account)."""
    key = ip_key(http_request)
    if not login_limiter.allow(f"ip:{key}"):
        _raise_rate_limited()
    if not login_limiter.allow(f"acct:{request.email.lower()}"):
        _raise_rate_limited()
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()

    if user is None or not verify_password(request.password, user.hashed_password):
        _record_auth_failure()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        _record_auth_failure()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive",
        )

    # Update last login (naive UTC to match the TIMESTAMP WITHOUT TIME ZONE column)
    user.last_login = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.flush()

    access_token = create_access_token(data={"sub": str(user.id)})
    refresh_token = create_refresh_token(data={"sub": str(user.id)})

    logger.info(f"User logged in: {user.email}")
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/forgot-password", response_model=MessageResponse)
async def forgot_password(request: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    """Send password reset link. Stub — logs the request."""
    result = await db.execute(select(User).where(User.email == request.email))
    user = result.scalar_one_or_none()

    # Always return success to prevent email enumeration
    if user:
        logger.info(f"Password reset requested for: {user.email}")
        # In production: generate reset token, send email

    return MessageResponse(
        message="If an account with that email exists, a password reset link has been sent."
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshTokenRequest, http_request: Request):
    """Exchange a refresh token for new access + refresh tokens (rate-limited)."""
    key = ip_key(http_request)
    if not refresh_limiter.allow(f"ip:{key}"):
        _raise_rate_limited()
    try:
        payload = decode_token(request.refresh_token)
        if payload.get("type") != "refresh":
            _record_auth_failure()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type",
            )
        user_id = payload.get("sub")
        if user_id is None:
            _record_auth_failure()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    except ValueError as e:
        _record_auth_failure()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )

    access_token = create_access_token(data={"sub": user_id})
    refresh_token_new = create_refresh_token(data={"sub": user_id})
    return TokenResponse(access_token=access_token, refresh_token=refresh_token_new)


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user profile."""
    return current_user


@router.patch("/settings", response_model=UserResponse)
async def update_settings(
    request: UserSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update user settings."""
    if request.name is not None:
        current_user.name = request.name
    if request.default_symbols is not None:
        current_user.default_symbols = request.default_symbols
    if request.timezone is not None:
        current_user.timezone = request.timezone

    await db.flush()
    await db.refresh(current_user)
    logger.info(f"User settings updated: {current_user.email}")
    return current_user


@router.post("/logout", response_model=MessageResponse)
async def logout(current_user: User = Depends(get_current_user)):
    """Logout. Client should discard tokens."""
    logger.info(f"User logged out: {current_user.email}")
    return MessageResponse(message="Logged out successfully")
