"""
Reusable FastAPI dependencies.

WHY DEPENDENCY INJECTION FOR AUTH:
Instead of every protected route manually parsing the Authorization header
and checking the JWT, we write that logic ONCE as `get_current_user` and
any route that needs auth just declares
`current_user: User = Depends(get_current_user)` in its signature. FastAPI
resolves it before the route body runs. This is how role-based route
protection scales cleanly — see require_role() below, used for admin-only
endpoints in later phases.
"""
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.razorpay_gateway import LiveRazorpayGateway, RazorpayGateway
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User, UserRole

# WHY HTTPBearer INSTEAD OF OAuth2PasswordBearer:
# OAuth2PasswordBearer(tokenUrl=...) tells Swagger's "Authorize" dialog to
# POST application/x-www-form-urlencoded username/password fields directly
# to tokenUrl. But POST /api/v1/auth/login is defined to accept a JSON body
# (LoginRequest) — which is also what the Next.js frontend correctly sends.
# The mismatch meant clicking "Authorize" in Swagger always 422'd, even
# though the login endpoint itself was never broken. HTTPBearer's Authorize
# dialog is just a text box for a raw token pasted in after logging in via
# "Try it out" — it never POSTs anywhere, so there's no request to fail.
# Nothing about token validation changes below, only how the token is
# extracted from the request.
bearer_scheme = HTTPBearer(auto_error=True, bearerFormat="JWT")


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise credentials_exception
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.get(User, uuid.UUID(user_id))
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def require_role(*allowed_roles: UserRole):
    """Factory for role-gated routes, e.g. Depends(require_role(UserRole.ADMIN))."""

    def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action",
            )
        return current_user

    return checker


def get_razorpay_gateway() -> RazorpayGateway:
    """A fresh instance per request is intentional and cheap (the SDK
    client itself is stateless) — no reason to manage a singleton here.
    Overridden in tests (see tests/conftest.py) with a fake that never
    makes a real network call."""
    return LiveRazorpayGateway()
