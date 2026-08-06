"""
Auth endpoints: signup, login, refresh, logout, me.

REQUEST FLOW FOR SIGNUP (explained since the brief asked to teach, not just ship):
1. Client POSTs {full_name, email, password} to /api/v1/auth/signup.
2. Pydantic (SignupRequest) validates shape + password complexity BEFORE
   our code runs — malformed requests never reach business logic.
3. We check the DB for an existing user with that email (case-insensitive
   in Postgres via citext would be nicer — noted for Phase 2 — for now we
   lowercase on write and read).
4. Password is hashed with bcrypt — the plaintext is never stored or logged.
5. A new User row is inserted and committed.
6. We issue an access + refresh token pair immediately, so the user is
   logged in right after signing up (no separate login step needed) —
   this matches Myntra/most e-commerce UX.
7. Response returns the user (without password) + tokens.

LOGOUT NOTE: JWTs are stateless by design, so a "logout" endpoint can't
truly invalidate a token server-side without a blocklist (Redis, Phase 2+
"Redis Caching" item in the brief). For Phase 1, logout is a client-side
operation — this endpoint exists so the frontend has a consistent call to
make, and the comment documents why it's a no-op for now rather than
pretending it revokes anything.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from jose import JWTError
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.rate_limit import AUTH_RATE_LIMIT, limiter
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.user import (
    AuthResponse,
    LoginRequest,
    RefreshRequest,
    SignupRequest,
    TokenPair,
    UserOut,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(AUTH_RATE_LIMIT)
def signup(request: Request, payload: SignupRequest, db: Session = Depends(get_db)):
    normalized_email = payload.email.lower()

    existing = db.query(User).filter(User.email == normalized_email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists",
        )

    user = User(
        full_name=payload.full_name.strip(),
        email=normalized_email,
        hashed_password=hash_password(payload.password),
        phone_number=payload.phone_number,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    tokens = TokenPair(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )
    return AuthResponse(user=UserOut.model_validate(user), tokens=tokens)


@router.post("/login", response_model=AuthResponse)
@limiter.limit(AUTH_RATE_LIMIT)
def login(request: Request, payload: LoginRequest, db: Session = Depends(get_db)):
    normalized_email = payload.email.lower()
    user = db.query(User).filter(User.email == normalized_email).first()

    # Deliberately identical error for "no such user" and "wrong password" —
    # revealing which one it was lets attackers enumerate valid emails.
    invalid_credentials = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Incorrect email or password",
    )

    if not user or not user.hashed_password:
        raise invalid_credentials
    if not verify_password(payload.password, user.hashed_password):
        raise invalid_credentials
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

    tokens = TokenPair(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )
    return AuthResponse(user=UserOut.model_validate(user), tokens=tokens)


@router.post("/refresh", response_model=TokenPair)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    invalid_token = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token"
    )
    try:
        decoded = decode_token(payload.refresh_token)
        if decoded.get("type") != "refresh":
            raise invalid_token
    except JWTError:
        raise invalid_token

    user = db.get(User, decoded["sub"])
    if user is None or not user.is_active:
        raise invalid_token

    return TokenPair(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),  # rotate refresh token too
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(current_user: User = Depends(get_current_user)):
    # Stateless JWT logout — see module docstring. Client discards tokens.
    return None


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)
