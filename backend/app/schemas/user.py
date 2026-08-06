"""
Pydantic schemas — the API's "contract" layer.

WHY SCHEMAS ARE SEPARATE FROM MODELS:
app/models/user.py describes the DATABASE table. app/schemas/user.py
describes what the API accepts/returns over HTTP. These are deliberately
different: the DB model has hashed_password, but NO response schema ever
includes it (see UserOut below — it's just omitted, so it's structurally
impossible to leak a password hash in a response). This separation is
standard in every serious FastAPI codebase.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class SignupRequest(BaseModel):
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    phone_number: str | None = Field(default=None, max_length=20)

    @field_validator("password")
    @classmethod
    def password_complexity(cls, v: str) -> str:
        # Production rule: require at least one digit and one letter.
        # Rejecting weak passwords here means bad input never even reaches
        # the DB layer — validation should happen as early as possible.
        if not any(c.isdigit() for c in v) or not any(c.isalpha() for c in v):
            raise ValueError("Password must contain at least one letter and one number")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    # from_attributes lets this schema build directly from a SQLAlchemy
    # User object (schema.model_validate(user_orm_instance)) instead of
    # requiring a manual dict conversion.
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    email: EmailStr
    phone_number: str | None
    role: str
    is_active: bool
    is_email_verified: bool
    created_at: datetime


class AuthResponse(BaseModel):
    user: UserOut
    tokens: TokenPair
