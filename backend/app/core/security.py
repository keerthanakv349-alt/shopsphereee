"""
Security primitives: password hashing and JWT issuing/verification.

WHY PASSLIB/BCRYPT:
Passwords are NEVER stored in plaintext or with reversible encryption.
Bcrypt is a one-way hash function specifically designed to be slow (it has
a configurable "cost factor"), which makes brute-force attacks on stolen
password hashes impractical. Even if the DB leaks, attackers can't recover
the original passwords.

WHY TWO TOKENS (ACCESS + REFRESH):
- Access token: short-lived (15 min). Sent on every API request. If stolen,
  the damage window is small.
- Refresh token: long-lived (7 days), stored more carefully, used ONLY to
  get a new access token when the old one expires. This lets us keep users
  logged in for a week without forcing them to re-enter a password, while
  still limiting how long a stolen access token is useful.
This is the same pattern used by Google, GitHub, Stripe, etc.
"""
from datetime import datetime, timedelta, timezone

from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def _create_token(subject: str, expires_delta: timedelta, token_type: str) -> str:
    now = datetime.now(timezone.utc)
    to_encode = {
        "sub": subject,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_access_token(user_id: str) -> str:
    return _create_token(
        subject=user_id,
        expires_delta=timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        token_type="access",
    )


def create_refresh_token(user_id: str) -> str:
    return _create_token(
        subject=user_id,
        expires_delta=timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        token_type="refresh",
    )


def decode_token(token: str) -> dict:
    """Raises jose.JWTError if invalid/expired — callers must catch it."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
